"""Automatic heading, appendix, and caption numbering repairs."""

from __future__ import annotations

import re
import warnings
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


def _paragraph_num_id(
    paragraph: etree._Element,
    styles: etree._Element | None,
    level: int,
) -> str | None:
    num_pr = paragraph.find("./w:pPr/w:numPr", namespaces=NS)
    if num_pr is None and styles is not None:
        style_ids = paragraph.xpath(
            "./w:pPr/w:pStyle/@w:val",
            namespaces=NS,
        )
        seen: set[str] = set()
        style_id = style_ids[0] if style_ids else None
        while style_id is not None and style_id not in seen:
            seen.add(style_id)
            style_nodes = styles.xpath(
                "./w:style[@w:styleId=$style_id]",
                namespaces=NS,
                style_id=style_id,
            )
            if len(style_nodes) != 1:
                break
            num_pr = style_nodes[0].find("./w:pPr/w:numPr", namespaces=NS)
            if num_pr is not None:
                break
            based_on = style_nodes[0].xpath(
                "./w:basedOn/@w:val",
                namespaces=NS,
            )
            style_id = based_on[0] if based_on else None
    if num_pr is None:
        return None
    levels = num_pr.xpath("./w:ilvl/@w:val", namespaces=NS)
    try:
        actual_level = int(levels[0]) if levels else 0
    except ValueError:
        return None
    values = num_pr.xpath("./w:numId/@w:val", namespaces=NS)
    return (
        values[0]
        if actual_level == level and values and values[0] != "0"
        else None
    )


def _numbering_level(
    numbering: etree._Element,
    num_id: str,
    level: int,
) -> etree._Element | None:
    nums = numbering.xpath(
        "./w:num[@w:numId=$num_id]",
        namespaces=NS,
        num_id=num_id,
    )
    if len(nums) != 1:
        return None
    overrides = nums[0].xpath(
        "./w:lvlOverride[@w:ilvl=$level]/w:lvl",
        namespaces=NS,
        level=str(level),
    )
    if overrides:
        return overrides[0]
    abstract_ids = nums[0].xpath(
        "./w:abstractNumId/@w:val",
        namespaces=NS,
    )
    if len(abstract_ids) != 1:
        return None
    levels = numbering.xpath(
        "./w:abstractNum[@w:abstractNumId=$abstract_id]"
        "/w:lvl[@w:ilvl=$level]",
        namespaces=NS,
        abstract_id=abstract_ids[0],
        level=str(level),
    )
    return levels[0] if len(levels) == 1 else None


def _numbering_level_compatible(
    level_node: etree._Element,
    role: str,
    level: int,
    profile: FormatProfile,
) -> bool:
    profile_rule = {
        "heading_1": profile.numbering.chapters,
        "heading_2": profile.numbering.sections,
        "heading_3": profile.numbering.sections,
        "appendix_heading": profile.numbering.appendices,
    }[role]
    expected_format = {
        "chinese_chapter": "chineseCounting",
        "decimal": "decimal",
        "upper_alpha": "upperLetter",
    }.get(profile_rule.format)
    if level_node.xpath(
        "string(./w:numFmt/@w:val)", namespaces=NS
    ) != expected_format:
        return False
    expected_core = {
        "chinese_chapter": "第%1章",
        "upper_alpha": "附录 %1",
        "decimal": profile_rule.separator.join(
            f"%{index}" for index in range(1, level + 2)
        ),
    }.get(profile_rule.format)
    level_text = level_node.xpath(
        "string(./w:lvlText/@w:val)", namespaces=NS
    )
    suffix = {
        "space": " ",
        "tab": "\t",
        "nothing": "",
    }.get(
        level_node.xpath("string(./w:suff/@w:val)", namespaces=NS),
        "\t",
    )
    if profile_rule.format == "decimal":
        if level_text != expected_core:
            return False
    elif not (
        level_text == f"{expected_core}{profile_rule.separator}"
        or (
            level_text == expected_core
            and suffix == profile_rule.separator
        )
    ):
        return False
    restart = level_node.xpath(
        "string(./w:lvlRestart/@w:val)", namespaces=NS
    ) or None
    if profile_rule.restart_scope == "document":
        if restart not in {None, "0"}:
            return False
    elif profile_rule.restart_scope == "chapter":
        if level == 0 or restart not in {None, "1"}:
            return False
    elif profile_rule.restart_scope == "appendix":
        if restart is None:
            return False
    else:
        return False
    styles = level_node.xpath("./w:pStyle/@w:val", namespaces=NS)
    return not styles or any(
        styles[0].casefold() == name.casefold()
        for name in profile.styles[role].word_styles
    )


def _existing_sequence(
    numbering: etree._Element,
    paragraphs: list[etree._Element],
    styles: etree._Element | None,
    semantic: SemanticDocument,
    profile: FormatProfile,
    roles: set[str],
    required_roles: set[str],
    *,
    warning_name: str,
) -> tuple[str | None, bool]:
    num_roles: dict[str, set[str]] = {}
    for paragraph, node in zip(paragraphs, semantic.paragraphs, strict=True):
        if node.role not in roles:
            continue
        level = 0 if node.role == "appendix_heading" else int(node.role[-1]) - 1
        num_id = _paragraph_num_id(paragraph, styles, level)
        if num_id is not None:
            num_roles.setdefault(num_id, set()).add(node.role)
    if not num_roles:
        return None, False
    compatible = all(
        all(
            (
                level_node := _numbering_level(
                    numbering,
                    num_id,
                    0 if role == "appendix_heading" else int(role[-1]) - 1,
                )
            )
            is not None
            and _numbering_level_compatible(
                level_node,
                role,
                0 if role == "appendix_heading" else int(role[-1]) - 1,
                profile,
            )
            for role in observed_roles | required_roles
        )
        for num_id, observed_roles in num_roles.items()
    )
    if compatible and len(num_roles) == 1:
        return next(iter(num_roles)), False
    warnings.warn(
        f"Skipping repair because incompatible {warning_name} numbering "
        "sequences are present or the sequence is ambiguous.",
        RuntimeWarning,
        stacklevel=3,
    )
    return None, True


_SEQ_FIELD = re.compile(
    r"(?i)(\bSEQ\s+)(?:\"([^\"]+)\"|([^\s\\]+))"
)


@dataclass
class _FieldCode:
    instruction: str
    simple: etree._Element | None = None
    parts: tuple[etree._Element, ...] = ()

    def set_sequence_identifier(self, identifier: str) -> None:
        replacement = _replace_sequence_identifier(
            self.instruction,
            identifier,
        )
        if self.simple is not None:
            self.simple.set(f"{W}instr", replacement)
        elif self.parts:
            remaining = replacement
            for part in self.parts[:-1]:
                length = len(part.text or "")
                part.text = remaining[:length]
                remaining = remaining[length:]
            self.parts[-1].text = remaining
        self.instruction = replacement


@dataclass
class _ComplexField:
    parts: list[etree._Element]
    collecting: bool = True
    emitted: bool = False


def _field_codes(paragraph: etree._Element) -> list[_FieldCode]:
    result: list[_FieldCode] = []
    complex_fields: list[_ComplexField] = []

    def emit(field: _ComplexField) -> None:
        if field.emitted:
            return
        instruction = "".join(part.text or "" for part in field.parts)
        if instruction.strip():
            result.append(_FieldCode(instruction, parts=tuple(field.parts)))
        field.emitted = True

    for descendant in paragraph.iter():
        name = etree.QName(descendant).localname
        if name == "fldSimple":
            instruction = descendant.get(f"{W}instr")
            if instruction and instruction.strip():
                result.append(_FieldCode(instruction, simple=descendant))
        elif name == "fldChar":
            field_type = descendant.get(f"{W}fldCharType")
            if field_type == "begin":
                complex_fields.append(_ComplexField([]))
            elif field_type == "separate" and complex_fields:
                emit(complex_fields[-1])
                complex_fields[-1].collecting = False
            elif field_type == "end" and complex_fields:
                emit(complex_fields.pop())
        elif (
            name == "instrText"
            and complex_fields
            and complex_fields[-1].collecting
        ):
            complex_fields[-1].parts.append(descendant)
    for field in complex_fields:
        emit(field)
    return result


def _sequence_identifier(instruction: str) -> str | None:
    match = _SEQ_FIELD.search(instruction)
    return (match.group(2) or match.group(3)) if match is not None else None


def _replace_sequence_identifier(instruction: str, identifier: str) -> str:
    return _SEQ_FIELD.sub(
        lambda match: f'{match.group(1)}{identifier}',
        instruction,
        count=1,
    )


def _caption_sequence_identifiers(
    paragraphs: list[etree._Element],
    semantic: SemanticDocument,
    roles: set[str],
) -> tuple[dict[str, str], set[str]]:
    chosen: dict[str, str] = {}
    blocked: set[str] = set()
    accepted = {
        "figure_caption": {"figure", "图"},
        "table_caption": {"table", "表"},
    }
    for role, identifiers in accepted.items():
        if role not in roles:
            continue
        fields: list[_FieldCode] = []
        values: list[str] = []
        for paragraph, node in zip(paragraphs, semantic.paragraphs, strict=True):
            if node.role != role:
                continue
            for field in _field_codes(paragraph):
                identifier = _sequence_identifier(field.instruction)
                if identifier is not None:
                    fields.append(field)
                    values.append(identifier)
        if not values:
            continue
        accepted_folded = {value.casefold() for value in identifiers}
        if any(value.casefold() not in accepted_folded for value in values):
            label = "figure" if role == "figure_caption" else "table"
            warnings.warn(
                f"Skipping repair because incompatible {label} caption "
                "SEQ identifiers are present.",
                RuntimeWarning,
                stacklevel=3,
            )
            blocked.add(role)
            continue
        selected = values[0]
        chosen[role] = selected
        for field in fields:
            field.set_sequence_identifier(selected)
    return chosen, blocked


def _caption_numbering_runs(
    role: str,
    profile: FormatProfile,
    sequence_identifier: str,
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
    result.extend(
        _field_runs(
            f"SEQ {sequence_identifier} \\s 1 \\* ARABIC",
            "1",
        )
    )
    return result


def _replace_caption_token(
    paragraph: etree._Element,
    role: str,
    profile: FormatProfile,
    token: str,
    sequence_identifier: str,
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
    for replacement in reversed(
        _caption_numbering_runs(role, profile, sequence_identifier)
    ):
        paragraph.insert(first_index, replacement)
    return True


def repair_numbering(
    document: etree._Element,
    numbering: etree._Element,
    styles: etree._Element | None,
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
    needs_heading = any(
        node.role in {"heading_1", "heading_2", "heading_3"}
        for _, node in eligible
    )
    needs_appendix = any(
        node.role == "appendix_heading" for _, node in eligible
    )
    required_heading_roles = {
        node.role
        for _, node in eligible
        if node.role in {"heading_1", "heading_2", "heading_3"}
    }
    heading_num_id, heading_blocked = (
        _existing_sequence(
            numbering,
            paragraphs,
            styles,
            semantic,
            profile,
            {"heading_1", "heading_2", "heading_3"},
            required_heading_roles,
            warning_name="heading",
        )
        if needs_heading
        else (None, False)
    )
    appendix_num_id, appendix_blocked = (
        _existing_sequence(
            numbering,
            paragraphs,
            styles,
            semantic,
            profile,
            {"appendix_heading"},
            {"appendix_heading"},
            warning_name="appendix",
        )
        if needs_appendix
        else (None, False)
    )
    installed = _install_numbering(
        numbering,
        profile,
        heading=needs_heading and heading_num_id is None and not heading_blocked,
        appendix=(
            needs_appendix
            and appendix_num_id is None
            and not appendix_blocked
        ),
    )
    context = _NumberingContext(
        heading_num_id or installed.heading_num_id,
        appendix_num_id or installed.appendix_num_id,
    )
    caption_identifiers, blocked_caption_roles = _caption_sequence_identifiers(
        paragraphs,
        semantic,
        {
            node.role
            for _, node in eligible
            if node.role in {"figure_caption", "table_caption"}
        },
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
            if node.role in blocked_caption_roles:
                continue
            sequence_identifier = caption_identifiers.get(
                node.role,
                "图" if node.role == "figure_caption" else "表",
            )
            if node.manual_number_token is None or not _replace_caption_token(
                paragraph,
                node.role,
                profile,
                node.manual_number_token,
                sequence_identifier,
            ):
                continue
        repaired.add(f"{rule_id}|{location}")
    return repaired
