"""Immutable semantic inspection of WordprocessingML documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lxml import etree

from thesis_format.ooxml import OoxmlPackage, Relationship
from thesis_format.profile import FormatProfile, TextPattern


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS, "r": R_NS}
W_VAL = f"{{{W_NS}}}val"
W_INSTR = f"{{{W_NS}}}instr"
W_FLD_CHAR_TYPE = f"{{{W_NS}}}fldCharType"
W_FLD_CHAR = f"{{{W_NS}}}fldChar"
W_FLD_SIMPLE = f"{{{W_NS}}}fldSimple"
W_INSTR_TEXT = f"{{{W_NS}}}instrText"
R_ATTRIBUTES = {
    f"{{{R_NS}}}id",
    f"{{{R_NS}}}embed",
    f"{{{R_NS}}}link",
}
AUTOMATIC_ROLES = frozenset(
    {
        "front_heading",
        "heading_1",
        "heading_2",
        "heading_3",
        "figure_caption",
        "table_caption",
        "reference",
        "appendix_heading",
    }
)
HEADING_LEVELS = {"heading_1": 1, "heading_2": 2, "heading_3": 3}
FIELD_SPACE = re.compile(r"\s+")
MANUAL_NUMBER = re.compile(
    r"^(?P<token>(?:第[一二三四五六七八九十百]+章|"
    r"\d+(?:\.\d+){1,2}|附录\s*[A-Z]|[图表]\s*\d+[.-]\d+))(?=\s|$)"
)


@dataclass(frozen=True, slots=True)
class SemanticParagraph:
    location: str
    raw_text: str
    style_id: str | None
    style_name: str | None
    role: str | None
    role_source: str | None
    repairable: bool
    manual_number_token: str | None
    fields: tuple[str, ...]
    relationship_identity: tuple[str, ...]
    bookmarks: tuple[str, ...]
    warnings: tuple[str, ...]
    part_name: str = "word/document.xml"

    @property
    def warning(self) -> str | None:
        return self.warnings[0] if self.warnings else None


@dataclass(frozen=True, slots=True)
class SemanticTable:
    location: str
    raw_text: str
    row_count: int
    column_count: int
    relationship_identity: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticSection:
    location: str
    start_paragraph: int
    header_relationship_ids: tuple[str, ...]
    footer_relationship_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticStyle:
    style_id: str
    name: str | None
    style_type: str | None


@dataclass(frozen=True, slots=True)
class SemanticNumbering:
    num_id: str
    abstract_num_id: str | None


@dataclass(frozen=True, slots=True)
class SemanticDocument:
    path: Path
    paragraphs: tuple[SemanticParagraph, ...]
    tables: tuple[SemanticTable, ...]
    sections: tuple[SemanticSection, ...]
    styles: tuple[SemanticStyle, ...]
    numbering: tuple[SemanticNumbering, ...]
    relationships: tuple[Relationship, ...]
    bookmarks: tuple[str, ...]
    headers: tuple[SemanticParagraph, ...]
    footers: tuple[SemanticParagraph, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Evidence:
    role: str
    source: str


@dataclass(frozen=True, slots=True)
class _StyleMetadata:
    name: str | None
    based_on: str | None
    outline_level: int | None


def _text(element: etree._Element) -> str:
    text: list[str] = []
    for descendant in element.iter():
        local_name = etree.QName(descendant).localname
        if local_name == "t" and descendant.text:
            text.append(descendant.text)
        elif local_name in {"br", "cr"}:
            text.append("\n")
        elif local_name == "tab":
            text.append("\t")
    return "".join(text)


def _fields(element: etree._Element) -> tuple[str, ...]:
    values: list[str] = []
    complex_fields: list[dict[str, object]] = []

    def append_instruction(instruction: str) -> None:
        normalized = FIELD_SPACE.sub(" ", instruction).strip()
        if normalized:
            values.append(normalized)

    for descendant in element.iter():
        if descendant.tag == W_FLD_SIMPLE:
            instruction = descendant.get(W_INSTR)
            if instruction:
                append_instruction(instruction)
        elif descendant.tag == W_FLD_CHAR:
            field_type = descendant.get(W_FLD_CHAR_TYPE)
            if field_type == "begin":
                complex_fields.append(
                    {"parts": [], "collecting": True, "emitted": False}
                )
            elif field_type == "separate" and complex_fields:
                current = complex_fields[-1]
                if not current["emitted"]:
                    append_instruction("".join(current["parts"]))
                    current["emitted"] = True
                current["collecting"] = False
            elif field_type == "end" and complex_fields:
                current = complex_fields.pop()
                if not current["emitted"]:
                    append_instruction("".join(current["parts"]))
        elif (
            descendant.tag == W_INSTR_TEXT
            and complex_fields
            and complex_fields[-1]["collecting"]
            and descendant.text
        ):
            complex_fields[-1]["parts"].append(descendant.text)

    for current in complex_fields:
        if not current["emitted"]:
            append_instruction("".join(current["parts"]))
    return tuple(values)


def _bookmarks(element: etree._Element) -> tuple[str, ...]:
    return tuple(
        name
        for name in element.xpath(".//w:bookmarkStart/@w:name", namespaces=NS)
        if not name.startswith("_")
    )


def _style_id(element: etree._Element) -> str | None:
    values = element.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return values[0] if values else None


def _style_metadata(package: OoxmlPackage) -> dict[str, _StyleMetadata]:
    if "word/styles.xml" not in package.parts:
        return {}
    result: dict[str, _StyleMetadata] = {}
    for style in package.xml("word/styles.xml").xpath(".//w:style", namespaces=NS):
        style_id = style.get(f"{{{W_NS}}}styleId")
        if not style_id:
            continue
        names = style.xpath("./w:name/@w:val", namespaces=NS)
        based_on = style.xpath("./w:basedOn/@w:val", namespaces=NS)
        outline_levels = style.xpath(
            "./w:pPr/w:outlineLvl/@w:val", namespaces=NS
        )
        try:
            outline_level = (
                int(outline_levels[0]) if outline_levels else None
            )
        except ValueError:
            outline_level = None
        result[style_id] = _StyleMetadata(
            name=names[0] if names else None,
            based_on=based_on[0] if based_on else None,
            outline_level=outline_level,
        )
    return result


def _style_map(package: OoxmlPackage) -> dict[str, str | None]:
    return {
        style_id: metadata.name
        for style_id, metadata in _style_metadata(package).items()
    }


def _style_chain(
    style_id: str | None,
    styles: dict[str, _StyleMetadata],
) -> tuple[str, ...]:
    result: list[str] = []
    current = style_id
    while current and current not in result:
        result.append(current)
        metadata = styles.get(current)
        current = metadata.based_on if metadata else None
    return tuple(result)


def _relationship_map(
    relationships: Iterable[Relationship], source_part: str = "word/document.xml"
) -> dict[str, Relationship]:
    return {
        relationship.id: relationship
        for relationship in relationships
        if relationship.source_part == source_part
    }


def _element_relationships(
    element: etree._Element, by_id: dict[str, Relationship]
) -> tuple[str, ...]:
    identities: list[str] = []
    for descendant in element.iter():
        for attribute, value in descendant.attrib.items():
            if attribute in R_ATTRIBUTES and value in by_id:
                identity = by_id[value].identity
                if identity not in identities:
                    identities.append(identity)
    return tuple(identities)


def _compile_pattern(pattern: TextPattern) -> re.Pattern[str]:
    flags = 0
    if "ignore_case" in pattern.flags:
        flags |= re.IGNORECASE
    if "unicode" in pattern.flags:
        flags |= re.UNICODE
    return re.compile(pattern.pattern, flags)


def _mapped_style_role(
    style_id: str | None,
    style_name: str | None,
    profile: FormatProfile,
) -> str | None:
    if style_id is None and style_name is None:
        return None
    for role, style in profile.styles.items():
        if style_id in style.word_styles or style_name in style.word_styles:
            return role
    return None


def _resolved_style_role(
    style_id: str | None,
    styles: dict[str, _StyleMetadata],
    profile: FormatProfile,
) -> str | None:
    for candidate_id in _style_chain(style_id, styles):
        metadata = styles.get(candidate_id)
        role = _mapped_style_role(
            candidate_id,
            metadata.name if metadata else None,
            profile,
        )
        if role is not None:
            return role
    return None


def _outline_role(
    element: etree._Element,
    style_id: str | None,
    styles: dict[str, _StyleMetadata],
) -> str | None:
    values = element.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=NS)
    level: int | None = None
    if values:
        try:
            level = int(values[0])
        except ValueError:
            return None
    else:
        for candidate_id in _style_chain(style_id, styles):
            metadata = styles.get(candidate_id)
            if metadata and metadata.outline_level is not None:
                level = metadata.outline_level
                break
    return {0: "heading_1", 1: "heading_2", 2: "heading_3"}.get(level)


def _numbering_level_map(
    package: OoxmlPackage,
) -> dict[tuple[str, int], tuple[str | None, str | None]]:
    if "word/numbering.xml" not in package.parts:
        return {}
    root = package.xml("word/numbering.xml")
    abstract_by_num: dict[str, str] = {}
    for numbering in root.xpath("./w:num", namespaces=NS):
        num_id = numbering.get(f"{{{W_NS}}}numId")
        abstract_ids = numbering.xpath(
            "./w:abstractNumId/@w:val", namespaces=NS
        )
        if num_id and abstract_ids:
            abstract_by_num[num_id] = abstract_ids[0]

    result: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    for abstract in root.xpath("./w:abstractNum", namespaces=NS):
        abstract_id = abstract.get(f"{{{W_NS}}}abstractNumId")
        if not abstract_id:
            continue
        num_ids = [
            num_id
            for num_id, candidate_id in abstract_by_num.items()
            if candidate_id == abstract_id
        ]
        for level in abstract.xpath("./w:lvl", namespaces=NS):
            raw_level = level.get(f"{{{W_NS}}}ilvl")
            if raw_level is None:
                continue
            try:
                level_index = int(raw_level)
            except ValueError:
                continue
            style_ids = level.xpath("./w:pStyle/@w:val", namespaces=NS)
            formats = level.xpath("./w:numFmt/@w:val", namespaces=NS)
            for num_id in num_ids:
                result[(num_id, level_index)] = (
                    style_ids[0] if style_ids else None,
                    formats[0] if formats else None,
                )
    return result


def _bookmark_roles(bookmarks: tuple[str, ...]) -> set[str]:
    normalized = {
        bookmark.removeprefix("thesis-role-")
        .removeprefix("role_")
        .removeprefix("role:")
        for bookmark in bookmarks
    }
    return normalized & AUTOMATIC_ROLES


def _field_roles(fields: tuple[str, ...]) -> set[str]:
    roles: set[str] = set()
    for field in fields:
        upper = field.upper()
        if re.search(r"\bSEQ\s+(FIGURE|图)\b", upper):
            roles.add("figure_caption")
        if re.search(r"\bSEQ\s+(TABLE|表)\b", upper):
            roles.add("table_caption")
    return roles


def _numbering_details(
    element: etree._Element,
) -> tuple[str, int, str] | None:
    num_ids = element.xpath("./w:pPr/w:numPr/w:numId/@w:val", namespaces=NS)
    if not num_ids or num_ids[0] == "0":
        return None
    levels = element.xpath("./w:pPr/w:numPr/w:ilvl/@w:val", namespaces=NS)
    try:
        level = int(levels[0]) if levels else 0
    except ValueError:
        return None
    role = {0: "heading_1", 1: "heading_2", 2: "heading_3"}.get(level)
    return (num_ids[0], level, role) if role is not None else None


def _explicit_role(
    element: etree._Element,
    fields: tuple[str, ...],
    bookmarks: tuple[str, ...],
    *,
    style_role: str | None,
    outline_role: str | None,
    pattern_roles: set[str],
    numbering_levels: dict[tuple[str, int], tuple[str | None, str | None]],
    styles: dict[str, _StyleMetadata],
    profile: FormatProfile,
) -> tuple[str | None, bool]:
    candidates = _field_roles(fields) | _bookmark_roles(bookmarks)
    numbering = _numbering_details(element)
    if numbering is not None:
        num_id, level, numbering_role = numbering
        numbering_level = numbering_levels.get((num_id, level))
        numbering_style_id = numbering_level[0] if numbering_level else None
        numbering_format = numbering_level[1] if numbering_level else None
        numbering_style_role = _resolved_style_role(
            numbering_style_id,
            styles,
            profile,
        )
        corroborating_roles = {
            role
            for role in (
                style_role,
                outline_role,
                numbering_style_role,
            )
            if role is not None
        } | pattern_roles
        if (
            numbering_format not in {None, "bullet", "none"}
            and numbering_role in corroborating_roles
        ):
            candidates.add(numbering_role)
    if len(candidates) > 1:
        return None, True
    return (next(iter(candidates)), False) if candidates else (None, False)


def _pattern_roles(text: str, profile: FormatProfile) -> set[str]:
    matches: list[tuple[int, str]] = []
    for role, patterns in profile.role_detection.text_patterns.items():
        if role not in AUTOMATIC_ROLES:
            continue
        for pattern in patterns:
            if _compile_pattern(pattern).fullmatch(text):
                matches.append((pattern.priority, role))
    if not matches:
        return set()
    highest_priority = max(priority for priority, _ in matches)
    return {
        role for priority, role in matches if priority == highest_priority
    }


def _manual_number(text: str) -> str | None:
    match = MANUAL_NUMBER.match(text)
    return match.group("token") if match else None


def _region_for(index: int, markers: dict[str, int | None]) -> str:
    appendix = markers["appendix"]
    references = markers["references"]
    body = markers["body"]
    if appendix is not None and index > appendix:
        return "appendix"
    if references is not None and index > references and (
        appendix is None or index < appendix
    ):
        return "references"
    if body is not None and index >= body:
        return "body"
    return "front_matter"


def _position_role(
    *,
    region: str,
    text: str,
    regional_index: int,
    profile: FormatProfile,
) -> str | None:
    candidates: set[str] = set()
    for role, constraints in profile.role_detection.position_constraints.items():
        if role not in AUTOMATIC_ROLES:
            continue
        for constraint in constraints:
            if constraint.section not in {region, "any"}:
                continue
            if regional_index < constraint.min_index:
                continue
            if (
                constraint.max_index is not None
                and regional_index > constraint.max_index
            ):
                continue
            if role == "reference" and region == "references" and text.strip():
                candidates.add(role)
            # Position alone is intentionally not enough to turn front-matter
            # prose into a heading. References are safe only after the
            # reference heading has established a recognized section.
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _marker_positions(
    elements: tuple[etree._Element, ...],
    style_names: dict[str, str | None],
    profile: FormatProfile,
) -> dict[str, int | None]:
    markers: dict[str, int | None] = {
        "body": None,
        "references": None,
        "appendix": None,
    }
    for index, element in enumerate(elements, start=1):
        text = _text(element).strip()
        style_id = _style_id(element)
        mapped = _mapped_style_role(
            style_id, style_names.get(style_id) if style_id else None, profile
        )
        patterns = _pattern_roles(text, profile)
        if markers["body"] is None and (
            mapped == "heading_1" or "heading_1" in patterns
        ):
            markers["body"] = index
        if markers["references"] is None and text == "参考文献":
            markers["references"] = index
        if markers["appendix"] is None and (
            mapped == "appendix_heading" or "appendix_heading" in patterns
        ):
            markers["appendix"] = index
    return markers


def _resolve_paragraphs(
    elements: tuple[etree._Element, ...],
    package: OoxmlPackage,
    profile: FormatProfile,
) -> tuple[SemanticParagraph, ...]:
    style_metadata = _style_metadata(package)
    styles = {
        style_id: metadata.name
        for style_id, metadata in style_metadata.items()
    }
    numbering_levels = _numbering_level_map(package)
    relationships = package.relationships()
    relationship_by_id = _relationship_map(relationships)
    markers = _marker_positions(elements, styles, profile)
    result: list[SemanticParagraph] = []
    seen_heading_level = 0
    regional_counts: dict[str, int] = {}

    for index, element in enumerate(elements, start=1):
        raw_text = _text(element)
        text = raw_text.strip()
        style_id = _style_id(element)
        style_name = styles.get(style_id) if style_id else None
        fields = _fields(element)
        bookmarks = _bookmarks(element)
        evidence: list[_Evidence] = []
        warnings: list[str] = []

        style_role = _resolved_style_role(
            style_id,
            style_metadata,
            profile,
        )
        if style_role in AUTOMATIC_ROLES:
            evidence.append(_Evidence(style_role, "word_style"))

        pattern_roles = _pattern_roles(text, profile)
        explicit_role, explicit_conflict = _explicit_role(
            element,
            fields,
            bookmarks,
            style_role=style_role,
            outline_role=_outline_role(
                element,
                style_id,
                style_metadata,
            ),
            pattern_roles=pattern_roles,
            numbering_levels=numbering_levels,
            styles=style_metadata,
            profile=profile,
        )
        if explicit_conflict:
            warnings.append("ROLE.CONFLICT")
        elif explicit_role:
            evidence.append(_Evidence(explicit_role, "explicit_structure"))

        if len(pattern_roles) > 1:
            warnings.append("ROLE.AMBIGUOUS")
        elif pattern_roles:
            pattern_role = next(iter(pattern_roles))
            region = _region_for(index, markers)
            if pattern_role != "reference" or region == "references":
                evidence.append(_Evidence(pattern_role, "text_pattern"))

        region = _region_for(index, markers)
        regional_index = regional_counts.get(region, 0)
        regional_counts[region] = regional_index + 1
        position_role = _position_role(
            region=region,
            text=text,
            regional_index=regional_index,
            profile=profile,
        )
        if position_role:
            evidence.append(_Evidence(position_role, "document_position"))

        roles = {item.role for item in evidence}
        if len(roles) > 1 or explicit_conflict:
            role = None
            source = None
            repairable = False
            warnings = ["ROLE.CONFLICT"]
        elif len(roles) == 1:
            role = next(iter(roles))
            source = next(item.source for item in evidence if item.role == role)
            repairable = True
        else:
            role = None
            source = None
            repairable = False
            if text and not warnings:
                warnings.append("ROLE.AMBIGUOUS")

        level = HEADING_LEVELS.get(role or "")
        if level is not None:
            if level > seen_heading_level + 1:
                repairable = False
                warnings.append("ROLE.SKIPPED_HEADING_LEVEL")
            if level == 1:
                seen_heading_level = 1
            elif level <= seen_heading_level + 1:
                seen_heading_level = level

        result.append(
            SemanticParagraph(
                location=f"paragraph:{index}",
                raw_text=raw_text,
                style_id=style_id,
                style_name=style_name,
                role=role,
                role_source=source,
                repairable=repairable,
                manual_number_token=_manual_number(text),
                fields=fields,
                relationship_identity=_element_relationships(
                    element, relationship_by_id
                ),
                bookmarks=bookmarks,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        )
    return tuple(result)


def _tables(
    document_root: etree._Element,
    relationships: tuple[Relationship, ...],
) -> tuple[SemanticTable, ...]:
    by_id = _relationship_map(relationships)
    result: list[SemanticTable] = []
    for index, table in enumerate(
        document_root.xpath("./w:body//w:tbl", namespaces=NS), start=1
    ):
        rows = table.xpath("./w:tr", namespaces=NS)
        columns = max(
            (len(row.xpath("./w:tc", namespaces=NS)) for row in rows),
            default=0,
        )
        row_texts = [
            "\t".join(_text(cell) for cell in row.xpath("./w:tc", namespaces=NS))
            for row in rows
        ]
        result.append(
            SemanticTable(
                location=f"table:{index}",
                raw_text="\n".join(row_texts),
                row_count=len(rows),
                column_count=columns,
                relationship_identity=_element_relationships(table, by_id),
            )
        )
    return tuple(result)


def _sections(document_root: etree._Element) -> tuple[SemanticSection, ...]:
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        return ()
    result: list[SemanticSection] = []
    paragraph_index = 0
    current_section_start = 1
    for element in body.iterchildren():
        if element.tag == f"{{{W_NS}}}p":
            paragraph_index += 1
            section_properties = element.find("./w:pPr/w:sectPr", namespaces=NS)
        elif element.tag == f"{{{W_NS}}}sectPr":
            section_properties = element
        else:
            section_properties = None
        if section_properties is None:
            continue
        result.append(
            SemanticSection(
                location=f"section:{len(result) + 1}",
                start_paragraph=current_section_start,
                header_relationship_ids=tuple(
                    section_properties.xpath(
                        "./w:headerReference/@r:id", namespaces=NS
                    )
                ),
                footer_relationship_ids=tuple(
                    section_properties.xpath(
                        "./w:footerReference/@r:id", namespaces=NS
                    )
                ),
            )
        )
        if element.tag == f"{{{W_NS}}}p":
            current_section_start = paragraph_index + 1
    return tuple(result)


def _styles(package: OoxmlPackage) -> tuple[SemanticStyle, ...]:
    if "word/styles.xml" not in package.parts:
        return ()
    values: list[SemanticStyle] = []
    for style in package.xml("word/styles.xml").xpath("./w:style", namespaces=NS):
        style_id = style.get(f"{{{W_NS}}}styleId")
        if not style_id:
            continue
        names = style.xpath("./w:name/@w:val", namespaces=NS)
        values.append(
            SemanticStyle(
                style_id=style_id,
                name=names[0] if names else None,
                style_type=style.get(f"{{{W_NS}}}type"),
            )
        )
    return tuple(values)


def _numbering(package: OoxmlPackage) -> tuple[SemanticNumbering, ...]:
    if "word/numbering.xml" not in package.parts:
        return ()
    values: list[SemanticNumbering] = []
    for num in package.xml("word/numbering.xml").xpath("./w:num", namespaces=NS):
        num_id = num.get(f"{{{W_NS}}}numId")
        if not num_id:
            continue
        abstracts = num.xpath("./w:abstractNumId/@w:val", namespaces=NS)
        values.append(
            SemanticNumbering(
                num_id=num_id,
                abstract_num_id=abstracts[0] if abstracts else None,
            )
        )
    return tuple(values)


def _story_paragraphs(
    package: OoxmlPackage,
    relationship_kind: str,
    profile: FormatProfile,
) -> tuple[SemanticParagraph, ...]:
    result: list[SemanticParagraph] = []
    style_names = _style_map(package)
    relationships = package.relationships()
    related_parts = sorted(
        package.related_parts("word/document.xml", relationship_kind),
        key=lambda item: item[1],
    )
    for _, part_name in related_parts:
        root = package.xml(part_name)
        elements = tuple(root.xpath(".//w:p", namespaces=NS))
        relationship_by_id = _relationship_map(relationships, part_name)
        for paragraph_index, element in enumerate(elements, start=1):
            fields = _fields(element)
            style_id = _style_id(element)
            result.append(
                SemanticParagraph(
                    location=f"part:{part_name}#paragraph:{paragraph_index}",
                    raw_text=_text(element),
                    style_id=style_id,
                    style_name=style_names.get(style_id) if style_id else None,
                    role=None,
                    role_source=None,
                    repairable=False,
                    manual_number_token=_manual_number(_text(element).strip()),
                    fields=fields,
                    relationship_identity=_element_relationships(
                        element, relationship_by_id
                    ),
                    bookmarks=_bookmarks(element),
                    warnings=(),
                    part_name=part_name,
                )
            )
    return tuple(result)


def inspect_document(
    path: str | Path, profile: FormatProfile
) -> SemanticDocument:
    """Inspect a DOCX without mutating it or guessing unsupported semantics."""

    package = OoxmlPackage.open(path)
    document_root = package.xml("word/document.xml")
    body = document_root.find("w:body", namespaces=NS)
    if body is None:
        from thesis_format.ooxml import OoxmlError

        raise OoxmlError("word/document.xml has no w:body")
    paragraph_elements = tuple(body.xpath(".//w:p", namespaces=NS))
    paragraphs = _resolve_paragraphs(paragraph_elements, package, profile)
    relationships = package.relationships()
    headers = _story_paragraphs(package, "header", profile)
    footers = _story_paragraphs(package, "footer", profile)
    bookmarks = tuple(
        dict.fromkeys(
            bookmark
            for node in (*paragraphs, *headers, *footers)
            for bookmark in node.bookmarks
        )
    )
    warnings = tuple(
        dict.fromkeys(
            warning for node in paragraphs for warning in node.warnings
        )
    )
    return SemanticDocument(
        path=Path(path),
        paragraphs=paragraphs,
        tables=_tables(document_root, relationships),
        sections=_sections(document_root),
        styles=_styles(package),
        numbering=_numbering(package),
        relationships=relationships,
        bookmarks=bookmarks,
        headers=headers,
        footers=footers,
        warnings=warnings,
    )
