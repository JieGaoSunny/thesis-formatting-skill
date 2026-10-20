"""Extract deterministic substantive-content snapshots from DOCX packages."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from lxml import etree

from thesis_format.contracts import (
    canonical_sha256,
    shortest_unique_digest_prefixes,
    stable_id,
    validate_content_snapshot,
)
from thesis_format.ooxml import OoxmlPackage, Relationship, resolve_relationship_target
from thesis_format.profile import FormatProfile
from thesis_format.snapshot.normalize import normalize_text, strip_manual_numbering


SCHEMA_VERSION = "1.0"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W_NS, "r": R_NS, "wp": WP_NS, "a": A_NS, "m": M_NS}
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
EXCLUDED_FIELDS = frozenset(
    {"TOC", "PAGE", "PAGEREF", "REF", "SEQ", "STYLEREF"}
)
OBJECT_MARKER = "\ufffc"


def _field_name(instruction: str) -> str:
    match = re.match(r"\s*([A-Za-z]+)", instruction)
    return match.group(1).upper() if match else ""


def _paragraph_text(
    paragraph: etree._Element,
    *,
    exclude_results: bool,
    stop_before: etree._Element | None = None,
) -> str:
    pieces: list[str] = []
    stack: list[dict[str, object]] = []
    for descendant in paragraph.iter():
        if descendant is stop_before:
            break
        local = etree.QName(descendant).localname
        if local == "fldSimple":
            continue
        if local == "fldChar":
            field_type = descendant.get(f"{W}fldCharType")
            if field_type == "begin":
                stack.append({"instruction": "", "result": False, "exclude": False})
            elif field_type == "separate" and stack:
                instruction = str(stack[-1]["instruction"])
                stack[-1]["result"] = True
                stack[-1]["exclude"] = _field_name(instruction) in EXCLUDED_FIELDS
            elif field_type == "end" and stack:
                stack.pop()
        elif local == "instrText" and stack and descendant.text:
            stack[-1]["instruction"] = str(stack[-1]["instruction"]) + descendant.text
        elif (
            local == "t"
            and etree.QName(descendant).namespace == W_NS
            and descendant.text
        ):
            simple = next(
                (
                    ancestor
                    for ancestor in descendant.iterancestors()
                    if etree.QName(ancestor).localname == "fldSimple"
                ),
                None,
            )
            simple_excluded = (
                simple is not None
                and _field_name(simple.get(f"{W}instr", "")) in EXCLUDED_FIELDS
            )
            complex_excluded = bool(
                stack and stack[-1]["result"] and stack[-1]["exclude"]
            )
            if not exclude_results or not (simple_excluded or complex_excluded):
                pieces.append(descendant.text)
        elif local in {"tab", "br", "cr"}:
            pieces.append(" ")
    return normalize_text("".join(pieces))


def _style_role(
    paragraph: etree._Element, text: str, profile: FormatProfile
) -> str | None:
    style_ids = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    style_id = style_ids[0] if style_ids else None
    for role, style in profile.styles.items():
        if style_id in style.word_styles:
            return role
    matches: list[tuple[int, str]] = []
    for role, patterns in profile.role_detection.text_patterns.items():
        for pattern in patterns:
            flags = re.IGNORECASE if "ignore_case" in pattern.flags else 0
            if re.fullmatch(pattern.pattern, text, flags):
                matches.append((pattern.priority, role))
    if not matches:
        return None
    priority = max(item[0] for item in matches)
    roles = {role for candidate, role in matches if candidate == priority}
    return next(iter(roles)) if len(roles) == 1 else None


def _field_role(paragraph: etree._Element) -> str | None:
    instructions = " ".join(
        paragraph.xpath(".//w:instrText/text()", namespaces=NS)
        + paragraph.xpath(".//w:fldSimple/@w:instr", namespaces=NS)
    )
    upper = instructions.upper()
    if re.search(r"\bSEQ\s+(?:FIGURE|图)\b", upper):
        return "figure_caption"
    if re.search(r"\bSEQ\s+(?:TABLE|表)\b", upper):
        return "table_caption"
    return None


def _clean_paragraph(paragraph: etree._Element, profile: FormatProfile) -> str:
    visible = _paragraph_text(paragraph, exclude_results=False)
    filtered = _paragraph_text(paragraph, exclude_results=True)
    return _clean_paragraph_text(paragraph, visible, filtered, profile)


def _clean_paragraph_text(
    paragraph: etree._Element,
    visible: str,
    filtered: str,
    profile: FormatProfile,
) -> str:
    role = _paragraph_role(paragraph, visible, profile)
    cleaned = strip_manual_numbering(filtered, role, profile, evidence_text=visible)
    if role == "figure_caption" and cleaned.startswith("图 "):
        cleaned = normalize_text(cleaned[1:])
    if role == "table_caption" and cleaned.startswith("表 "):
        cleaned = normalize_text(cleaned[1:])
    return cleaned


def _paragraph_role(
    paragraph: etree._Element,
    visible_text: str,
    profile: FormatProfile,
) -> str | None:
    return _field_role(paragraph) or _style_role(
        paragraph, visible_text, profile
    )


def _relationship_map(
    relationships: Iterable[Relationship], source_part: str
) -> dict[str, Relationship]:
    return {
        relationship.id: relationship
        for relationship in relationships
        if relationship.source_part == source_part
    }


def _relationship_hash(
    package: OoxmlPackage,
    relationship: Relationship,
) -> str:
    if relationship.target_mode == "External":
        return hashlib.sha256(relationship.identity.encode("utf-8")).hexdigest()
    target = resolve_relationship_target(
        relationship.source_part, relationship.target
    )
    return hashlib.sha256(package.parts[target]).hexdigest()


def _location(
    part: str,
    path: str,
    index: int,
    *,
    character_offset: int | None = None,
    same_offset_ordinal: int | None = None,
) -> dict[str, object]:
    location: dict[str, object] = {"part": part, "path": path, "index": index}
    if character_offset is not None:
        location["character_offset"] = character_offset
    if same_offset_ordinal is not None:
        location["same_offset_ordinal"] = same_offset_ordinal
    return location


def _candidate(
    node_type: str,
    text: str,
    part: str,
    path: str,
    index: int,
    relationship_hash: str | None = None,
    *,
    note_id: str | None = None,
    note_type: str | None = None,
    table_geometry: dict[str, object] | None = None,
    character_offset: int | None = None,
    same_offset_ordinal: int | None = None,
) -> dict[str, object]:
    candidate: dict[str, object] = {
        "node_type": node_type,
        "source_location": _location(
            part,
            path,
            index,
            character_offset=character_offset,
            same_offset_ordinal=same_offset_ordinal,
        ),
        "normalized_text": text,
        "relationship_hash": relationship_hash,
    }
    if note_id is not None:
        candidate["note_id"] = note_id
    if note_type is not None:
        candidate["note_type"] = note_type
    if table_geometry is not None:
        candidate["table_geometry"] = table_geometry
    return candidate


@dataclass
class _ObjectIdentities:
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def identity(self, content_hash: str, story: str, node_type: str) -> str:
        key = (story, node_type)
        self.counts[key] += 1
        return canonical_sha256([content_hash, story, self.counts[key]])


def _images(
    element: etree._Element,
    package: OoxmlPackage,
    part: str,
    base_path: str,
    source_index: int,
    story: str,
    object_identities: _ObjectIdentities,
    *,
    exclude_nested_tables: bool = False,
    note_id: str | None = None,
    note_type: str | None = None,
) -> list[dict[str, object]]:
    relationships = _relationship_map(package.relationships(), part)
    result: list[dict[str, object]] = []
    drawings = [
        drawing
        for drawing in element.xpath(".//w:drawing", namespaces=NS)
        if not exclude_nested_tables or _belongs_to_container(drawing, element)
    ]
    for drawing_index, drawing in enumerate(drawings, start=1):
        doc_properties = drawing.xpath(".//wp:docPr", namespaces=NS)
        alt = ""
        if doc_properties:
            alt = (
                doc_properties[0].get("descr")
                or doc_properties[0].get("title")
                or ""
            )
        relationship_ids = drawing.xpath(
            ".//a:blip/@r:embed | .//a:blip/@r:link", namespaces=NS
        )
        hashes = [
            _relationship_hash(package, relationships[relationship_id])
            for relationship_id in relationship_ids
            if relationship_id in relationships
        ]
        if len(hashes) > 1:
            content_hash = canonical_sha256(hashes)
        elif hashes:
            content_hash = hashes[0]
        else:
            content_hash = hashlib.sha256(
                etree.tostring(drawing, method="c14n", with_comments=False)
            ).hexdigest()
        relationship_hash = object_identities.identity(
            content_hash, story, "image"
        )
        result.append(
            _candidate(
                "image",
                normalize_text(alt),
                part,
                f"{base_path}/w:drawing[{drawing_index}]",
                source_index + len(result),
                relationship_hash,
                note_id=note_id,
                note_type=note_type,
            )
        )
    return result


def _equations(
    element: etree._Element,
    part: str,
    base_path: str,
    source_index: int,
    *,
    exclude_nested_tables: bool = False,
    note_id: str | None = None,
    note_type: str | None = None,
) -> list[dict[str, object]]:
    equations = [
        equation
        for equation in element.xpath(
            ".//m:oMathPara | .//m:oMath[not(ancestor::m:oMathPara)]",
            namespaces=NS,
        )
        if not exclude_nested_tables or _belongs_to_container(equation, element)
    ]
    result: list[dict[str, object]] = []
    for equation_index, equation in enumerate(equations, start=1):
        text = normalize_text("".join(equation.xpath(".//m:t/text()", namespaces=NS)))
        result.append(
            _candidate(
                "equation",
                text,
                part,
                f"{base_path}/m:equation[{equation_index}]",
                source_index + len(result),
                note_id=note_id,
                note_type=note_type,
            )
        )
    return result


def _note_references(
    element: etree._Element,
    part: str,
    base_path: str,
    source_index: int,
    profile: FormatProfile,
    *,
    exclude_nested_tables: bool = False,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    offset_counts: Counter[tuple[int, int]] = Counter()
    for descendant in element.iter():
        local = etree.QName(descendant).localname
        if local not in {"footnoteReference", "endnoteReference"}:
            continue
        if exclude_nested_tables and not _belongs_to_container(descendant, element):
            continue
        kind = local.removesuffix("Reference")
        note_id = descendant.get(f"{W}id", "")
        paragraph = next(
            (
                ancestor
                for ancestor in descendant.iterancestors()
                if etree.QName(ancestor).localname == "p"
            ),
            None,
        )
        if paragraph is None:
            character_offset = 0
            paragraph_key = id(element)
        else:
            visible = _paragraph_text(paragraph, exclude_results=False)
            filtered_prefix = _paragraph_text(
                paragraph,
                exclude_results=True,
                stop_before=descendant,
            )
            character_offset = len(
                _clean_paragraph_text(
                    paragraph,
                    visible,
                    filtered_prefix,
                    profile,
                )
            )
            paragraph_key = id(paragraph)
        offset_key = (paragraph_key, character_offset)
        offset_counts[offset_key] += 1
        counts[kind] += 1
        result.append(
            _candidate(
                f"{kind}_reference",
                "",
                part,
                f"{base_path}/w:{local}[{counts[kind]}]",
                source_index + len(result),
                note_id=note_id,
                note_type=kind,
                character_offset=character_offset,
                same_offset_ordinal=offset_counts[offset_key],
            )
        )
    return result


def _belongs_to_container(
    descendant: etree._Element,
    container: etree._Element,
) -> bool:
    for ancestor in descendant.iterancestors():
        if ancestor is container:
            return True
        if etree.QName(ancestor).localname == "tbl":
            return False
    return False


def _story_blocks(
    container: etree._Element,
    base_path: str,
) -> Iterable[tuple[etree._Element, str]]:
    sibling_counts: Counter[str] = Counter()
    for child in container:
        qname = etree.QName(child)
        sibling_counts[child.tag] += 1
        prefix = child.prefix
        if prefix is None:
            prefix = next(
                (
                    candidate
                    for candidate, namespace in NS.items()
                    if namespace == qname.namespace
                ),
                "ns",
            )
        child_path = (
            f"{base_path}/{prefix}:{qname.localname}"
            f"[{sibling_counts[child.tag]}]"
        )
        if qname.localname in {"p", "tbl"} and qname.namespace == W_NS:
            yield child, child_path
        else:
            yield from _story_blocks(child, child_path)


def _cell_text(cell: etree._Element, profile: FormatProfile) -> str:
    pieces: list[str] = []
    for child, _ in _story_blocks(cell, ""):
        local = etree.QName(child).localname
        if local == "p":
            text = _clean_paragraph(child, profile)
            if text:
                pieces.append(text)
        elif local == "tbl":
            pieces.append(OBJECT_MARKER)
    return normalize_text(" ".join(pieces))


def _table_cells(
    table: etree._Element,
    profile: FormatProfile,
) -> tuple[list[tuple[etree._Element, str, dict[str, object]]], dict[str, object]]:
    rows = table.xpath("./w:tr", namespaces=NS)
    parsed: list[tuple[etree._Element, str, dict[str, object]]] = []
    grid_column_count = len(table.xpath("./w:tblGrid/w:gridCol", namespaces=NS))
    column_count = grid_column_count
    for row_index, row in enumerate(rows, start=1):
        grid_before = row.xpath("./w:trPr/w:gridBefore/@w:val", namespaces=NS)
        grid_after = row.xpath("./w:trPr/w:gridAfter/@w:val", namespaces=NS)
        column = (int(grid_before[0]) if grid_before else 0) + 1
        for cell in row.xpath("./w:tc", namespaces=NS):
            span_values = cell.xpath("./w:tcPr/w:gridSpan/@w:val", namespaces=NS)
            grid_span = int(span_values[0]) if span_values else 1
            merge_nodes = cell.xpath("./w:tcPr/w:vMerge", namespaces=NS)
            v_merge: str | None = None
            if merge_nodes:
                v_merge = merge_nodes[0].get(f"{W}val") or "continue"
            text = _cell_text(cell, profile)
            geometry = {
                "row_count": len(rows),
                "column_count": 0,
                "row": row_index,
                "column": column,
                "grid_span": grid_span,
                "v_merge": v_merge,
            }
            parsed.append((cell, text, geometry))
            column += grid_span
        column_count = max(
            column_count,
            column - 1 + (int(grid_after[0]) if grid_after else 0),
        )
    for _, _, geometry in parsed:
        geometry["column_count"] = column_count
    signature = {
        "row_count": len(rows),
        "column_count": column_count,
        "cells": [
            {
                "row": geometry["row"],
                "column": geometry["column"],
                "grid_span": geometry["grid_span"],
                "v_merge": geometry["v_merge"],
                "text": text,
            }
            for _, text, geometry in parsed
        ],
    }
    return parsed, signature


def _append_table_nodes(
    result: list[dict[str, object]],
    table: etree._Element,
    package: OoxmlPackage,
    profile: FormatProfile,
    object_identities: _ObjectIdentities,
    *,
    part: str,
    table_path: str,
    story: str,
    index_offset: int = 0,
    note_id: str | None = None,
    note_type: str | None = None,
) -> None:
    cells, table_signature = _table_cells(table, profile)
    table_identity = object_identities.identity(
        canonical_sha256(table_signature), story, "table"
    )
    row_physical_columns: Counter[int] = Counter()
    for cell, text, geometry in cells:
        row_index = int(geometry["row"])
        row_physical_columns[row_index] += 1
        cell_path = (
            f"{table_path}/w:tr[{row_index}]"
            f"/w:tc[{row_physical_columns[row_index]}]"
        )
        result.append(
            _candidate(
                "table",
                text,
                part,
                cell_path,
                index_offset + len(result),
                table_identity,
                note_id=note_id,
                note_type=note_type,
                table_geometry=geometry,
            )
        )
        result.extend(
            _note_references(
                cell,
                part,
                cell_path,
                index_offset + len(result),
                profile,
                exclude_nested_tables=True,
            )
        )
        result.extend(
            _images(
                cell,
                package,
                part,
                cell_path,
                index_offset + len(result),
                story,
                object_identities,
                exclude_nested_tables=True,
                note_id=note_id,
                note_type=note_type,
            )
        )
        result.extend(
            _equations(
                cell,
                part,
                cell_path,
                index_offset + len(result),
                exclude_nested_tables=True,
                note_id=note_id,
                note_type=note_type,
            )
        )
        for nested_table, nested_path in _story_blocks(cell, cell_path):
            if etree.QName(nested_table).localname != "tbl":
                continue
            _append_table_nodes(
                result,
                nested_table,
                package,
                profile,
                object_identities,
                part=part,
                table_path=nested_path,
                story=story,
                index_offset=index_offset,
                note_id=note_id,
                note_type=note_type,
            )


def _story_nodes(
    package: OoxmlPackage,
    profile: FormatProfile,
    object_identities: _ObjectIdentities,
) -> list[dict[str, object]]:
    body = package.xml("word/document.xml").find("w:body", namespaces=NS)
    if body is None:
        return []
    result: list[dict[str, object]] = []
    source_index = 0
    for child, base_path in _story_blocks(body, "/w:document/w:body"):
        local = etree.QName(child).localname
        if local == "p":
            visible = _paragraph_text(child, exclude_results=False)
            role = _paragraph_role(child, visible, profile)
            text = _clean_paragraph(child, profile)
            if text:
                result.append(
                    _candidate(
                        "caption"
                        if role in {"figure_caption", "table_caption"}
                        else "paragraph",
                        text,
                        "word/document.xml",
                        base_path,
                        source_index,
                    )
                )
                source_index += 1
            references = _note_references(
                child,
                "word/document.xml",
                base_path,
                source_index,
                profile,
            )
            result.extend(references)
            source_index += len(references)
            images = _images(
                child,
                package,
                "word/document.xml",
                base_path,
                source_index,
                "body",
                object_identities,
            )
            result.extend(images)
            source_index += len(images)
            equations = _equations(
                child,
                "word/document.xml",
                base_path,
                source_index,
            )
            result.extend(equations)
            source_index += len(equations)
        elif local == "tbl":
            _append_table_nodes(
                result,
                child,
                package,
                profile,
                object_identities,
                part="word/document.xml",
                table_path=base_path,
                story="body",
            )
            source_index = len(result)
    return result


def _note_nodes(
    package: OoxmlPackage,
    profile: FormatProfile,
    kind: str,
    source_index: int,
    object_identities: _ObjectIdentities,
) -> list[dict[str, object]]:
    part = f"word/{kind}s.xml"
    if part not in package.parts:
        return []
    root = package.xml(part)
    notes = root.xpath(f"./w:{kind}", namespaces=NS)

    def note_key(note: etree._Element) -> tuple[int, int | str]:
        note_id = note.get(f"{W}id", "")
        try:
            return 0, int(note_id)
        except ValueError:
            return 1, note_id

    result: list[dict[str, object]] = []
    for note in sorted(notes, key=note_key):
        note_id = note.get(f"{W}id", "")
        try:
            if int(note_id) < 1:
                continue
        except ValueError:
            pass
        base_path = f"/w:{kind}s/w:{kind}[@w:id='{note_id}']"
        story = f"{kind}:{note_id}"
        for child, child_path in _story_blocks(note, base_path):
            local = etree.QName(child).localname
            if local == "p":
                text = _clean_paragraph(child, profile)
                if text:
                    result.append(
                        _candidate(
                            kind,
                            text,
                            part,
                            child_path,
                            source_index + len(result),
                            note_id=note_id,
                            note_type=kind,
                        )
                    )
                result.extend(
                    _images(
                        child,
                        package,
                        part,
                        child_path,
                        source_index + len(result),
                        story,
                        object_identities,
                        note_id=note_id,
                        note_type=kind,
                    )
                )
                result.extend(
                    _equations(
                        child,
                        part,
                        child_path,
                        source_index + len(result),
                        note_id=note_id,
                        note_type=kind,
                    )
                )
            elif local == "tbl":
                _append_table_nodes(
                    result,
                    child,
                    package,
                    profile,
                    object_identities,
                    part=part,
                    table_path=child_path,
                    story=story,
                    index_offset=source_index,
                    note_id=note_id,
                    note_type=kind,
                )
    return result


def _section_story_nodes(
    package: OoxmlPackage,
    profile: FormatProfile,
    kind: str,
    object_identities: _ObjectIdentities,
) -> list[dict[str, object]]:
    relationships = _relationship_map(package.relationships(), "word/document.xml")
    sections = package.xml("word/document.xml").xpath(
        ".//w:body/w:p/w:pPr/w:sectPr | .//w:body/w:sectPr", namespaces=NS
    )
    inherited: dict[str, str] = {}
    result: list[dict[str, object]] = []
    for section_index, section in enumerate(sections, start=1):
        for reference in section.xpath(f"./w:{kind}Reference", namespaces=NS):
            reference_type = reference.get(f"{W}type", "default")
            relationship_id = reference.get(f"{R}id")
            if relationship_id:
                inherited[reference_type] = relationship_id
        for reference_type in ("default", "first", "even"):
            relationship_id = inherited.get(reference_type)
            if relationship_id is None:
                continue
            relationship = relationships.get(relationship_id)
            if relationship is None or relationship.target_mode == "External":
                continue
            part = resolve_relationship_target(
                relationship.source_part, relationship.target
            )
            root = package.xml(part)
            story = f"{kind}:section:{section_index}:{reference_type}"
            story_path = (
                f"/section[{section_index}]/{kind}[{reference_type}]"
            )
            for child, base_path in _story_blocks(root, story_path):
                local = etree.QName(child).localname
                if local == "p":
                    text = _clean_paragraph(child, profile)
                    if text:
                        result.append(
                            _candidate(
                                kind,
                                text,
                                part,
                                base_path,
                                len(result),
                            )
                        )
                    result.extend(
                        _images(
                            child,
                            package,
                            part,
                            base_path,
                            len(result),
                            story,
                            object_identities,
                        )
                    )
                    equations = _equations(
                        child,
                        part,
                        base_path,
                        len(result),
                    )
                    result.extend(equations)
                elif local == "tbl":
                    _append_table_nodes(
                        result,
                        child,
                        package,
                        profile,
                        object_identities,
                        part=part,
                        table_path=base_path,
                        story=story,
                    )
    return result


def assign_node_ids(
    payloads: Iterable[object],
    *,
    digest_function: Callable[[object], str] = canonical_sha256,
) -> list[str]:
    """Assign shortest collision-free SHA prefixes to canonical node payloads."""

    digests = [digest_function(payload) for payload in payloads]
    return shortest_unique_digest_prefixes(digests)


def _assign_ids(collections: list[list[dict[str, object]]]) -> None:
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    payloads: list[list[object]] = []
    nodes = [node for collection in collections for node in collection]
    for node in nodes:
        key = (
            str(node["node_type"]),
            str(node["normalized_text"]),
            str(node.get("relationship_hash") or ""),
            str(node.get("note_id") or ""),
            str(node.get("note_type") or ""),
        )
        ordinal = counts[key]
        counts[key] += 1
        payloads.append(
            [
                SCHEMA_VERSION,
                key[0],
                key[1],
                key[2],
                key[3],
                key[4],
                ordinal,
            ]
        )
    for node, node_id in zip(nodes, assign_node_ids(payloads), strict=True):
        node["node_id"] = node_id


def extract_snapshot(
    path: str | Path, profile: FormatProfile
) -> dict[str, object]:
    """Extract and validate a Task 2 content snapshot from a DOCX file."""

    document_path = Path(path)
    package = OoxmlPackage.open(document_path)
    object_identities = _ObjectIdentities()
    body = _story_nodes(package, profile, object_identities)
    body.extend(
        _note_nodes(
            package,
            profile,
            "footnote",
            len(body),
            object_identities,
        )
    )
    body.extend(
        _note_nodes(
            package,
            profile,
            "endnote",
            len(body),
            object_identities,
        )
    )
    headers = _section_story_nodes(
        package, profile, "header", object_identities
    )
    footers = _section_story_nodes(
        package, profile, "footer", object_identities
    )
    _assign_ids([body, headers, footers])
    snapshot: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "document_sha256": hashlib.sha256(document_path.read_bytes()).hexdigest(),
        "body": body,
        "headers": headers,
        "footers": footers,
    }
    snapshot["snapshot_id"] = stable_id(snapshot)
    validate_content_snapshot(snapshot)
    return snapshot
