"""Figure, caption, and table repairs."""

from __future__ import annotations

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS = {"w": W_NS, "wp": WP_NS}
W = f"{{{W_NS}}}"


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
) -> tuple[set[str], list[dict[str, object]]]:
    """Repair object layout and return caption-move metadata."""

    repaired: set[str] = set()
    moves: list[dict[str, object]] = []
    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    semantic_by_location = {node.location: node for node in semantic.paragraphs}
    body = document.find("w:body", namespaces=NS)
    if body is None:
        return repaired, moves
    body_children = [child for child in body if isinstance(child.tag, str)]

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
                object_child = paragraph
                child_index = body_children.index(object_child)
                candidates = []
                for candidate_index, child in enumerate(body_children):
                    if etree.QName(child).localname != "p":
                        continue
                    try:
                        paragraph_index = paragraphs.index(child) + 1
                    except ValueError:
                        continue
                    node = semantic_by_location.get(f"paragraph:{paragraph_index}")
                    if node is not None and node.role == "figure_caption":
                        candidates.append((abs(candidate_index - child_index), child))
                if candidates:
                    caption = min(candidates, key=lambda item: item[0])[1]
                    body.remove(caption)
                    body.insert(
                        body.index(object_child)
                        + (1 if profile.figures.caption_position == "below" else 0),
                        caption,
                    )
                    moves.append({"rule_id": rule_id, "caption": caption})
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
            table_child_index = body_children.index(table)
            paragraph_nodes = {
                id(paragraph): semantic_by_location.get(
                    f"paragraph:{paragraph_index}"
                )
                for paragraph_index, paragraph in enumerate(paragraphs, start=1)
            }
            candidates = [
                (abs(candidate_index - table_child_index), child)
                for candidate_index, child in enumerate(body_children)
                if etree.QName(child).localname == "p"
                and (
                    node := paragraph_nodes.get(id(child))
                ) is not None
                and node.role == "table_caption"
            ]
            if not candidates:
                continue
            caption = min(candidates, key=lambda item: item[0])[1]
            body.remove(caption)
            body.insert(
                body.index(table)
                + (1 if profile.tables.caption_position == "below" else 0),
                caption,
            )
            moves.append({"rule_id": rule_id, "caption": caption})
        else:
            continue
        repaired.add(f"{rule_id}|{location}")
    return repaired, moves
