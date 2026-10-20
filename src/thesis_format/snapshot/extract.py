"""Extract deterministic substantive-content snapshots from DOCX packages."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
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
NS = {"w": W_NS, "r": R_NS, "wp": WP_NS, "a": A_NS}
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
EXCLUDED_FIELDS = frozenset(
    {"TOC", "PAGE", "PAGEREF", "REF", "SEQ", "STYLEREF"}
)


def _field_name(instruction: str) -> str:
    match = re.match(r"\s*([A-Za-z]+)", instruction)
    return match.group(1).upper() if match else ""


def _paragraph_text(paragraph: etree._Element, *, exclude_results: bool) -> str:
    pieces: list[str] = []
    stack: list[dict[str, object]] = []
    for descendant in paragraph.iter():
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
        elif local == "t" and descendant.text:
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
    role = _field_role(paragraph) or _style_role(paragraph, visible, profile)
    filtered = _paragraph_text(paragraph, exclude_results=True)
    cleaned = strip_manual_numbering(filtered, role, profile, evidence_text=visible)
    if role == "figure_caption" and cleaned.startswith("图 "):
        cleaned = normalize_text(cleaned[1:])
    if role == "table_caption" and cleaned.startswith("表 "):
        cleaned = normalize_text(cleaned[1:])
    return cleaned


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


def _location(part: str, path: str, index: int) -> dict[str, object]:
    return {"part": part, "path": path, "index": index}


def _candidate(
    node_type: str,
    text: str,
    part: str,
    path: str,
    index: int,
    relationship_hash: str | None = None,
) -> dict[str, object]:
    return {
        "node_type": node_type,
        "source_location": _location(part, path, index),
        "normalized_text": text,
        "relationship_hash": relationship_hash,
    }


def _images(
    element: etree._Element,
    package: OoxmlPackage,
    part: str,
    base_path: str,
    source_index: int,
) -> list[dict[str, object]]:
    relationships = _relationship_map(package.relationships(), part)
    result: list[dict[str, object]] = []
    drawings = element.xpath(".//w:drawing", namespaces=NS)
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
        relationship_hash = canonical_sha256(hashes) if len(hashes) > 1 else (
            hashes[0] if hashes else None
        )
        result.append(
            _candidate(
                "image",
                normalize_text(alt),
                part,
                f"{base_path}/w:drawing[{drawing_index}]",
                source_index,
                relationship_hash,
            )
        )
    return result


def _story_nodes(
    package: OoxmlPackage, profile: FormatProfile
) -> list[dict[str, object]]:
    body = package.xml("word/document.xml").find("w:body", namespaces=NS)
    if body is None:
        return []
    result: list[dict[str, object]] = []
    paragraph_number = 0
    table_number = 0
    source_index = 0
    for child in body:
        local = etree.QName(child).localname
        if local == "p":
            paragraph_number += 1
            base_path = f"/w:document/w:body/w:p[{paragraph_number}]"
            text = _clean_paragraph(child, profile)
            if text:
                result.append(
                    _candidate(
                        "paragraph",
                        text,
                        "word/document.xml",
                        base_path,
                        source_index,
                    )
                )
                source_index += 1
            images = _images(
                child,
                package,
                "word/document.xml",
                base_path,
                source_index,
            )
            result.extend(images)
            source_index += len(images)
        elif local == "tbl":
            table_number += 1
            cells = child.xpath("./w:tr/w:tc", namespaces=NS)
            normalized_cells = [
                normalize_text(
                    " ".join(
                        _clean_paragraph(paragraph, profile)
                        for paragraph in cell.xpath(".//w:p", namespaces=NS)
                    )
                )
                for cell in cells
            ]
            table_hash = canonical_sha256(normalized_cells)
            cell_offset = 0
            for row_index, row in enumerate(
                child.xpath("./w:tr", namespaces=NS), start=1
            ):
                for column_index, cell in enumerate(
                    row.xpath("./w:tc", namespaces=NS), start=1
                ):
                    result.append(
                        _candidate(
                            "table",
                            normalized_cells[cell_offset],
                            "word/document.xml",
                            (
                                f"/w:document/w:body/w:tbl[{table_number}]"
                                f"/w:tr[{row_index}]/w:tc[{column_index}]"
                            ),
                            source_index,
                            table_hash,
                        )
                    )
                    source_index += 1
                    cell_offset += 1
                    result.extend(
                        _images(
                            cell,
                            package,
                            "word/document.xml",
                            (
                                f"/w:document/w:body/w:tbl[{table_number}]"
                                f"/w:tr[{row_index}]/w:tc[{column_index}]"
                            ),
                            source_index,
                        )
                    )
                    source_index = len(result)
    return result


def _section_story_nodes(
    package: OoxmlPackage,
    profile: FormatProfile,
    kind: str,
) -> list[dict[str, object]]:
    relationships = _relationship_map(package.relationships(), "word/document.xml")
    sections = package.xml("word/document.xml").xpath(
        ".//w:body/w:p/w:pPr/w:sectPr | .//w:body/w:sectPr", namespaces=NS
    )
    inherited: list[str] = []
    result: list[dict[str, object]] = []
    for section_index, section in enumerate(sections, start=1):
        references = section.xpath(
            f"./w:{kind}Reference/@r:id", namespaces=NS
        )
        if references:
            inherited = list(references)
        for reference_index, relationship_id in enumerate(inherited, start=1):
            relationship = relationships.get(relationship_id)
            if relationship is None or relationship.target_mode == "External":
                continue
            part = resolve_relationship_target(
                relationship.source_part, relationship.target
            )
            root = package.xml(part)
            for paragraph_index, paragraph in enumerate(
                root.xpath(".//w:p", namespaces=NS), start=1
            ):
                text = _clean_paragraph(paragraph, profile)
                if not text:
                    continue
                result.append(
                    _candidate(
                        kind,
                        text,
                        part,
                        (
                            f"/section[{section_index}]/{kind}[{reference_index}]"
                            f"/w:p[{paragraph_index}]"
                        ),
                        len(result),
                    )
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
    counts: Counter[tuple[str, str, str]] = Counter()
    payloads: list[list[object]] = []
    nodes = [node for collection in collections for node in collection]
    for node in nodes:
        key = (
            str(node["node_type"]),
            str(node["normalized_text"]),
            str(node.get("relationship_hash") or ""),
        )
        ordinal = counts[key]
        counts[key] += 1
        payloads.append(
            [
                SCHEMA_VERSION,
                key[0],
                key[1],
                key[2],
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
    body = _story_nodes(package, profile)
    headers = _section_story_nodes(package, profile, "header")
    footers = _section_story_nodes(package, profile, "footer")
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
