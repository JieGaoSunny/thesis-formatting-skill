"""Figure, caption, and table repairs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": W_NS, "wp": WP_NS}
W = f"{{{W_NS}}}"


@dataclass(frozen=True)
class _Block:
    kind: str
    element: etree._Element
    paragraph_index: int | None = None
    object_number: int | None = None
    caption_location: str | None = None
    number: str | None = None
    bookmarks: frozenset[str] = frozenset()
    object_count: int = 1


def _normalized_marker(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _number_marker(text: str) -> str | None:
    match = re.match(
        r"^\s*(?:图|表|figure|table)\s*([0-9A-Z]+(?:[.\-—][0-9A-Z]+)*)",
        text,
        re.IGNORECASE,
    )
    return _normalized_marker(match.group(1)) if match else None


def _element_bookmarks(element: etree._Element) -> frozenset[str]:
    return frozenset(
        _normalized_marker(value)
        for value in element.xpath(".//w:bookmarkStart/@w:name", namespaces=NS)
        if value and not value.startswith("_")
    )


def _object_markers(block: _Block) -> set[str]:
    markers = set(block.bookmarks)
    if block.kind == "figure":
        markers.update(
            _normalized_marker(value)
            for value in block.element.xpath(
                ".//wp:docPr/@title | .//wp:docPr/@descr", namespaces=NS
            )
            if value
        )
    return {marker for marker in markers if marker}


def _explicitly_matches(caption: _Block, object_block: _Block) -> bool:
    caption_markers = set(caption.bookmarks)
    if caption.number:
        caption_markers.add(caption.number)
    object_markers = _object_markers(object_block)
    return bool(
        caption_markers
        and object_markers
        and any(
            left == right or left in right or right in left
            for left in caption_markers
            for right in object_markers
        )
    )


def _body_blocks(
    body: etree._Element,
    semantic: SemanticDocument,
) -> list[_Block]:
    semantic_by_element = {
        id(element): node
        for element, node in zip(
            body.xpath(".//w:p", namespaces=NS),
            semantic.paragraphs,
            strict=True,
        )
    }
    blocks: list[_Block] = []
    paragraph_number = 0
    table_number = 0
    for child in body:
        if not isinstance(child.tag, str):
            continue
        local_name = etree.QName(child).localname
        if local_name == "p":
            paragraph_number += 1
            node = semantic_by_element.get(id(child))
            if child.xpath(".//w:drawing", namespaces=NS):
                kind = "figure"
            elif node is not None and node.role in {
                "figure_caption",
                "table_caption",
            }:
                kind = node.role
            else:
                kind = "other"
            blocks.append(
                _Block(
                    kind=kind,
                    element=child,
                    paragraph_index=paragraph_number,
                    caption_location=(
                        node.location if kind.endswith("_caption") else None
                    ),
                    number=_number_marker(node.raw_text) if node is not None else None,
                    bookmarks=(
                        frozenset(_normalized_marker(value) for value in node.bookmarks)
                        if node is not None
                        else frozenset()
                    ),
                    object_count=len(
                        child.xpath(".//w:drawing", namespaces=NS)
                    )
                    if kind == "figure"
                    else 1,
                )
            )
        elif local_name == "tbl":
            table_number += 1
            blocks.append(
                _Block(
                    kind="table",
                    element=child,
                    object_number=table_number,
                    bookmarks=_element_bookmarks(child),
                )
            )
        else:
            blocks.append(_Block(kind="other", element=child))
    return blocks


def _caption_associations(
    blocks: list[_Block],
    object_kind: str,
) -> tuple[dict[int, _Block], set[int]]:
    caption_kind = f"{object_kind}_caption"
    relevant = {object_kind, caption_kind}
    associations: dict[int, _Block] = {}
    ambiguous: set[int] = set()
    start = 0
    while start < len(blocks):
        if blocks[start].kind not in relevant:
            start += 1
            continue
        end = start
        while end < len(blocks) and blocks[end].kind in relevant:
            end += 1
        group = blocks[start:end]
        objects = [block for block in group if block.kind == object_kind]
        captions = [block for block in group if block.kind == caption_kind]
        invalid_objects = [
            block for block in objects if block.object_count != 1
        ]
        if invalid_objects:
            ambiguous.update(id(block.element) for block in objects)
            start = end
            continue
        explicit_pairs = [
            (object_block, caption)
            for object_block in objects
            for caption in captions
            if _explicitly_matches(caption, object_block)
        ]
        if len(explicit_pairs) == 1:
            object_block, caption = explicit_pairs[0]
            associations[id(object_block.element)] = caption
            for candidate in objects:
                if candidate is not object_block:
                    ambiguous.add(id(candidate.element))
        elif len(objects) == 1 and len(captions) == 1:
            associations[id(objects[0].element)] = captions[0]
        else:
            ambiguous.update(id(block.element) for block in objects)
        start = end
    return associations, ambiguous


def _property(parent: etree._Element, group: str, name: str) -> etree._Element:
    properties = parent.find(f"w:{group}", namespaces=NS)
    if properties is None:
        properties = etree.Element(f"{W}{group}")
        _insert_by_schema_order(parent, properties)
    element = properties.find(f"w:{name}", namespaces=NS)
    if element is None:
        element = etree.Element(f"{W}{name}")
        _insert_by_schema_order(properties, element)
    return element


def _border(name: str, size: str) -> etree._Element:
    element = etree.Element(f"{W}{name}")
    element.set(f"{W}val", "single")
    element.set(f"{W}sz", size)
    element.set(f"{W}color", "000000")
    return element


def repair_objects(
    document: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> tuple[
    set[str],
    dict[str, dict[str, object]],
    dict[str, str],
]:
    """Repair object layout and return caption-move metadata."""

    repaired: set[str] = set()
    moves: dict[str, dict[str, object]] = {}
    unrepaired: dict[str, str] = {}
    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    body = document.find("w:body", namespaces=NS)
    if body is None:
        return repaired, moves, unrepaired
    blocks = _body_blocks(body, semantic)
    figure_associations, ambiguous_figures = _caption_associations(
        blocks, "figure"
    )
    table_associations, ambiguous_tables = _caption_associations(blocks, "table")
    table_by_number = {
        block.object_number: block
        for block in blocks
        if block.kind == "table"
    }
    figure_by_element = {
        id(block.element): block for block in blocks if block.kind == "figure"
    }

    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        if rule_id.startswith("FIGURE.") and location.startswith("paragraph:"):
            index = int(location.split(":")[1]) - 1
            if not 0 <= index < len(paragraphs):
                continue
            paragraph = paragraphs[index]
            if rule_id == "FIGURE.DIMENSIONS.MAX_WIDTH":
                maximum = round(profile.figures.max_width_mm * 36000)
                for extent in paragraph.xpath(".//wp:extent", namespaces=NS):
                    width = int(extent.get("cx", "0"))
                    if width > maximum:
                        height = int(extent.get("cy", "0"))
                        extent.set("cy", str(round(height * maximum / width)))
                        extent.set("cx", str(maximum))
            elif rule_id == "FIGURE.ALIGNMENT":
                _property(paragraph, "pPr", "jc").set(
                    f"{W}val", profile.figures.alignment
                )
            elif rule_id == "FIGURE.CAPTION.POSITION":
                key = f"{rule_id}|{location}"
                association = figure_associations.get(id(paragraph))
                figure_block = figure_by_element.get(id(paragraph))
                if association is None or figure_block is None:
                    unrepaired[key] = (
                        "ambiguous"
                        if id(paragraph) in ambiguous_figures
                        else "missing"
                    )
                    continue
                caption = association.element
                before_position = (
                    "above"
                    if body.index(caption) < body.index(paragraph)
                    else "below"
                )
                body.remove(caption)
                body.insert(
                    body.index(paragraph)
                    + (1 if profile.figures.caption_position == "below" else 0),
                    caption,
                )
                moves[key] = {
                    "caption_location": association.caption_location,
                    "caption_body_number": association.paragraph_index,
                    "object_kind": "figure",
                    "object_number": figure_block.paragraph_index,
                    "before_position": before_position,
                    "after_position": profile.figures.caption_position,
                }
                _property(paragraph, "pPr", "keepNext").set(f"{W}val", "1")
            else:
                continue
            repaired.add(f"{rule_id}|{location}")

    tables = document.xpath(".//w:body//w:tbl", namespaces=NS)
    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        if not location.startswith("table:"):
            continue
        index = int(location.split(":")[1]) - 1
        if not 0 <= index < len(tables):
            continue
        table = tables[index]
        if rule_id == "TABLE.REPEAT_HEADER":
            rows = table.findall("w:tr", namespaces=NS)
            if rows:
                _property(rows[0], "trPr", "tblHeader").set(f"{W}val", "1")
        elif rule_id == "TABLE.ROW_SPLIT":
            for row in table.findall("w:tr", namespaces=NS):
                _property(row, "trPr", "cantSplit").set(f"{W}val", "1")
        elif rule_id == "TABLE.BORDERS.THREE_LINE":
            tbl_pr = table.find("w:tblPr", namespaces=NS)
            if tbl_pr is None:
                tbl_pr = etree.Element(f"{W}tblPr")
                table.insert(0, tbl_pr)
            old = tbl_pr.find("w:tblBorders", namespaces=NS)
            if old is not None:
                tbl_pr.remove(old)
            borders = etree.Element(f"{W}tblBorders")
            _insert_by_schema_order(tbl_pr, borders)
            borders.extend((_border("top", "8"), _border("bottom", "8")))
            rows = table.findall("w:tr", namespaces=NS)
            if rows:
                for cell in rows[0].findall("w:tc", namespaces=NS):
                    tc_pr = cell.find("w:tcPr", namespaces=NS)
                    if tc_pr is None:
                        tc_pr = etree.Element(f"{W}tcPr")
                        cell.insert(0, tc_pr)
                    old_cell = tc_pr.find("w:tcBorders", namespaces=NS)
                    if old_cell is not None:
                        tc_pr.remove(old_cell)
                    cell_borders = etree.Element(f"{W}tcBorders")
                    _insert_by_schema_order(tc_pr, cell_borders)
                    cell_borders.append(_border("bottom", "6"))
                for row in rows[1:]:
                    for cell_border in row.xpath(
                        "./w:tc/w:tcPr/w:tcBorders", namespaces=NS
                    ):
                        cell_border.getparent().remove(cell_border)
        elif rule_id == "TABLE.CAPTION.POSITION":
            key = f"{rule_id}|{location}"
            table_block = table_by_number.get(index + 1)
            association = table_associations.get(id(table))
            if association is None or table_block is None:
                unrepaired[key] = (
                    "ambiguous"
                    if id(table) in ambiguous_tables
                    else "missing"
                )
                continue
            caption = association.element
            before_position = (
                "above" if body.index(caption) < body.index(table) else "below"
            )
            body.remove(caption)
            body.insert(
                body.index(table)
                + (1 if profile.tables.caption_position == "below" else 0),
                caption,
            )
            moves[key] = {
                "caption_location": association.caption_location,
                "caption_body_number": association.paragraph_index,
                "object_kind": "table",
                "object_number": index + 1,
                "before_position": before_position,
                "after_position": profile.tables.caption_position,
            }
        else:
            continue
        repaired.add(f"{rule_id}|{location}")
    return repaired, moves, unrepaired
