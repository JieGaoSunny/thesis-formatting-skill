"""Safe, lossless access to the OOXML parts used by Word documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Iterable, Mapping
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree


REQUIRED_PARTS = frozenset(
    {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
)
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
MAX_PARTS = 10_000
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
MAX_PART_UNCOMPRESSED = 128 * 1024 * 1024


class OoxmlError(ValueError):
    """An invalid, unsafe, or corrupt OOXML package."""


@dataclass(frozen=True, slots=True)
class Relationship:
    source_part: str
    id: str
    type: str
    target: str
    target_mode: str | None

    @property
    def identity(self) -> str:
        return "|".join(
            (
                self.source_part,
                self.id,
                self.type,
                self.target,
                self.target_mode or "Internal",
            )
        )


def secure_xml_parser() -> etree.XMLParser:
    """Return a parser that never loads DTDs, entities, or network resources."""

    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        huge_tree=False,
        recover=False,
        remove_comments=False,
        remove_blank_text=False,
        strip_cdata=False,
    )


def parse_xml(data: bytes, *, part_name: str = "<memory>") -> etree._Element:
    """Parse one XML part using the hardened parser."""

    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise OoxmlError(f"unsafe XML declaration in part {part_name!r}")
    try:
        return etree.fromstring(data, parser=secure_xml_parser())
    except (etree.XMLSyntaxError, ValueError) as error:
        raise OoxmlError(f"invalid XML in part {part_name!r}: {error}") from error


def _validate_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or any(component in {"", ".", ".."} for component in path.parts)
    ):
        raise OoxmlError(f"unsafe ZIP part name {name!r}")


def _relationship_source(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    path = PurePosixPath(rels_name)
    if len(path.parts) < 2 or path.parts[-2] != "_rels":
        raise OoxmlError(f"invalid relationships part path {rels_name!r}")
    filename = path.name.removesuffix(".rels")
    return str(PurePosixPath(*path.parts[:-2], filename))


def resolve_relationship_target(source_part: str, target: str) -> str:
    """Resolve an internal OPC relationship target to a package part name."""

    if target.startswith("/"):
        candidate = PurePosixPath(target[1:])
    else:
        candidate = PurePosixPath(source_part).parent / target
    normalized: list[str] = []
    for component in candidate.parts:
        if component in {"", "."}:
            continue
        if component == "..":
            if not normalized:
                raise OoxmlError(f"relationship target escapes package: {target!r}")
            normalized.pop()
        else:
            normalized.append(component)
    result = "/".join(normalized)
    _validate_name(result)
    return result


class OoxmlPackage:
    """An in-memory OOXML package whose writes preserve every untouched part."""

    def __init__(
        self,
        path: Path,
        parts: Mapping[str, bytes],
        infos: Mapping[str, ZipInfo],
    ) -> None:
        self.path = path
        self.parts = MappingProxyType(dict(parts))
        self._infos = dict(infos)
        self._xml: dict[str, etree._Element] = {}

    @classmethod
    def open(cls, path: str | Path) -> "OoxmlPackage":
        package_path = Path(path)
        try:
            with ZipFile(package_path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_PARTS:
                    raise OoxmlError("OOXML package contains too many parts")
                names: set[str] = set()
                total_size = 0
                parts: dict[str, bytes] = {}
                info_by_name: dict[str, ZipInfo] = {}
                for info in infos:
                    _validate_name(info.filename)
                    if info.filename in names:
                        raise OoxmlError(
                            f"duplicate ZIP part {info.filename!r}"
                        )
                    names.add(info.filename)
                    if info.file_size > MAX_PART_UNCOMPRESSED:
                        raise OoxmlError(
                            f"OOXML part {info.filename!r} is too large"
                        )
                    total_size += info.file_size
                    if total_size > MAX_TOTAL_UNCOMPRESSED:
                        raise OoxmlError("OOXML package is too large")
                    parts[info.filename] = archive.read(info)
                    info_by_name[info.filename] = info
        except (BadZipFile, OSError, RuntimeError) as error:
            raise OoxmlError(f"cannot open OOXML package {package_path}: {error}") from error

        missing = sorted(REQUIRED_PARTS - parts.keys())
        if missing:
            raise OoxmlError(
                "OOXML package is missing required part(s): " + ", ".join(missing)
            )

        package = cls(package_path, parts, info_by_name)
        for part_name in REQUIRED_PARTS:
            package.xml(part_name)
        for optional in (
            "word/styles.xml",
            "word/numbering.xml",
            "word/_rels/document.xml.rels",
        ):
            if optional in parts:
                package.xml(optional)
        for relationship in package.relationships():
            if (
                relationship.target_mode != "External"
                and relationship.type.rsplit("/", 1)[-1] in {"header", "footer"}
            ):
                target = resolve_relationship_target(
                    relationship.source_part, relationship.target
                )
                if target not in parts:
                    raise OoxmlError(
                        f"relationship {relationship.id!r} targets missing part "
                        f"{target!r}"
                    )
                package.xml(target)
        return package

    def xml(self, part_name: str) -> etree._Element:
        if part_name in self._xml:
            return self._xml[part_name]
        if part_name not in self.parts:
            raise OoxmlError(f"OOXML part {part_name!r} does not exist")
        self._xml[part_name] = parse_xml(
            self.parts[part_name], part_name=part_name
        )
        return self._xml[part_name]

    def iter_part_names(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(name for name in self.parts if name.startswith(prefix))

    def relationships(self) -> tuple[Relationship, ...]:
        relationships: list[Relationship] = []
        for name in sorted(self.parts):
            if not name.endswith(".rels"):
                continue
            root = self.xml(name)
            try:
                root_name = etree.QName(root)
            except ValueError as error:
                raise OoxmlError(
                    f"invalid relationships root in part {name!r}"
                ) from error
            if (
                root_name.namespace != REL_NS
                or root_name.localname != "Relationships"
            ):
                raise OoxmlError(
                    f"invalid relationships root in part {name!r}"
                )
            source = _relationship_source(name)
            for element in root:
                if not isinstance(element.tag, str):
                    continue
                try:
                    element_name = etree.QName(element)
                except ValueError as error:
                    raise OoxmlError(
                        f"invalid relationship element in part {name!r}"
                    ) from error
                if (
                    element_name.namespace != REL_NS
                    or element_name.localname != "Relationship"
                ):
                    raise OoxmlError(
                        f"invalid relationship element in part {name!r}"
                    )
                relationship_id = element.get("Id")
                relationship_type = element.get("Type")
                target = element.get("Target")
                target_mode = element.get("TargetMode")
                if not relationship_id or not relationship_type or not target:
                    raise OoxmlError(
                        f"incomplete relationship in part {name!r}"
                    )
                if target_mode not in {None, "Internal", "External"}:
                    raise OoxmlError(
                        f"invalid relationship target mode in part {name!r}"
                    )
                relationships.append(
                    Relationship(
                        source_part=source,
                        id=relationship_id,
                        type=relationship_type,
                        target=target,
                        target_mode=target_mode,
                    )
                )
        return tuple(relationships)

    def related_parts(
        self, source_part: str, relationship_kind: str
    ) -> tuple[tuple[Relationship, str], ...]:
        matches: list[tuple[Relationship, str]] = []
        for relationship in self.relationships():
            if (
                relationship.source_part == source_part
                and relationship.type.rsplit("/", 1)[-1] == relationship_kind
                and relationship.target_mode != "External"
            ):
                matches.append(
                    (
                        relationship,
                        resolve_relationship_target(
                            source_part, relationship.target
                        ),
                    )
                )
        return tuple(matches)

    def write(
        self,
        output_path: str | Path,
        replacements: Mapping[str, bytes | etree._Element] | None = None,
    ) -> Path:
        """Write a copy, replacing selected parts and preserving all others."""

        changed = dict(replacements or {})
        serialized: dict[str, bytes] = {}
        for name, value in changed.items():
            _validate_name(name)
            if isinstance(value, etree._Element):
                value = etree.tostring(
                    value,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=None,
                )
            if not isinstance(value, bytes):
                raise TypeError("OOXML replacements must be bytes or XML elements")
            if name.endswith((".xml", ".rels")):
                parse_xml(value, part_name=name)
            serialized[name] = value

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
                for name, data in self.parts.items():
                    archive.writestr(self._infos[name], serialized.get(name, data))
                for name in sorted(changed.keys() - self.parts.keys()):
                    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, serialized[name])
        except OSError as error:
            raise OoxmlError(f"cannot write OOXML package {destination}: {error}") from error
        return destination


def iter_xml_parts(
    package: OoxmlPackage, names: Iterable[str]
) -> tuple[tuple[str, etree._Element], ...]:
    return tuple((name, package.xml(name)) for name in names if name in package.parts)
