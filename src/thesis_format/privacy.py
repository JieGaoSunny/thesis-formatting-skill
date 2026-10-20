"""Fail-closed privacy scanning for public thesis releases."""

from __future__ import annotations

import hashlib
import re
import stat
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

import pymupdf
import pikepdf
from lxml import etree
from PIL import ExifTags, Image, UnidentifiedImageError

from thesis_format.contracts import (
    canonical_sha256,
    shortest_unique_digest_prefixes,
    validate_privacy_report,
)
from thesis_format.profile import FormatProfile, load_profile


_TEXT_SUFFIXES = {
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".tex",
    ".toml",
    ".ts",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png"}
_UTF16LE_EXIF_TAGS = {
    "XPAuthor",
    "XPComment",
    "XPKeywords",
    "XPSubject",
    "XPTitle",
}
_SKIPPED_DIRECTORIES = {".git", ".hg", ".svn", "__pycache__", ".pytest_cache"}
_WORDPROCESSINGML_NAMESPACE = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
_BUILTIN_PATTERNS = (
    (
        "PRIVACY.ABSOLUTE_PATH",
        re.compile(
            r"(?:(?<![A-Z0-9+.-])[A-Z]:[\\/](?:[^\\/\r\n]+[\\/])*[^\\/\r\n]*|"
            r"/(?:Users|home)/[^/\s]+(?:/[^\s]*)?)",
            re.IGNORECASE,
        ),
        "An absolute user path was found.",
    ),
    (
        "PRIVACY.EMAIL",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "An email-like value was found.",
    ),
    (
        "PRIVACY.PHONE",
        re.compile(
            r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)"
            r"\d{3,4}[\s.-]?\d{4}(?!\w)"
        ),
        "A phone-like value was found.",
    ),
)
_IDENTITY_LABELS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("institution_en", re.compile(r"(?im)^\s*(?:institution|university)\s*[:：]\s*(.+)$")),
    ("institution_zh", re.compile(r"(?m)^\s*(?:学校|院校)\s*[:：]\s*(.+)$")),
    ("author", re.compile(r"(?im)^\s*(?:author|作者|姓名)\s*[:：]\s*(.+)$")),
    ("student_id", re.compile(r"(?im)^\s*(?:student\s*id|学号)\s*[:：]\s*(.+)$")),
    ("adviser", re.compile(r"(?im)^\s*(?:adviser|advisor|导师)\s*[:：]\s*(.+)$")),
    ("company", re.compile(r"(?im)^\s*(?:company|公司)\s*[:：]\s*(.+)$")),
)
_FILENAME_IDENTITY = re.compile(
    r"(?i)^(author|student[ _-]*id|company|adviser|advisor|institution)"
    r"[ _-]+(.+?)(?:\.[^.]+)?$"
)
_CORE_PROPERTY_NAMESPACES = {
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "http://purl.org/dc/elements/1.1/",
}
_APP_PROPERTY_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
_CUSTOM_PROPERTY_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
_PERMITTED_IDENTITY_METADATA = {
    "creator": "author",
    "lastmodifiedby": "author",
}
_PDF_CREATOR_ALIASES = frozenset({"author", "creator", "creatortool"})


@dataclass(frozen=True)
class _Finding:
    rule_id: str
    severity: str
    path: str
    location: str
    match_hash: str
    message: str


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\\", "/")).casefold()


def _sha(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _pdf_metadata_key_forms(value: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFC", value).strip().lstrip("/").casefold()
    forms = {normalized}
    if normalized.startswith("{") and "}" in normalized:
        forms.add(normalized.rsplit("}", 1)[1])
    for separator in (":", ".", "|"):
        if separator in normalized:
            forms.add(normalized.rsplit(separator, 1)[1])
    if forms & _PDF_CREATOR_ALIASES:
        forms.update(_PDF_CREATOR_ALIASES)
    return frozenset(forms)


def _pdf_metadata_key_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip().lstrip("/").casefold()
    if normalized.startswith("{") and "}" in normalized:
        return normalized.rsplit("}", 1)[1]
    for separator in (":", "|"):
        if separator in normalized:
            return normalized.rsplit(separator, 1)[1]
    return normalized


def _pdf_metadata_values(value: object) -> tuple[str, ...]:
    values = value if isinstance(value, (list, set, tuple)) else (value,)
    return tuple(rendered for item in values if (rendered := str(item).strip()))


def _read_denylist(path: Path) -> tuple[tuple[str, str], ...]:
    try:
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o444 == 0:
            raise OSError
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeError):
        raise ValueError(
            "denylist configuration is invalid "
            "(thesis_format.privacy.release_check)"
        ) from None
    terms = tuple(
        (line.strip(), _normalized(line.strip()))
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not terms:
        raise ValueError(
            "denylist configuration is invalid "
            "(thesis_format.privacy.release_check)"
        )
    return terms


def _regex_flags(flags: str) -> re.RegexFlag:
    result = re.NOFLAG
    for flag, value in {
        "i": re.IGNORECASE,
        "m": re.MULTILINE,
        "s": re.DOTALL,
        "u": re.UNICODE,
    }.items():
        if flag in flags:
            result |= value
    return result


class _Scanner:
    def __init__(
        self,
        root: Path,
        profile: FormatProfile,
        denylist_path: Path,
        deny_terms: Sequence[tuple[str, str]],
    ) -> None:
        self.root = root
        self.profile = profile
        self.denylist_path = denylist_path.resolve()
        self.deny_terms = deny_terms
        self.findings: dict[tuple[str, str, str, str], _Finding] = {}
        self.scanned: set[str] = set()
        self.skipped: set[str] = set()
        self.profile_patterns = tuple(
            (
                f"PRIVACY.PATTERN.{pattern.id.upper().replace('-', '_')}",
                re.compile(pattern.regex, _regex_flags(pattern.flags)),
                "A profile privacy pattern matched.",
            )
            for pattern in profile.privacy.generic_patterns
        )
        placeholder_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in profile.privacy.unresolved_placeholder_patterns
        ]
        placeholder_patterns.extend(
            (
                re.compile(r"【[^】]*】"),
                re.compile(r"\bTBD\b", re.IGNORECASE),
            )
        )
        self.placeholder_patterns = tuple(placeholder_patterns)

    def _redact_segment(self, segment: str) -> str:
        normalized = _normalized(segment)
        private = any(term in normalized for _, term in self.deny_terms)
        if not private:
            private = any(pattern.search(segment) for _, pattern, _ in _BUILTIN_PATTERNS)
        if not private:
            private = any(pattern.search(segment) for _, pattern, _ in self.profile_patterns)
        if not private:
            private = _FILENAME_IDENTITY.match(segment) is not None
        if not private:
            return segment
        suffix = PurePosixPath(segment).suffix
        return f"[REDACTED]{suffix}"

    def redact_path(self, path: str) -> str:
        normalized = path.replace("\\", "/")
        return "/".join(self._redact_segment(part) for part in normalized.split("/"))

    def display_path(self, path: Path) -> str:
        if not self.root.is_symlink() and self.root.is_dir():
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                relative = path.name
        else:
            relative = path.name
        return self.redact_path(relative)

    def add(
        self,
        rule_id: str,
        path: str,
        location: str,
        matched: str,
        message: str,
        *,
        severity: str = "error",
        hash_value: str | None = None,
    ) -> None:
        safe_path = self.redact_path(path) or "[REDACTED]"
        safe_location = self.redact_path(location) or "document"
        match_hash = hash_value or _sha(_normalized(matched))
        key = (rule_id, safe_path, safe_location, match_hash)
        self.findings[key] = _Finding(
            rule_id,
            severity,
            safe_path,
            safe_location,
            match_hash,
            message,
        )

    def scan_filename(self, path: Path, display_path: str) -> None:
        self.scan_text(path.name, display_path, "filename")
        identity_match = _FILENAME_IDENTITY.match(path.name)
        if identity_match is None:
            return
        label, value = identity_match.groups()
        identity = {
            "author": "author",
            "studentid": "student_id",
            "company": "company",
            "adviser": "adviser",
            "advisor": "adviser",
            "institution": "institution_en",
        }[re.sub(r"[ _-]", "", label.casefold())]
        expected = self.profile.privacy.fictional_values
        mismatch = identity == "company" or _normalized(value) != _normalized(
            getattr(expected, identity)
        )
        if mismatch:
            self.add(
                f"PRIVACY.IDENTITY.{identity.upper()}",
                display_path,
                "filename",
                value,
                "A non-fictional identity value was found.",
            )

    def scan_text(
        self,
        text: str,
        path: str,
        location: str,
        *,
        scan_placeholders: bool = True,
    ) -> None:
        normalized = _normalized(text)
        for term, normalized_term in self.deny_terms:
            if normalized_term in normalized:
                self.add(
                    "PRIVACY.DENYLIST",
                    path,
                    location,
                    term,
                    "A private denylist term was found.",
                    hash_value=_sha(normalized_term),
                )
        for rule_id, pattern, message in (*_BUILTIN_PATTERNS, *self.profile_patterns):
            for match in pattern.finditer(text):
                self.add(rule_id, path, location, match.group(0), message)
        if scan_placeholders:
            for pattern in self.placeholder_patterns:
                for match in pattern.finditer(text):
                    self.add(
                        "PRIVACY.UNRESOLVED_PLACEHOLDER",
                        path,
                        location,
                        match.group(0),
                        "An unresolved placeholder was found.",
                    )
        expected = self.profile.privacy.fictional_values
        for identity, pattern in _IDENTITY_LABELS:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                if identity == "company":
                    mismatch = bool(value)
                else:
                    mismatch = _normalized(value) != _normalized(getattr(expected, identity))
                if mismatch:
                    self.add(
                        f"PRIVACY.IDENTITY.{identity.upper()}",
                        path,
                        location,
                        value,
                        "A non-fictional identity value was found.",
                    )

    def unreadable(self, path: Path, display_path: str, location: str = "file") -> None:
        self.add(
            "PRIVACY.UNREADABLE",
            display_path,
            location,
            display_path,
            "An in-scope file could not be scanned.",
        )

    def unsupported(self, display_path: str) -> None:
        self.add(
            "PRIVACY.UNSUPPORTED",
            display_path,
            "file",
            PurePosixPath(display_path).suffix or display_path,
            "An in-scope file uses an unsupported format.",
        )

    def scan_regular_file(self, path: Path, display_path: str) -> None:
        try:
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or mode & 0o444 == 0:
                raise OSError
        except OSError:
            self.unreadable(path, display_path)
            return
        suffix = path.suffix.casefold()
        if suffix == ".docx":
            self.scan_docx(path, display_path)
        elif suffix == ".pdf":
            self.scan_pdf(path, display_path)
        elif suffix == ".svg":
            self.scan_svg(path, display_path)
        elif suffix in _IMAGE_SUFFIXES:
            self.scan_image(path, display_path)
        elif suffix in _TEXT_SUFFIXES or not suffix:
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeError):
                self.unreadable(path, display_path)
            else:
                self.scan_text_lines(text, display_path)
        else:
            self.unsupported(display_path)
        self.scanned.add(display_path)

    def scan_text_lines(self, text: str, display_path: str) -> None:
        for line_number, line in enumerate(text.splitlines(), 1):
            self.scan_text(line, display_path, f"line:{line_number}")

    def scan_docx(self, path: Path, display_path: str) -> None:
        try:
            with zipfile.ZipFile(path) as package:
                for name in sorted(package.namelist()):
                    safe_name = self.redact_path(name)
                    self.scan_text(
                        name,
                        display_path,
                        f"part:{safe_name}",
                        scan_placeholders=False,
                    )
                    if not (
                        name.endswith(".xml")
                        or name.endswith(".rels")
                        or name == "[Content_Types].xml"
                    ):
                        continue
                    try:
                        raw = package.read(name)
                        root = etree.fromstring(
                            raw,
                            parser=etree.XMLParser(
                                resolve_entities=False,
                                no_network=True,
                            ),
                        )
                    except (
                        KeyError,
                        OSError,
                        RuntimeError,
                        etree.XMLSyntaxError,
                    ):
                        self.add(
                            "PRIVACY.UNREADABLE",
                            display_path,
                            f"part:{safe_name}",
                            safe_name,
                            "An in-scope document part could not be scanned.",
                        )
                        continue
                    self.scan_ooxml_text(root, display_path, safe_name)
                    self.scan_xml_attributes(root, display_path, f"part:{safe_name}")
                    self.scan_ooxml_metadata(root, display_path, safe_name)
        except (OSError, zipfile.BadZipFile):
            self.unreadable(path, display_path, "package")

    def scan_ooxml_text(
        self,
        root: etree._Element,
        path: str,
        part_name: str,
    ) -> None:
        location = f"part:{part_name}"
        namespaces = {"w": _WORDPROCESSINGML_NAMESPACE}
        paragraphs = root.xpath(".//w:p", namespaces=namespaces)
        if paragraphs:
            for paragraph in paragraphs:
                visible_nodes = paragraph.xpath(
                    ".//w:t | .//w:delText",
                    namespaces=namespaces,
                )
                if visible_nodes:
                    self.scan_text(
                        "".join(node.text or "" for node in visible_nodes),
                        path,
                        location,
                    )
            orphan_nodes = root.xpath(
                ".//w:t[not(ancestor::w:p)] | .//w:delText[not(ancestor::w:p)]",
                namespaces=namespaces,
            )
            for node in orphan_nodes:
                if node.text:
                    self.scan_text(node.text, path, location)
            return
        visible_nodes = root.xpath(
            ".//w:t | .//w:delText",
            namespaces=namespaces,
        )
        if visible_nodes:
            self.scan_text(
                "".join(node.text or "" for node in visible_nodes),
                path,
                location,
            )
            return
        text = "".join(root.itertext())
        if text:
            self.scan_text(text, path, location)

    def scan_xml_attributes(
        self,
        root: etree._Element,
        path: str,
        location: str,
    ) -> None:
        for element in root.iter():
            for value in element.attrib.values():
                self.scan_text(value, path, location)

    def scan_ooxml_metadata(
        self,
        root: etree._Element,
        path: str,
        part_name: str,
    ) -> None:
        properties: list[tuple[str, str]] = []
        if part_name == "docProps/core.xml":
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = etree.QName(element)
                if tag.namespace in _CORE_PROPERTY_NAMESPACES:
                    properties.append((tag.localname, "".join(element.itertext()).strip()))
        elif part_name == "docProps/app.xml":
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = etree.QName(element)
                if tag.namespace == _APP_PROPERTY_NAMESPACE:
                    properties.append((tag.localname, "".join(element.itertext()).strip()))
        elif part_name == "docProps/custom.xml":
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = etree.QName(element)
                if (
                    tag.namespace == _CUSTOM_PROPERTY_NAMESPACE
                    and tag.localname == "property"
                    and element.get("name")
                ):
                    properties.append(
                        (element.get("name", ""), "".join(element.itertext()).strip())
                    )
        else:
            return

        forbidden = {
            key.casefold() for key in self.profile.privacy.forbidden_metadata_keys
        }
        expected = self.profile.privacy.fictional_values
        for name, value in properties:
            if not value:
                continue
            lowered = name.casefold()
            location = f"part:{part_name}:metadata:{name}"
            if lowered in forbidden:
                self.add(
                    "PRIVACY.METADATA",
                    path,
                    location,
                    value,
                    "Forbidden document metadata was found and redacted.",
                )
                continue
            identity = _PERMITTED_IDENTITY_METADATA.get(lowered)
            if identity and _normalized(value) != _normalized(
                getattr(expected, identity)
            ):
                self.add(
                    f"PRIVACY.IDENTITY.{identity.upper()}",
                    path,
                    location,
                    value,
                    "A non-fictional identity value was found.",
                )

    def scan_svg(self, path: Path, display_path: str) -> None:
        try:
            root = etree.parse(
                str(path),
                parser=etree.XMLParser(resolve_entities=False, no_network=True),
            ).getroot()
        except (OSError, etree.XMLSyntaxError):
            self.unreadable(path, display_path, "svg")
            return
        text = "".join(root.itertext())
        if text:
            self.scan_text(text, display_path, "svg:text")
        self.scan_xml_attributes(root, display_path, "svg:attribute")

    def scan_image(self, path: Path, display_path: str) -> None:
        try:
            with Image.open(path) as image:
                image.load()
                metadata = list(image.info.items())
                metadata.extend(
                    (
                        ExifTags.TAGS.get(tag, str(tag)),
                        value,
                    )
                    for tag, value in image.getexif().items()
                )
            for key, value in metadata:
                if isinstance(value, bytes):
                    encoding = (
                        "utf-16le"
                        if str(key) in _UTF16LE_EXIF_TAGS
                        else "utf-8"
                    )
                    rendered = value.decode(encoding, errors="ignore").rstrip("\0")
                else:
                    rendered = str(value)
                if rendered:
                    self.scan_text(
                        rendered,
                        display_path,
                        f"metadata:{str(key).casefold()}",
                    )
        except (OSError, UnidentifiedImageError, ValueError):
            self.unreadable(path, display_path, "image")

    def scan_pdf(self, path: Path, display_path: str) -> None:
        try:
            metadata: list[tuple[str, str]] = []
            with pymupdf.open(path) as document:
                metadata.extend(
                    (key, rendered)
                    for key, value in (document.metadata or {}).items()
                    for rendered in _pdf_metadata_values(value)
                )
                for page_number, page in enumerate(document, 1):
                    self.scan_text(
                        page.get_text(), display_path, f"page:{page_number}"
                    )
            with pikepdf.open(path) as pdf:
                if "/Metadata" in pdf.Root:
                    raw_xmp = pdf.Root.Metadata.read_bytes()
                    xmp_root = etree.fromstring(
                        raw_xmp,
                        parser=etree.XMLParser(resolve_entities=False, no_network=True),
                    )
                    if xmp_root.find(
                        ".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
                    ) is None:
                        raise ValueError("PDF metadata stream is not valid XMP")
                with pdf.open_metadata(update_docinfo=False) as xmp:
                    metadata.extend(
                        (str(key), rendered)
                        for key, value in xmp.items()
                        for rendered in _pdf_metadata_values(value)
                    )
                for key, value in pdf.docinfo.items():
                    metadata.extend(
                        (str(key), rendered)
                        for rendered in _pdf_metadata_values(value)
                    )
            forbidden = frozenset(
                form
                for key in self.profile.privacy.forbidden_metadata_keys
                for form in _pdf_metadata_key_forms(key)
            )
            for key, value in sorted(metadata):
                normalized_key = _pdf_metadata_key_name(key)
                location = f"metadata:{normalized_key}"
                self.scan_text(value, display_path, location)
                if _pdf_metadata_key_forms(key) & forbidden:
                    self.add(
                        "PRIVACY.METADATA",
                        display_path,
                        location,
                        value,
                        "Forbidden document metadata was found and redacted.",
                    )
                    continue
                if normalized_key in {"author", "creator"} and _normalized(
                    value
                ) != _normalized(
                    self.profile.privacy.fictional_values.author
                ):
                    self.add(
                        "PRIVACY.IDENTITY.AUTHOR",
                        display_path,
                        location,
                        value,
                        "A non-fictional identity value was found.",
                    )
        except (
            OSError,
            RuntimeError,
            ValueError,
            etree.XMLSyntaxError,
            pikepdf.PdfError,
        ):
            self.unreadable(path, display_path, "pdf")

    def scan(self) -> None:
        paths: Iterable[Path]
        if self.root.is_symlink():
            paths = (self.root,)
        elif self.root.is_dir():
            paths = sorted(self.root.rglob("*"), key=lambda item: item.as_posix())
        else:
            paths = (self.root,)
        for path in paths:
            if any(part in _SKIPPED_DIRECTORIES for part in path.parts):
                if path.is_file():
                    self.skipped.add(self.display_path(path))
                continue
            try:
                display_path = self.display_path(path)
                if path.is_symlink():
                    self.scan_filename(path, display_path)
                    self.scan_text(
                        str(path.readlink()),
                        display_path,
                        "symlink-target",
                    )
                    self.scanned.add(display_path)
                    continue
                if path.absolute() == self.denylist_path:
                    self.skipped.add(self.display_path(path))
                    continue
                if not path.is_file():
                    continue
            except OSError:
                self.unreadable(path, self.display_path(path))
                continue
            self.scan_filename(path, display_path)
            self.scan_regular_file(path, display_path)


def _default_denylist(source: Path) -> Path:
    base = source if source.is_dir() else source.parent
    return base / ".privacy-denylist.txt"


def _report(scanner: _Scanner, denylist_path: Path) -> dict[str, object]:
    ordered = sorted(
        scanner.findings.values(),
        key=lambda item: (
            unicodedata.normalize("NFC", item.path),
            unicodedata.normalize("NFC", item.location),
            item.rule_id,
            item.match_hash,
        ),
    )
    full_digests = [
        canonical_sha256(
            ["1.0", item.rule_id, item.path, item.location, item.match_hash]
        )
        for item in ordered
    ]
    ids = shortest_unique_digest_prefixes(full_digests)
    findings = [
        {
            "finding_id": finding_id,
            "rule_id": item.rule_id,
            "severity": item.severity,
            "path": item.path,
            "location": item.location,
            "redacted_match_sha256": item.match_hash,
            "message": item.message,
        }
        for item, finding_id in zip(ordered, ids, strict=True)
    ]
    findings.sort(
        key=lambda item: (
            unicodedata.normalize("NFC", item["path"]),
            unicodedata.normalize("NFC", item["location"]),
            item["rule_id"],
            item["redacted_match_sha256"],
            item["finding_id"],
        )
    )
    counts = Counter(item["severity"] for item in findings)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "root_sha256": _sha(str(scanner.root.resolve())),
        "denylist_sha256": _sha(denylist_path.read_bytes()),
        "scanned_files": sorted(scanner.scanned),
        "skipped_files": sorted(scanner.skipped),
        "findings": findings,
        "summary": {
            "errors": counts["error"],
            "violations": counts["violation"],
            "warnings": counts["warning"],
        },
    }
    validate_privacy_report(report)
    return report


def release_check(
    source: Path | str,
    profile_path: Path | str,
    denylist_path: Path | str | None = None,
) -> dict[str, object]:
    """Scan a repository or release artifact without exposing matched values."""

    source = Path(source)
    profile_path = Path(profile_path)
    denylist = Path(denylist_path) if denylist_path is not None else _default_denylist(source)
    if source.is_symlink() or (
        not source.exists() or (not source.is_file() and not source.is_dir())
    ):
        raise ValueError("privacy scan source is invalid")
    deny_terms = _read_denylist(denylist)
    try:
        profile = load_profile(profile_path)
    except (OSError, ValueError):
        raise ValueError("privacy configuration is invalid") from None
    scanner = _Scanner(source, profile, denylist, deny_terms)
    scanner.scan()
    return _report(scanner, denylist)


def render_privacy_markdown(report: Mapping[str, object]) -> str:
    """Render a deterministic privacy report containing redacted data only."""

    validate_privacy_report(report)
    summary = report["summary"]
    lines = [
        "# Privacy release check",
        "",
        f"- Root SHA-256: `{report['root_sha256']}`",
        f"- Denylist SHA-256: `{report['denylist_sha256']}`",
        f"- Scanned files: {len(report['scanned_files'])}",
        f"- Skipped files: {len(report['skipped_files'])}",
        (
            f"- Findings: {summary['errors']} errors, "  # type: ignore[index]
            f"{summary['violations']} violations, "  # type: ignore[index]
            f"{summary['warnings']} warnings"  # type: ignore[index]
        ),
        "",
        "## Findings",
        "",
    ]
    findings = report["findings"]
    if not findings:
        lines.append("No privacy findings.")
    else:
        lines.extend(
            (
                f"- **{item['rule_id']}** `{item['path']}` "
                f"({item['location']}): {item['message']} "
                f"`sha256:{item['redacted_match_sha256']}`"
            )
            for item in findings  # type: ignore[union-attr]
        )
    return "\n".join(lines) + "\n"


__all__ = ["release_check", "render_privacy_markdown"]
