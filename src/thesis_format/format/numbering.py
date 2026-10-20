"""Automatic heading, appendix, and caption numbering repairs."""

from __future__ import annotations

import re

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _new(name: str, **attributes: str) -> etree._Element:
    element = etree.Element(f"{W}{name}")
    for key, value in attributes.items():
        element.set(f"{W}{key}", value)
    return element


def _add(parent: etree._Element, child: etree._Element) -> None:
    _insert_by_schema_order(parent, child)


def _field_runs(instruction: str, placeholder: str) -> list[etree._Element]:
    result: list[etree._Element] = []
    for field_type, text in (
        ("begin", None),
        (None, instruction),
        ("separate", None),
        (None, placeholder),
        ("end", None),
    ):
        run = _new("r")
        if field_type is not None:
            field = _new("fldChar", fldCharType=field_type)
            if field_type == "begin":
                field.set(f"{W}dirty", "true")
            run.append(field)
        elif text == instruction:
            code = _new("instrText")
            code.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            code.text = f" {text} "
            run.append(code)
        else:
            value = _new("t")
            value.text = text
            run.append(value)
        result.append(run)
    return result


def _install_numbering(numbering: etree._Element, profile: FormatProfile) -> None:
    for num_id in ("910", "911"):
        for element in numbering.xpath(
            f"./w:num[@w:numId='{num_id}']", namespaces=NS
        ):
            numbering.remove(element)
    for abstract_id in ("910", "911"):
        for element in numbering.xpath(
            f"./w:abstractNum[@w:abstractNumId='{abstract_id}']", namespaces=NS
        ):
            numbering.remove(element)

    abstract = _new("abstractNum", abstractNumId="910")
    _add(abstract, _new("multiLevelType", val="multilevel"))
    for level, (fmt, text, role) in enumerate(
        (
            ("chineseCounting", "第%1章", "heading_1"),
            ("decimal", "%1.%2", "heading_2"),
            ("decimal", "%1.%2.%3", "heading_3"),
        )
    ):
        lvl = _new("lvl", ilvl=str(level))
        children = [
            _new("start", val="1"),
            _new("numFmt", val=fmt),
            _new("pStyle", val=profile.styles[role].word_styles[0]),
            _new("suff", val="space" if level == 0 else "nothing"),
            _new("lvlText", val=text),
        ]
        if level:
            children.append(_new("lvlRestart", val="1"))
        for child in children:
            _add(lvl, child)
        _add(abstract, lvl)
    _add(numbering, abstract)
    num = _new("num", numId="910")
    _add(num, _new("abstractNumId", val="910"))
    _add(numbering, num)

    appendix = _new("abstractNum", abstractNumId="911")
    _add(appendix, _new("multiLevelType", val="multilevel"))
    level = _new("lvl", ilvl="0")
    for child in (
        _new("start", val="1"),
        _new("numFmt", val="upperLetter"),
        _new(
            "pStyle",
            val=profile.styles.appendix_heading.word_styles[0],
        ),
        _new("suff", val="space"),
        _new("lvlText", val="附录 %1"),
    ):
        _add(level, child)
    _add(appendix, level)
    _add(numbering, appendix)
    appendix_num = _new("num", numId="911")
    _add(appendix_num, _new("abstractNumId", val="911"))
    _add(numbering, appendix_num)


def _strip_token(paragraph: etree._Element, token: str) -> None:
    remaining = token
    for text in paragraph.xpath(".//w:t", namespaces=NS):
        if not remaining:
            break
        value = text.text or ""
        prefix = min(len(value), len(remaining))
        if value[:prefix] != remaining[:prefix]:
            return
        text.text = value[prefix:]
        remaining = remaining[prefix:]
    if remaining:
        return
    first_text = paragraph.find(".//w:t", namespaces=NS)
    if first_text is not None:
        first_text.text = (first_text.text or "").lstrip()


def _set_num_pr(paragraph: etree._Element, level: int, num_id: str) -> None:
    p_pr = paragraph.find("w:pPr", namespaces=NS)
    if p_pr is None:
        p_pr = _new("pPr")
        paragraph.insert(0, p_pr)
    old = p_pr.find("w:numPr", namespaces=NS)
    if old is not None:
        p_pr.remove(old)
    num_pr = _new("numPr")
    num_pr.extend((_new("ilvl", val=str(level)), _new("numId", val=num_id)))
    _insert_by_schema_order(p_pr, num_pr)
    outline = p_pr.find("w:outlineLvl", namespaces=NS)
    if outline is None:
        outline = _new("outlineLvl")
        _insert_by_schema_order(p_pr, outline)
    outline.set(f"{W}val", str(level))


def _caption_content(
    paragraph: etree._Element,
    role: str,
    profile: FormatProfile,
    raw_text: str,
) -> None:
    label = "图" if role == "figure_caption" else "表"
    title = re.sub(rf"^{label}\s*\d+[.-]\d+\s*", "", raw_text).strip()
    for child in list(paragraph):
        if etree.QName(child).localname not in {
            "pPr",
            "bookmarkStart",
            "bookmarkEnd",
        }:
            paragraph.remove(child)
    run = _new("r")
    text = _new("t")
    text.text = f"{label} "
    run.append(text)
    paragraph.append(run)
    heading_style = profile.styles.heading_1.word_styles[0]
    paragraph.extend(
        _field_runs(f'STYLEREF "{heading_style}" \\n', "1")
    )
    separator = (
        profile.numbering.figures.separator
        if role == "figure_caption"
        else profile.numbering.tables.separator
    )
    separator_run = _new("r")
    separator_text = _new("t")
    separator_text.text = separator
    separator_run.append(separator_text)
    paragraph.append(separator_run)
    paragraph.extend(
        _field_runs(f"SEQ {label} \\s 1 \\* ARABIC", "1")
    )
    title_run = _new("r")
    title_text = _new("t")
    title_text.text = f" {title}"
    title_run.append(title_text)
    paragraph.append(title_run)


def repair_numbering(
    document: etree._Element,
    numbering: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Install deterministic numbering and apply it only to confirmed roles."""

    _install_numbering(numbering, profile)
    repaired: set[str] = set()
    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    semantic_by_location = {node.location: node for node in semantic.paragraphs}
    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        if rule_id not in {
            "NUMBERING.MANUAL_HEADING",
            "NUMBERING.MANUAL_APPENDIX",
            "NUMBERING.MANUAL_CAPTION",
        } or not location.startswith("paragraph:"):
            continue
        index = int(location.split(":")[1]) - 1
        node = semantic_by_location.get(location)
        if (
            node is None
            or node.role is None
            or not node.repairable
            or not 0 <= index < len(paragraphs)
        ):
            continue
        paragraph = paragraphs[index]
        if node.manual_number_token:
            _strip_token(paragraph, node.manual_number_token)
        if node.role in {"heading_1", "heading_2", "heading_3"}:
            _set_num_pr(paragraph, int(node.role[-1]) - 1, "910")
        elif node.role == "appendix_heading":
            _set_num_pr(paragraph, 0, "911")
        elif node.role in {"figure_caption", "table_caption"}:
            _caption_content(paragraph, node.role, profile, node.raw_text)
        repaired.add(f"{rule_id}|{location}")
    return repaired
