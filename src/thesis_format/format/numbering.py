"""Automatic heading, appendix, and caption numbering repairs."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from thesis_format.demo.build import _insert_by_schema_order
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument, SemanticParagraph


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
_HEADING_OWNER = ("54464844", "48454144")
_APPENDIX_OWNER = ("54464150", "41505058")


@dataclass(frozen=True)
class _NumberingContext:
    heading_num_id: str | None = None
    appendix_num_id: str | None = None


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


def _integer_ids(numbering: etree._Element, name: str, attribute: str) -> set[int]:
    values: set[int] = set()
    for value in numbering.xpath(
        f"./w:{name}/@w:{attribute}", namespaces=NS
    ):
        try:
            candidate = int(value)
        except ValueError:
            continue
        if candidate >= 0:
            values.add(candidate)
    return values


def _allocate_id(used: set[int], preferred: str | None = None) -> str:
    if preferred is not None:
        try:
            candidate = int(preferred)
        except ValueError:
            candidate = -1
        if candidate >= 0 and candidate not in used:
            used.add(candidate)
            return str(candidate)
    candidate = max(used, default=-1) + 1
    while candidate in used:
        candidate += 1
    used.add(candidate)
    return str(candidate)


def _remove_owned_numbering(
    numbering: etree._Element,
    owner: tuple[str, str],
) -> tuple[str | None, str | None]:
    abstracts = numbering.xpath(
        "./w:abstractNum[w:nsid[@w:val=$nsid]][w:tmpl[@w:val=$tmpl]]",
        namespaces=NS,
        nsid=owner[0],
        tmpl=owner[1],
    )
    abstract_ids = [
        element.get(f"{W}abstractNumId")
        for element in abstracts
        if element.get(f"{W}abstractNumId") is not None
    ]
    nums = [
        element
        for element in numbering.findall("w:num", namespaces=NS)
        if element.xpath(
            "string(./w:abstractNumId/@w:val)", namespaces=NS
        )
        in abstract_ids
    ]
    preferred_abstract = abstract_ids[0] if abstract_ids else None
    preferred_num = nums[0].get(f"{W}numId") if nums else None
    for element in (*nums, *abstracts):
        numbering.remove(element)
    return preferred_abstract, preferred_num


def _owned_abstract(
    abstract_id: str,
    owner: tuple[str, str],
) -> etree._Element:
    abstract = _new("abstractNum", abstractNumId=abstract_id)
    _add(abstract, _new("nsid", val=owner[0]))
    _add(abstract, _new("multiLevelType", val="multilevel"))
    _add(abstract, _new("tmpl", val=owner[1]))
    return abstract


def _install_numbering(
    numbering: etree._Element,
    profile: FormatProfile,
    *,
    heading: bool,
    appendix: bool,
) -> _NumberingContext:
    heading_preferred = (
        _remove_owned_numbering(numbering, _HEADING_OWNER)
        if heading
        else (None, None)
    )
    appendix_preferred = (
        _remove_owned_numbering(numbering, _APPENDIX_OWNER)
        if appendix
        else (None, None)
    )
    abstract_ids = _integer_ids(numbering, "abstractNum", "abstractNumId")
    num_ids = _integer_ids(numbering, "num", "numId")
    heading_abstract_id = (
        _allocate_id(abstract_ids, heading_preferred[0]) if heading else None
    )
    heading_num_id = (
        _allocate_id(num_ids, heading_preferred[1]) if heading else None
    )
    appendix_abstract_id = (
        _allocate_id(abstract_ids, appendix_preferred[0]) if appendix else None
    )
    appendix_num_id = (
        _allocate_id(num_ids, appendix_preferred[1]) if appendix else None
    )

    if heading_abstract_id is not None and heading_num_id is not None:
        abstract = _owned_abstract(heading_abstract_id, _HEADING_OWNER)
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
        num = _new("num", numId=heading_num_id)
        _add(num, _new("abstractNumId", val=heading_abstract_id))
        _add(numbering, num)

    if appendix_abstract_id is not None and appendix_num_id is not None:
        appendix_definition = _owned_abstract(
            appendix_abstract_id, _APPENDIX_OWNER
        )
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
        _add(appendix_definition, level)
        _add(numbering, appendix_definition)
        appendix_number = _new("num", numId=appendix_num_id)
        _add(
            appendix_number,
            _new("abstractNumId", val=appendix_abstract_id),
        )
        _add(numbering, appendix_number)

    return _NumberingContext(heading_num_id, appendix_num_id)


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


def _caption_numbering_runs(
    role: str,
    profile: FormatProfile,
) -> list[etree._Element]:
    label = "图" if role == "figure_caption" else "表"
    result: list[etree._Element] = []
    label_run = _new("r")
    label_text = _new("t")
    label_text.set(
        "{http://www.w3.org/XML/1998/namespace}space",
        "preserve",
    )
    label_text.text = f"{label} "
    label_run.append(label_text)
    result.append(label_run)
    heading_style = profile.styles.heading_1.word_styles[0]
    result.extend(_field_runs(f'STYLEREF "{heading_style}" \\n', "1"))
    separator = (
        profile.numbering.figures.separator
        if role == "figure_caption"
        else profile.numbering.tables.separator
    )
    separator_run = _new("r")
    separator_text = _new("t")
    separator_text.text = separator
    separator_run.append(separator_text)
    result.append(separator_run)
    result.extend(_field_runs(f"SEQ {label} \\s 1 \\* ARABIC", "1"))
    return result


def _replace_caption_token(
    paragraph: etree._Element,
    role: str,
    profile: FormatProfile,
    token: str,
) -> bool:
    text_nodes = paragraph.xpath(".//w:t", namespaces=NS)
    full_text = "".join(text.text or "" for text in text_nodes)
    if not full_text.startswith(token):
        return False
    token_end = len(token)
    affected: list[tuple[etree._Element, int, int]] = []
    offset = 0
    for text in text_nodes:
        value = text.text or ""
        start = offset
        end = offset + len(value)
        offset = end
        if start >= token_end:
            break
        if end > 0:
            affected.append((text, start, min(end, token_end)))
    if not affected or affected[-1][2] != token_end:
        return False
    runs: list[etree._Element] = []
    for text, _, _ in affected:
        run = text.getparent()
        if (
            run is None
            or run.getparent() is not paragraph
            or etree.QName(run).localname != "r"
            or any(
                etree.QName(child).localname not in {"rPr", "t"}
                for child in run
            )
        ):
            return False
        if run not in runs:
            runs.append(run)
    first_index = paragraph.index(runs[0])
    last_index = paragraph.index(runs[-1])
    if any(
        etree.QName(child).localname != "r"
        for child in paragraph[first_index : last_index + 1]
    ):
        return False
    for text, start, end in affected:
        value = text.text or ""
        local_end = min(len(value), end - start)
        text.text = value[local_end:]
    for replacement in reversed(_caption_numbering_runs(role, profile)):
        paragraph.insert(first_index, replacement)
    return True


def repair_numbering(
    document: etree._Element,
    numbering: etree._Element,
    semantic: SemanticDocument,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    """Install deterministic numbering and apply it only to confirmed roles."""

    repaired: set[str] = set()
    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    semantic_by_location = {node.location: node for node in semantic.paragraphs}
    eligible: list[tuple[dict[str, object], SemanticParagraph]] = []
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
        eligible.append((finding, node))
    context = _install_numbering(
        numbering,
        profile,
        heading=any(
            node.role in {"heading_1", "heading_2", "heading_3"}
            for _, node in eligible
        ),
        appendix=any(node.role == "appendix_heading" for _, node in eligible),
    )
    for finding, node in eligible:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        index = int(location.split(":")[1]) - 1
        paragraph = paragraphs[index]
        if node.role in {"heading_1", "heading_2", "heading_3"}:
            if node.manual_number_token is None or context.heading_num_id is None:
                continue
            _strip_token(paragraph, node.manual_number_token)
            _set_num_pr(
                paragraph,
                int(node.role[-1]) - 1,
                context.heading_num_id,
            )
        elif node.role == "appendix_heading":
            if node.manual_number_token is None or context.appendix_num_id is None:
                continue
            _strip_token(paragraph, node.manual_number_token)
            _set_num_pr(paragraph, 0, context.appendix_num_id)
        elif node.role in {"figure_caption", "table_caption"}:
            if node.manual_number_token is None or not _replace_caption_token(
                paragraph,
                node.role,
                profile,
                node.manual_number_token,
            ):
                continue
        repaired.add(f"{rule_id}|{location}")
    return repaired
