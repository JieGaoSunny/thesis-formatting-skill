"""Semantic style and direct-formatting repairs."""

from __future__ import annotations

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.profile import FormatProfile, Style
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _replace(parent: etree._Element, name: str, **attributes: str) -> etree._Element:
    existing = parent.find(f"w:{name}", namespaces=NS)
    if existing is not None:
        parent.remove(existing)
    element = etree.Element(f"{W}{name}")
    for key, value in attributes.items():
        element.set(f"{W}{key}", value)
    _insert_by_schema_order(parent, element)
    return element


def _on(parent: etree._Element, name: str, enabled: bool) -> None:
    values = {} if enabled else {"val": "0"}
    _replace(parent, name, **values)


def _configure_style(element: etree._Element, definition: Style) -> None:
    based_on = element.find("w:basedOn", namespaces=NS)
    if based_on is not None:
        element.remove(based_on)
    p_pr = element.find("w:pPr", namespaces=NS)
    if p_pr is None:
        p_pr = etree.Element(f"{W}pPr")
        _insert_by_schema_order(element, p_pr)
    paragraph = definition.paragraph
    spacing = {
        "before": str(round(paragraph.space_before_pt * 20)),
        "after": str(round(paragraph.space_after_pt * 20)),
    }
    if paragraph.line_spacing.type == "exact":
        spacing.update(
            lineRule="exact",
            line=str(round(float(paragraph.line_spacing.value_pt) * 20)),
        )
    else:
        spacing.update(
            lineRule="auto",
            line=str(round(float(paragraph.line_spacing.value) * 240)),
        )
    _replace(p_pr, "spacing", **spacing)
    indent = {"left": str(round(paragraph.left_indent_mm * 1440 / 25.4))}
    if paragraph.first_line_chars:
        indent["firstLineChars"] = str(round(paragraph.first_line_chars * 100))
    if paragraph.hanging_indent_mm:
        indent["hanging"] = str(
            round(paragraph.hanging_indent_mm * 1440 / 25.4)
        )
    _replace(p_pr, "ind", **indent)
    _replace(
        p_pr,
        "jc",
        val={"justify": "both", "left": "start", "right": "end"}.get(
            paragraph.alignment, paragraph.alignment
        ),
    )
    _on(p_pr, "keepNext", paragraph.keep_with_next)
    _on(p_pr, "pageBreakBefore", paragraph.page_break_before)

    r_pr = element.find("w:rPr", namespaces=NS)
    if r_pr is None:
        r_pr = etree.Element(f"{W}rPr")
        _insert_by_schema_order(element, r_pr)
    _replace(
        r_pr,
        "rFonts",
        ascii=definition.run.font_latin,
        hAnsi=definition.run.font_latin,
        eastAsia=definition.run.font_zh,
    )
    _replace(r_pr, "sz", val=str(round(definition.run.size_pt * 2)))
    _on(r_pr, "b", definition.run.bold)
    _on(r_pr, "i", definition.run.italic)


def repair_styles(
    document: etree._Element,
    styles: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Repair known semantic styles while preserving ambiguous paragraphs."""

    repaired: set[str] = set()
    style_by_id = {
        element.get(f"{W}styleId"): element
        for element in styles.findall("w:style", namespaces=NS)
    }
    for role, definition in profile.styles.items():
        style_id = definition.word_styles[0]
        element = style_by_id.get(style_id)
        if element is None:
            element = etree.SubElement(
                styles,
                f"{W}style",
                {f"{W}type": "paragraph", f"{W}styleId": style_id},
            )
            etree.SubElement(element, f"{W}name", {f"{W}val": style_id})
            style_by_id[style_id] = element
        _configure_style(element, definition)

    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    semantic_by_location = {node.location: node for node in semantic.paragraphs}
    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        if rule_id == "STYLE.DEFINITION":
            repaired.add(f"{rule_id}|{location}")
            continue
        if not location.startswith("paragraph:"):
            continue
        index = int(location.split(":")[1]) - 1
        if not 0 <= index < len(paragraphs):
            continue
        node = semantic_by_location.get(location)
        if node is None or node.role is None or not node.repairable:
            continue
        paragraph = paragraphs[index]
        p_pr = paragraph.find("w:pPr", namespaces=NS)
        if p_pr is None:
            p_pr = etree.Element(f"{W}pPr")
            paragraph.insert(0, p_pr)
        if rule_id == "STYLE.ROLE.MAPPING":
            p_style = p_pr.find("w:pStyle", namespaces=NS)
            if p_style is None:
                p_style = etree.Element(f"{W}pStyle")
                p_pr.insert(0, p_style)
            p_style.set(f"{W}val", profile.styles[node.role].word_styles[0])
        elif rule_id == "STYLE.DIRECT_FORMATTING":
            for child in list(p_pr):
                if etree.QName(child).localname not in {"pStyle", "numPr", "sectPr"}:
                    p_pr.remove(child)
            for r_pr in paragraph.xpath("./w:r/w:rPr", namespaces=NS):
                r_pr.getparent().remove(r_pr)
        else:
            continue
        repaired.add(f"{rule_id}|{location}")
    return repaired
