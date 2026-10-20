"""Deterministic, read-only auditing of thesis DOCX formatting."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable, Protocol

from lxml import etree

from thesis_format import __version__
from thesis_format.contracts import (
    canonical_json,
    shortest_unique_digest_prefixes,
    validate_audit,
)
from thesis_format.ooxml import OoxmlPackage, resolve_relationship_target
from thesis_format.profile import FormatProfile
from thesis_format.semantic import SemanticDocument, inspect_document


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
NS = {"w": W_NS, "wp": WP_NS}
W = f"{{{W_NS}}}"
SEVERITY_ORDER = {"error": 0, "violation": 1, "warning": 2}
LOCATION_ORDER = {
    "document": 0,
    "section": 1,
    "paragraph": 2,
    "table": 3,
    "cell": 4,
    "header": 5,
    "footer": 6,
    "part": 7,
}


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """A finding before its deterministic contract ID is assigned."""

    rule_id: str
    severity: str
    location: str
    message: str
    repairable: bool
    before: object
    after: object
    repaired: bool = False


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Shared immutable evidence supplied to every audit rule."""

    path: Path
    profile: FormatProfile
    package: OoxmlPackage
    semantic: SemanticDocument
    document_root: etree._Element
    paragraph_elements: tuple[etree._Element, ...]
    table_elements: tuple[etree._Element, ...]
    section_elements: tuple[etree._Element, ...]


class Rule(Protocol):
    """Stable extension point for independently testable audit rules."""

    rule_id: str

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        """Return findings in document order."""


class RuleRegistry:
    """An immutable registry that preserves caller registration order."""

    def __init__(self, rules: Iterable[Rule] = ()) -> None:
        ordered = tuple(rules)
        seen: set[str] = set()
        for rule in ordered:
            if rule.rule_id in seen:
                raise ValueError(f"duplicate rule_id {rule.rule_id!r}")
            seen.add(rule.rule_id)
        self._rules = ordered

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def __iter__(self):
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def register(self, rule: Rule) -> None:
        """Append a rule while preserving order and ID uniqueness."""

        if any(existing.rule_id == rule.rule_id for existing in self._rules):
            raise ValueError(f"duplicate rule_id {rule.rule_id!r}")
        self._rules = (*self._rules, rule)

    def audit(self, context: AuditContext) -> tuple[AuditFinding, ...]:
        return tuple(
            finding for rule in self._rules for finding in rule.audit(context)
        )


AuditRule = Rule


def _attr(element: etree._Element | None, name: str) -> str | None:
    return None if element is None else element.get(f"{W}{name}")


def _mm_from_twips(value: str | None) -> float | None:
    return None if value is None else round(float(value) * 25.4 / 1440, 2)


def _pt_from_twips(value: str | None) -> float | None:
    return None if value is None else round(float(value) / 20, 2)


def _close(actual: float | None, expected: float, tolerance: float = 0.15) -> bool:
    return actual is not None and abs(actual - expected) <= tolerance


def _location_key(location: str) -> tuple[object, ...]:
    if location == "document":
        return (0,)
    kind, value = location.split(":", 1)
    if kind == "cell":
        return (LOCATION_ORDER[kind], *(int(item) for item in value.split("/")))
    if kind == "part":
        return (LOCATION_ORDER[kind], value)
    return (LOCATION_ORDER[kind], int(value))


def _finding_digest(schema_version: str, finding: dict[str, object]) -> str:
    payload = "|".join(
        (
            schema_version,
            str(finding["rule_id"]),
            str(finding["location"]),
            canonical_json(finding["before"]).rstrip("\n"),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _paragraph_property(
    paragraph: etree._Element, name: str
) -> etree._Element | None:
    return paragraph.find(f"w:pPr/w:{name}", namespaces=NS)


def _field_texts(element: etree._Element) -> tuple[str, ...]:
    values = element.xpath(
        ".//w:instrText/text() | .//w:fldSimple/@w:instr", namespaces=NS
    )
    return tuple(
        re.sub(r"\s+", " ", str(value)).strip() for value in values if str(value).strip()
    )


def _style_role_matches(context: AuditContext, role: str, style_id: str | None) -> bool:
    if style_id is None:
        return False
    style = context.profile.styles[role]
    names = {name.casefold() for name in style.word_styles}
    return style_id.casefold() in names


def _style_role_for_id(
    context: AuditContext, style_id: str | None
) -> str | None:
    if style_id is None:
        return None
    candidate = style_id.casefold()
    return next(
        (
            role
            for role, style in context.profile.styles.items()
            if candidate in {name.casefold() for name in style.word_styles}
        ),
        None,
    )


def _section_for_paragraph(context: AuditContext, paragraph_number: int) -> int:
    section_number = 1
    for index, section in enumerate(context.semantic.sections, start=1):
        if section.start_paragraph <= paragraph_number:
            section_number = index
        else:
            break
    return section_number


def _first_role_section(context: AuditContext, role: str) -> int | None:
    paragraph = next(
        (
            int(node.location.split(":")[1])
            for node in context.semantic.paragraphs
            if node.role == role
        ),
        None,
    )
    return (
        _section_for_paragraph(context, paragraph)
        if paragraph is not None
        else None
    )


def _section_region(
    index: int,
    body_section: int | None,
    appendix_section: int | None,
) -> str:
    if appendix_section is not None and index >= appendix_section:
        return "appendix"
    if body_section is not None and index >= body_section:
        return "body"
    return "front_matter"


def _on(element: etree._Element | None) -> bool:
    value = _attr(element, "val")
    return element is not None and (
        value is None or value.casefold() not in {"0", "false", "off", "no"}
    )


def _style_elements(context: AuditContext) -> dict[str, etree._Element]:
    if "word/styles.xml" not in context.package.parts:
        return {}
    root = context.package.xml("word/styles.xml")
    return {
        style_id: style
        for style in root.findall("w:style", namespaces=NS)
        if (style_id := _attr(style, "styleId"))
    }


def _effective_style(
    styles: dict[str, etree._Element], style_id: str
) -> tuple[etree._Element, ...]:
    chain: list[etree._Element] = []
    seen: set[str] = set()
    current = style_id
    while current in styles and current not in seen:
        seen.add(current)
        style = styles[current]
        chain.append(style)
        current = _attr(style.find("w:basedOn", namespaces=NS), "val") or ""
    return tuple(reversed(chain))


def _latest(
    chain: tuple[etree._Element, ...], path: str
) -> etree._Element | None:
    result = None
    for style in chain:
        candidate = style.find(path, namespaces=NS)
        if candidate is not None:
            result = candidate
    return result


def _effective_formatting_property(
    context: AuditContext,
    *,
    style_id: str | None,
    property_group: str,
    property_name: str,
    direct: etree._Element | None = None,
) -> etree._Element | None:
    styles = _style_elements(context)
    candidates: list[etree._Element] = []
    if "word/styles.xml" in context.package.parts:
        root = context.package.xml("word/styles.xml")
        default = root.find(
            f"w:docDefaults/w:{property_group}Default/"
            f"w:{property_group}/w:{property_name}",
            namespaces=NS,
        )
        if default is not None:
            candidates.append(default)
    if style_id:
        candidates.extend(
            candidate
            for style in _effective_style(styles, style_id)
            if (
                candidate := style.find(
                    f"w:{property_group}/w:{property_name}",
                    namespaces=NS,
                )
            )
            is not None
        )
    if direct is not None:
        candidates.append(direct)
    if not candidates:
        return None
    effective = etree.Element(candidates[-1].tag)
    for candidate in candidates:
        effective.attrib.update(candidate.attrib)
        for child in candidate:
            existing = effective.find(child.tag)
            if existing is not None:
                effective.remove(existing)
            effective.append(deepcopy(child))
    return effective


def _paragraph_style_id(
    context: AuditContext,
    paragraph: etree._Element,
) -> str | None:
    explicit = _attr(
        paragraph.find("w:pPr/w:pStyle", namespaces=NS),
        "val",
    )
    if explicit or "word/styles.xml" not in context.package.parts:
        return explicit
    defaults = context.package.xml("word/styles.xml").xpath(
        "./w:style[@w:type='paragraph' and @w:default='1']/@w:styleId",
        namespaces=NS,
    )
    return defaults[0] if defaults else None


def _effective_paragraph_property(
    context: AuditContext,
    paragraph: etree._Element,
    property_name: str,
) -> etree._Element | None:
    return _effective_formatting_property(
        context,
        style_id=_paragraph_style_id(context, paragraph),
        property_group="pPr",
        property_name=property_name,
        direct=paragraph.find(f"w:pPr/w:{property_name}", namespaces=NS),
    )


def _style_snapshot(
    context: AuditContext, role: str, style_id: str
) -> dict[str, object]:
    def property_value(group: str, name: str) -> etree._Element | None:
        return _effective_formatting_property(
            context,
            style_id=style_id,
            property_group=group,
            property_name=name,
        )

    spacing = property_value("pPr", "spacing")
    ind = property_value("pPr", "ind")
    fonts = property_value("rPr", "rFonts")
    size = property_value("rPr", "sz")
    line_rule = _attr(spacing, "lineRule") or "auto"
    line = _float_attr_value(spacing, "line")
    if line_rule == "exact":
        line_spacing: dict[str, object] = {
            "type": "exact",
            "value_pt": None if line is None else round(line / 20, 2),
        }
    else:
        line_spacing = {
            "type": "multiple",
            "value": None if line is None else round(line / 240, 3),
        }
    return {
        "style_id": style_id,
        "role": role,
        "paragraph": {
            "alignment": _attr(property_value("pPr", "jc"), "val"),
            "line_spacing": line_spacing,
            "space_before_pt": _pt_from_twips(_attr(spacing, "before")) or 0,
            "space_after_pt": _pt_from_twips(_attr(spacing, "after")) or 0,
            "first_line_chars": (
                float(_attr(ind, "firstLineChars")) / 100
                if _attr(ind, "firstLineChars") is not None
                else 0
            ),
            "left_indent_mm": _mm_from_twips(_attr(ind, "left")) or 0,
            "hanging_indent_mm": _mm_from_twips(_attr(ind, "hanging")) or 0,
            "keep_with_next": _on(property_value("pPr", "keepNext")),
            "page_break_before": _on(property_value("pPr", "pageBreakBefore")),
        },
        "run": {
            "font_zh": _attr(fonts, "eastAsia"),
            "font_latin": _attr(fonts, "ascii") or _attr(fonts, "hAnsi"),
            "size_pt": (
                None
                if _attr(size, "val") is None
                else float(_attr(size, "val")) / 2
            ),
            "bold": _on(property_value("rPr", "b")),
            "italic": _on(property_value("rPr", "i")),
        },
    }


def _float_attr_value(
    element: etree._Element | None, name: str
) -> float | None:
    value = _attr(element, name)
    return None if value is None else float(value)


def _expected_style_snapshot(
    context: AuditContext, role: str, style_id: str
) -> dict[str, object]:
    style = context.profile.styles[role]
    spacing = style.paragraph.line_spacing
    line_spacing: dict[str, object] = {"type": spacing.type}
    if spacing.type == "exact":
        line_spacing["value_pt"] = spacing.value_pt
    else:
        line_spacing["value"] = spacing.value
    return {
        "style_id": style_id,
        "role": role,
        "paragraph": {
            "alignment": style.paragraph.alignment,
            "line_spacing": line_spacing,
            "space_before_pt": style.paragraph.space_before_pt,
            "space_after_pt": style.paragraph.space_after_pt,
            "first_line_chars": style.paragraph.first_line_chars,
            "left_indent_mm": style.paragraph.left_indent_mm,
            "hanging_indent_mm": style.paragraph.hanging_indent_mm,
            "keep_with_next": style.paragraph.keep_with_next,
            "page_break_before": style.paragraph.page_break_before,
        },
        "run": {
            "font_zh": style.run.font_zh,
            "font_latin": style.run.font_latin,
            "size_pt": style.run.size_pt,
            "bold": style.run.bold,
            "italic": style.run.italic,
        },
    }


class PageRule:
    rule_id = "PAGE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        profile = context.profile
        body_section = _first_role_section(context, "heading_1")
        appendix_section = _first_role_section(context, "appendix_heading")
        start_values = {
            "next_page": "nextPage",
            "odd_page": "oddPage",
            "continuous": "continuous",
        }
        for index, section in enumerate(context.section_elements, start=1):
            location = f"section:{index}"
            size = section.find("w:pgSz", namespaces=NS)
            width = _mm_from_twips(_attr(size, "w"))
            height = _mm_from_twips(_attr(size, "h"))
            expected_size = {
                "width_mm": profile.page.paper.width_mm,
                "height_mm": profile.page.paper.height_mm,
            }
            actual_size = {"width_mm": width, "height_mm": height}
            if not (
                _close(width, profile.page.paper.width_mm)
                and _close(height, profile.page.paper.height_mm)
            ):
                yield AuditFinding(
                    "PAGE.PAPER.SIZE",
                    "violation",
                    location,
                    "Paper dimensions do not match the selected profile.",
                    True,
                    actual_size,
                    expected_size,
                )

            margin = section.find("w:pgMar", namespaces=NS)
            actual_margin = {
                name: _mm_from_twips(_attr(margin, name))
                for name in ("top", "bottom", "left", "right")
            }
            expected_margin = {
                "top": profile.page.body.top_mm,
                "bottom": profile.page.body.bottom_mm,
                "left": profile.page.body.left_mm,
                "right": profile.page.body.right_mm,
            }
            if any(
                not _close(actual_margin[name], expected_margin[name])
                for name in expected_margin
            ):
                yield AuditFinding(
                    "PAGE.MARGIN.BODY",
                    "violation",
                    location,
                    "Body margins do not match the selected profile.",
                    True,
                    actual_margin,
                    expected_margin,
                )

            distances = {
                "header": _mm_from_twips(_attr(margin, "header")),
                "footer": _mm_from_twips(_attr(margin, "footer")),
            }
            expected_distances = {
                "header": profile.page.header_distance_mm,
                "footer": profile.page.footer_distance_mm,
            }
            if any(
                not _close(distances[name], expected_distances[name])
                for name in distances
            ):
                yield AuditFinding(
                    "PAGE.HEADER_FOOTER_DISTANCE",
                    "violation",
                    location,
                    "Header or footer distance does not match the profile.",
                    True,
                    distances,
                    expected_distances,
                )

            section_type = section.find("w:type", namespaces=NS)
            actual_start = _attr(section_type, "val") or "nextPage"
            expected_start = None
            if index > 1 and index == appendix_section:
                expected_start = start_values[
                    profile.page.section_start.major_back_matter
                ]
            elif index > 1 and index == body_section:
                expected_start = start_values[profile.page.section_start.body]
            if expected_start is not None and actual_start != expected_start:
                yield AuditFinding(
                    "PAGE.SECTION.START",
                    "violation",
                    location,
                    "Section start does not match the selected profile.",
                    True,
                    actual_start,
                    expected_start,
                )

class SemanticRule:
    rule_id = "SEMANTIC"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        for node in context.semantic.paragraphs:
            if "ROLE.SKIPPED_HEADING_LEVEL" in node.warnings:
                yield AuditFinding(
                    "STYLE.HEADING.HIERARCHY",
                    "violation",
                    node.location,
                    "Heading hierarchy skips a level.",
                    False,
                    node.role,
                    None,
                )
            if "ROLE.CONFLICT" in node.warnings:
                yield AuditFinding(
                    "SEMANTIC.ROLE_CONFLICT",
                    "warning",
                    node.location,
                    "Paragraph role evidence conflicts and requires review.",
                    False,
                    "conflicting evidence",
                    None,
                )
            elif "ROLE.AMBIGUOUS" in node.warnings:
                yield AuditFinding(
                    "SEMANTIC.AMBIGUOUS_ROLE",
                    "warning",
                    node.location,
                    "Paragraph role is ambiguous and requires review.",
                    False,
                    "ambiguous",
                    None,
                )


class StyleRule:
    rule_id = "STYLE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        checked: set[str] = set()
        available_styles = _style_elements(context)
        for node in context.semantic.paragraphs:
            role = _style_role_for_id(context, node.style_id)
            if (
                role is None
                or node.style_id is None
                or node.style_id in checked
                or node.style_id not in available_styles
            ):
                continue
            checked.add(node.style_id)
            actual = _style_snapshot(context, role, node.style_id)
            expected = _expected_style_snapshot(context, role, node.style_id)
            if actual != expected:
                yield AuditFinding(
                    "STYLE.DEFINITION",
                    "violation",
                    "part:word/styles.xml",
                    "Profile style definition contains incorrect formatting.",
                    True,
                    actual,
                    expected,
                )

        for node, paragraph in zip(
            context.semantic.paragraphs,
            context.paragraph_elements,
            strict=True,
        ):
            if node.role is None:
                continue
            expected_names = list(context.profile.styles[node.role].word_styles)
            if not _style_role_matches(context, node.role, node.style_id):
                yield AuditFinding(
                    "STYLE.ROLE.MAPPING",
                    "violation",
                    node.location,
                    "Paragraph does not use the profile style for its semantic role.",
                    node.repairable,
                    node.style_id,
                    expected_names,
                )
            direct_p = paragraph.xpath(
                "./w:pPr/*[not(self::w:pStyle or self::w:numPr or self::w:sectPr)]",
                namespaces=NS,
            )
            direct_r = paragraph.xpath("./w:r/w:rPr/*", namespaces=NS)
            if direct_p or direct_r:
                yield AuditFinding(
                    "STYLE.DIRECT_FORMATTING",
                    "warning",
                    node.location,
                    "Direct formatting may override the selected profile style.",
                    True,
                    {
                        "paragraph_properties": len(direct_p),
                        "run_properties": len(direct_r),
                    },
                    {"paragraph_properties": 0, "run_properties": 0},
                )


class NumberingRule:
    rule_id = "NUMBERING"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        for node, paragraph in zip(
            context.semantic.paragraphs,
            context.paragraph_elements,
            strict=True,
        ):
            has_numbering = _has_heading_numbering(context, node, paragraph)
            has_sequence = _has_caption_numbering(context, node)
            if node.role in {"figure_caption", "table_caption"}:
                if not has_sequence:
                    yield AuditFinding(
                        "NUMBERING.MANUAL_CAPTION",
                        "violation",
                        node.location,
                        "Caption number is typed manually instead of generated.",
                        True,
                        node.manual_number_token or "static caption label",
                        "chapter-based automatic caption fields",
                    )
                continue
            if not node.manual_number_token:
                continue
            if node.role in {"heading_1", "heading_2", "heading_3"} and not (
                has_numbering
            ):
                yield AuditFinding(
                    "NUMBERING.MANUAL_HEADING",
                    "violation",
                    node.location,
                    "Heading number is typed manually instead of generated.",
                    True,
                    node.manual_number_token,
                    "automatic numbering",
                )
            elif node.role == "appendix_heading" and not (
                has_numbering
            ):
                yield AuditFinding(
                    "NUMBERING.MANUAL_APPENDIX",
                    "violation",
                    node.location,
                    "Appendix label is typed manually instead of generated.",
                    True,
                    node.manual_number_token,
                    "automatic appendix numbering",
                )


def _has_heading_numbering(
    context: AuditContext,
    node,
    paragraph: etree._Element,
) -> bool:
    num_pr = _effective_paragraph_property(context, paragraph, "numPr")
    num_ids = (
        num_pr.xpath("./w:numId/@w:val", namespaces=NS)
        if num_pr is not None
        else ()
    )
    if (
        not num_ids
        or num_ids[0] == "0"
        or "word/numbering.xml" not in context.package.parts
    ):
        return False
    levels = (
        num_pr.xpath("./w:ilvl/@w:val", namespaces=NS)
        if num_pr is not None
        else ()
    )
    try:
        level = int(levels[0]) if levels else 0
    except ValueError:
        return False
    expected_level = {
        "heading_1": 0,
        "heading_2": 1,
        "heading_3": 2,
        "appendix_heading": 0,
    }.get(node.role)
    if expected_level != level:
        return False
    numbering = context.package.xml("word/numbering.xml")
    num_nodes = numbering.xpath(
        f"./w:num[@w:numId='{num_ids[0]}']",
        namespaces=NS,
    )
    if not num_nodes:
        return False
    num_node = num_nodes[0]
    overridden_levels = num_node.xpath(
        f"./w:lvlOverride[@w:ilvl='{level}']/w:lvl",
        namespaces=NS,
    )
    if overridden_levels:
        level_node = overridden_levels[0]
    else:
        abstract_ids = num_node.xpath(
            "./w:abstractNumId/@w:val",
            namespaces=NS,
        )
        if not abstract_ids:
            return False
        level_nodes = numbering.xpath(
            f"./w:abstractNum[@w:abstractNumId='{abstract_ids[0]}']"
            f"/w:lvl[@w:ilvl='{level}']",
            namespaces=NS,
        )
        if not level_nodes:
            return False
        level_node = level_nodes[0]

    profile_rule = {
        "heading_1": context.profile.numbering.chapters,
        "heading_2": context.profile.numbering.sections,
        "heading_3": context.profile.numbering.sections,
        "appendix_heading": context.profile.numbering.appendices,
    }[node.role]
    expected_formats = {
        "chinese_chapter": {"chineseCounting"},
        "decimal": {"decimal"},
        "upper_alpha": {"upperLetter"},
    }
    number_format = _attr(level_node.find("w:numFmt", namespaces=NS), "val")
    if number_format not in expected_formats.get(profile_rule.format, set()):
        return False
    level_text = _attr(level_node.find("w:lvlText", namespaces=NS), "val")
    suffix = {
        "space": " ",
        "tab": "\t",
        "nothing": "",
    }.get(_attr(level_node.find("w:suff", namespaces=NS), "val"), "\t")
    expected_core = {
        "chinese_chapter": "第%1章",
        "upper_alpha": "附录 %1",
        "decimal": profile_rule.separator.join(
            f"%{index}" for index in range(1, level + 2)
        ),
    }.get(profile_rule.format)
    if profile_rule.format == "decimal":
        text_matches = level_text == expected_core
    else:
        text_matches = (
            level_text == f"{expected_core}{profile_rule.separator}"
            or (
                level_text == expected_core
                and suffix == profile_rule.separator
            )
        )
    if not text_matches:
        return False
    restart_value = _attr(
        level_node.find("w:lvlRestart", namespaces=NS),
        "val",
    )
    if profile_rule.restart_scope == "document":
        if restart_value not in {None, "0"}:
            return False
    elif profile_rule.restart_scope == "chapter":
        if level == 0 or restart_value not in {None, "1"}:
            return False
    elif profile_rule.restart_scope == "appendix":
        if restart_value is None:
            return False
    else:
        return False
    style_ids = level_node.xpath("./w:pStyle/@w:val", namespaces=NS)
    style_matches = bool(
        style_ids
        and any(
            style_ids[0].casefold() == name.casefold()
            for name in context.profile.styles[node.role].word_styles
        )
    )
    outline_values = paragraph.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=NS)
    outline_matches = bool(
        outline_values and outline_values[0] == str(expected_level)
    )
    abstract = level_node.getparent()
    if etree.QName(abstract).localname == "lvlOverride":
        abstract_ids = num_node.xpath(
            "./w:abstractNumId/@w:val",
            namespaces=NS,
        )
        abstracts = (
            numbering.xpath(
                f"./w:abstractNum[@w:abstractNumId='{abstract_ids[0]}']",
                namespaces=NS,
            )
            if abstract_ids
            else ()
        )
        abstract = abstracts[0] if abstracts else abstract
    multi_types = abstract.xpath("./w:multiLevelType/@w:val", namespaces=NS)
    multilevel_matches = bool(
        multi_types
        and multi_types[0] in {"multilevel", "hybridMultilevel"}
        and _style_role_matches(context, node.role, node.style_id)
    )
    return style_matches or outline_matches or multilevel_matches


def _has_caption_numbering(context: AuditContext, node) -> bool:
    if node.role not in {"figure_caption", "table_caption"}:
        return False
    label = "figure" if node.role == "figure_caption" else "table"
    localized_label = "图" if label == "figure" else "表"
    fields = tuple(re.sub(r"\s+", " ", field).strip() for field in node.fields)
    sequence_fields = tuple(
        field
        for field in fields
        if re.match(
            rf"^SEQ\s+({label}|{localized_label})\b",
            field,
            re.IGNORECASE,
        )
    )
    if not sequence_fields:
        return False
    has_restarting_sequence = any(
        re.search(r"\\s\s+1\b", field, re.IGNORECASE)
        for field in sequence_fields
    )
    profile_rule = (
        context.profile.numbering.figures
        if label == "figure"
        else context.profile.numbering.tables
    )
    restart_matches = {
        "document": not has_restarting_sequence,
        "chapter": has_restarting_sequence,
        "appendix": has_restarting_sequence,
    }.get(profile_rule.restart_scope, False)
    reference_fields = tuple(
        field for field in fields if re.match(r"^STYLEREF\b", field, re.IGNORECASE)
    )
    reference_role = {
        "chapter": "heading_1",
        "appendix": "appendix_heading",
    }.get(profile_rule.restart_scope)
    expected_styles = (
        {
            name.casefold()
            for name in context.profile.styles[reference_role].word_styles
        }
        if reference_role is not None
        else set()
    )
    has_scope_reference = any(
        (
            match := re.match(
                r"^STYLEREF\s+\"?([^\"\\]+?)\"?(?:\s+\\|$)",
                field,
                re.IGNORECASE,
            )
        )
        and match.group(1).strip().casefold() in expected_styles
        for field in reference_fields
    )
    reference_matches = (
        not reference_fields
        if profile_rule.restart_scope == "document"
        else has_scope_reference
    )
    number_pairs = re.findall(
        r"(?<!\w)(?:\d+|[A-Z]+|[一二三四五六七八九十百千]+)"
        r"([-.、])\d+(?!\w)",
        node.raw_text,
        re.IGNORECASE,
    )
    separator_matches = (
        len(number_pairs) == 1
        and number_pairs[0] == profile_rule.separator
    )
    return restart_matches and reference_matches and separator_matches


class FieldRule:
    rule_id = "FIELD"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        fields = tuple(
            (node.location, occurrence, field)
            for node in (
                *context.semantic.paragraphs,
                *context.semantic.headers,
                *context.semantic.footers,
            )
            for occurrence, field in enumerate(node.fields, start=1)
        )
        normalized = tuple(
            re.sub(r"\s+", " ", code).strip() for _, _, code in fields
        )
        required = (
            (
                "FIELD.TOC.REQUIRED",
                context.profile.fields.toc.required,
                context.profile.fields.toc.field_code,
            ),
            (
                "FIELD.LIST_OF_FIGURES.REQUIRED",
                context.profile.fields.list_of_figures.required,
                context.profile.fields.list_of_figures.field_code,
            ),
            (
                "FIELD.LIST_OF_TABLES.REQUIRED",
                context.profile.fields.list_of_tables.required,
                context.profile.fields.list_of_tables.field_code,
            ),
        )
        for rule_id, is_required, field_code in required:
            if not is_required:
                continue
            expected = re.sub(r"\s+", " ", field_code).strip()
            if not any(code.casefold() == expected.casefold() for code in normalized):
                yield AuditFinding(
                    rule_id,
                    "violation",
                    "document",
                    "Required generated field is missing.",
                    True,
                    False,
                    expected,
                )

        bookmarks = set(context.semantic.bookmarks)
        for location, occurrence, field in fields:
            match = re.match(r"^(?:REF|PAGEREF)\s+(\S+)", field, re.IGNORECASE)
            if (
                context.profile.fields.cross_references.require_existing_target
                and match
                and match.group(1) not in bookmarks
            ):
                target_digest = hashlib.sha256(
                    match.group(1).encode("utf-8")
                ).hexdigest()
                yield AuditFinding(
                    "FIELD.CROSS_REFERENCE.TARGET",
                    "error",
                    location,
                    "Cross-reference target does not exist.",
                    True,
                    {
                        "field_occurrence": occurrence,
                        "missing_target_sha256": target_digest,
                    },
                    "existing bookmark",
                )


class FigureRule:
    rule_id = "FIGURE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        for index, paragraph in enumerate(context.paragraph_elements, start=1):
            if not paragraph.xpath(".//w:drawing", namespaces=NS):
                continue
            location = f"paragraph:{index}"
            extents = paragraph.xpath(".//wp:extent", namespaces=NS)
            widths = [
                round(float(extent.get("cx", "0")) / 36000, 2)
                for extent in extents
            ]
            if widths and max(widths) > context.profile.figures.max_width_mm + 0.15:
                yield AuditFinding(
                    "FIGURE.DIMENSIONS.MAX_WIDTH",
                    "violation",
                    location,
                    "Figure exceeds the maximum profile width.",
                    True,
                    max(widths),
                    context.profile.figures.max_width_mm,
                )
            justification = (
                _attr(
                    _effective_paragraph_property(context, paragraph, "jc"),
                    "val",
                )
                or "left"
            )
            if justification != context.profile.figures.alignment:
                yield AuditFinding(
                    "FIGURE.ALIGNMENT",
                    "violation",
                    location,
                    "Figure alignment does not match the profile.",
                    True,
                    justification,
                    context.profile.figures.alignment,
                )
            caption_index = (
                index - 1
                if context.profile.figures.caption_position == "above"
                else index + 1
            )
            caption = (
                context.semantic.paragraphs[caption_index - 1]
                if 1 <= caption_index <= len(context.semantic.paragraphs)
                else None
            )
            if caption is None or caption.role != "figure_caption":
                position = context.profile.figures.caption_position
                yield AuditFinding(
                    "FIGURE.CAPTION.POSITION",
                    "violation",
                    location,
                    f"Figure must have a caption immediately {position} it.",
                    True,
                    False,
                    f"caption {position}",
                )


class TableRule:
    rule_id = "TABLE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        body_children = [
            child
            for child in context.document_root.find("w:body", namespaces=NS)
            if isinstance(child.tag, str)
        ]
        semantic_by_paragraph = {
            id(paragraph): node
            for paragraph, node in zip(
                context.paragraph_elements,
                context.semantic.paragraphs,
                strict=True,
            )
        }
        table_number = 0
        for child_index, table in enumerate(body_children):
            if etree.QName(table).localname != "tbl":
                continue
            table_number += 1
            location = f"table:{table_number}"
            position = context.profile.tables.caption_position
            caption_index = (
                child_index - 1 if position == "above" else child_index + 1
            )
            caption_element = (
                body_children[caption_index]
                if 0 <= caption_index < len(body_children)
                else None
            )
            caption_node = (
                semantic_by_paragraph.get(id(caption_element))
                if caption_element is not None
                and etree.QName(caption_element).localname == "p"
                else None
            )
            if caption_node is None or caption_node.role != "table_caption":
                yield AuditFinding(
                    "TABLE.CAPTION.POSITION",
                    "violation",
                    location,
                    f"Table must have a caption immediately {position} it.",
                    True,
                    False,
                    f"caption {position}",
                )

            first_row = table.find("w:tr", namespaces=NS)
            repeat_header = (
                first_row is not None
                and _on(
                    first_row.find("w:trPr/w:tblHeader", namespaces=NS)
                )
            )
            if context.profile.tables.repeat_header and not repeat_header:
                yield AuditFinding(
                    "TABLE.REPEAT_HEADER",
                    "violation",
                    location,
                    "Table header row is not configured to repeat.",
                    True,
                    False,
                    True,
                )
            splittable_rows = sum(
                not _on(row.find("w:trPr/w:cantSplit", namespaces=NS))
                for row in table.findall("w:tr", namespaces=NS)
            )
            if not context.profile.tables.allow_row_split and splittable_rows:
                yield AuditFinding(
                    "TABLE.ROW_SPLIT",
                    "violation",
                    location,
                    "Table rows are allowed to split across pages.",
                    True,
                    splittable_rows,
                    0,
                )
            borders = table.find("w:tblPr/w:tblBorders", namespaces=NS)
            def visible_border(element: etree._Element | None) -> bool:
                return element is not None and _attr(element, "val") not in {
                    None,
                    "nil",
                    "none",
                }

            header_cells = (
                first_row.findall("w:tc", namespaces=NS)
                if first_row is not None
                else ()
            )
            has_header_bottom = (
                borders is not None
                and visible_border(borders.find("w:insideH", namespaces=NS))
            ) or (
                bool(header_cells)
                and all(
                    visible_border(
                        cell.find("w:tcPr/w:tcBorders/w:bottom", namespaces=NS)
                    )
                    for cell in header_cells
                )
            )
            has_three_line = (
                borders is not None
                and visible_border(borders.find("w:top", namespaces=NS))
                and visible_border(borders.find("w:bottom", namespaces=NS))
                and has_header_bottom
                and not any(
                    visible_border(borders.find(f"w:{name}", namespaces=NS))
                    for name in (
                        "left",
                        "right",
                        "start",
                        "end",
                        "insideV",
                    )
                )
            )
            if (
                context.profile.tables.border_model == "three_line"
                and not has_three_line
            ):
                yield AuditFinding(
                    "TABLE.BORDERS.THREE_LINE",
                    "violation",
                    location,
                    "Table does not use the required three-line border model.",
                    True,
                    "other",
                    "three_line",
                )


class ReferenceRule:
    rule_id = "REFERENCE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        expected = context.profile.references
        for node, paragraph in zip(
            context.semantic.paragraphs,
            context.paragraph_elements,
            strict=True,
        ):
            if node.role != "reference":
                continue
            spacing = _effective_paragraph_property(
                context,
                paragraph,
                "spacing",
            )
            ind = _effective_paragraph_property(context, paragraph, "ind")
            line_rule = _attr(spacing, "lineRule") or "auto"
            line = _float_attr_value(spacing, "line")
            actual = {
                "line_spacing": (
                    {
                        "type": "exact",
                        "value_pt": None if line is None else round(line / 20, 2),
                    }
                    if line_rule == "exact"
                    else {
                        "type": "multiple",
                        "value": None if line is None else round(line / 240, 3),
                    }
                ),
                "space_before_pt": _pt_from_twips(_attr(spacing, "before")) or 0,
                "space_after_pt": _pt_from_twips(_attr(spacing, "after")) or 0,
                "hanging_indent_mm": _mm_from_twips(_attr(ind, "hanging")) or 0,
            }
            wanted = {
                "line_spacing": {
                    "type": "exact",
                    "value_pt": expected.line_spacing_pt,
                },
                "space_before_pt": expected.space_before_pt,
                "space_after_pt": expected.space_after_pt,
                "hanging_indent_mm": expected.hanging_indent_mm,
            }
            if (
                actual["line_spacing"] != wanted["line_spacing"]
                or any(
                    not _close(actual[key], value)
                    for key, value in wanted.items()
                    if key != "line_spacing"
                )
            ):
                yield AuditFinding(
                    "REFERENCE.PARAGRAPH_FORMAT",
                    "violation",
                    node.location,
                    "Reference spacing or hanging indent does not match the profile.",
                    True,
                    actual,
                    wanted,
                )


class HeaderFooterRule:
    rule_id = "HEADER.FOOTER"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        body_paragraph = next(
            (
                int(node.location.split(":")[1])
                for node in context.semantic.paragraphs
                if node.role == "heading_1"
            ),
            None,
        )
        body_section = _first_role_section(context, "heading_1")
        appendix_section = _first_role_section(context, "appendix_heading")
        front_section = _first_numbered_front_section(context, body_paragraph)
        header_targets = _effective_story_targets(context, "header")
        footer_targets = _effective_story_targets(context, "footer")
        for index, section in enumerate(context.section_elements, start=1):
            location = f"section:{index}"
            region = _section_region(index, body_section, appendix_section)
            region_profile = getattr(context.profile.headers_footers, region)
            front_part = (
                _front_part_for_section(context, index, body_paragraph)
                if region == "front_matter"
                else None
            )
            header_enabled = region_profile.header_enabled and (
                front_part is None or front_part.show_header
            )
            page_number_enabled = region_profile.page_number_enabled and (
                front_part is None or front_part.page_number_style != "none"
            )
            linking = context.profile.headers_footers.section_linking
            link_headers = {
                "front_matter": False,
                "body": linking.link_body_headers,
                "appendix": linking.link_appendix_headers,
            }[region] and header_enabled
            link_footers = {
                "front_matter": False,
                "body": linking.link_body_footers,
                "appendix": linking.link_appendix_footers,
            }[region] and page_number_enabled
            broken_links: list[str] = []
            if (
                index > 1
                and link_headers
                and header_targets[index - 1] != header_targets[index - 2]
            ):
                broken_links.append("header")
            if (
                index > 1
                and link_footers
                and footer_targets[index - 1] != footer_targets[index - 2]
            ):
                broken_links.append("footer")
            if broken_links:
                yield AuditFinding(
                    "HEADER.FOOTER.LINKING",
                    "warning",
                    location,
                    "Header or footer relationship target breaks required section linking.",
                    True,
                    broken_links,
                    "linked to previous",
                )

            header_target = header_targets[index - 1]
            header_paragraphs = tuple(
                node
                for node in context.semantic.headers
                if node.part_name == header_target
            )
            if header_enabled and not header_paragraphs:
                yield AuditFinding(
                    "HEADER.FOOTER.HEADER_REQUIRED",
                    "violation",
                    location,
                    "No generated thesis header was found for this section.",
                    True,
                    False,
                    True,
                )
            elif header_enabled:
                source = region_profile.header_source
                dynamic_roles = {
                    "current_front_heading": "front_heading",
                    "current_heading_1": "heading_1",
                    "current_appendix": "appendix_heading",
                    "current_appendix_heading": "appendix_heading",
                }
                source_matches = True
                if source in dynamic_roles:
                    expected_styles = {
                        name.casefold()
                        for name in context.profile.styles[
                            dynamic_roles[source]
                        ].word_styles
                    }
                    source_matches = any(
                        _styleref_targets(field, expected_styles)
                        for node in header_paragraphs
                        for field in node.fields
                    )
                elif source in {"fixed", "fixed_text"}:
                    expected_text = re.sub(
                        r"\s+", " ", region_profile.header_text or ""
                    ).strip()
                    source_matches = any(
                        re.sub(r"\s+", " ", node.raw_text).strip()
                        == expected_text
                        for node in header_paragraphs
                    )
                elif source == "none":
                    source_matches = False
                if not source_matches:
                    yield AuditFinding(
                        "HEADER.FOOTER.HEADER_SOURCE",
                        "violation",
                        location,
                        "Header content does not match the configured source.",
                        True,
                        "missing or unrelated header source",
                        source,
                    )

            footer_target = footer_targets[index - 1]
            footer_paragraphs = tuple(
                node
                for node in context.semantic.footers
                if node.part_name == footer_target
            )
            page_paragraphs = tuple(
                node
                for node in footer_paragraphs
                if any(
                    re.match(r"^PAGE(?:\s|$)", field, re.IGNORECASE)
                    for field in node.fields
                )
            )
            if page_number_enabled and not footer_paragraphs:
                yield AuditFinding(
                    "HEADER.FOOTER.FOOTER_REQUIRED",
                    "violation",
                    location,
                    "No thesis footer was found for this section.",
                    True,
                    False,
                    True,
                )
            if page_number_enabled and not page_paragraphs:
                yield AuditFinding(
                    "HEADER.FOOTER.PAGE_NUMBER",
                    "violation",
                    location,
                    "No generated page-number field was found for this section.",
                    True,
                    False,
                    True,
                )

            page_number = section.find("w:pgNumType", namespaces=NS)
            if body_section is not None and index == body_section:
                expected_start = context.profile.fields.page_number.body_start
            elif front_section is not None and index == front_section:
                expected_start = context.profile.fields.page_number.front_start
            else:
                expected_start = None
            actual_start = _attr(page_number, "start")
            if page_number_enabled and (
                (
                    expected_start is not None
                    and actual_start != str(expected_start)
                )
                or (
                    expected_start is None
                    and (
                        (front_section is None or index < front_section)
                        and (body_section is None or index < body_section)
                    )
                    and actual_start is not None
                )
            ):
                yield AuditFinding(
                    "HEADER.FOOTER.PAGE_RESET",
                    "violation",
                    location,
                    "Page numbering must reset at the configured region start.",
                    True,
                    actual_start,
                    expected_start,
                )
            page_number_style = (
                front_part.page_number_style
                if front_part is not None
                else region_profile.page_number_style
            )
            expected_format = {
                "none": None,
                "upper_roman": "upperRoman",
                "decimal": "decimal",
            }[page_number_style]
            actual_format = _attr(page_number, "fmt")
            if page_number_enabled and actual_format != expected_format:
                yield AuditFinding(
                    "HEADER.FOOTER.PAGE_STYLE",
                    "violation",
                    location,
                    "Page-number style does not match the section region.",
                    True,
                    actual_format,
                    expected_format,
                )

            if page_number_enabled and page_paragraphs:
                expected_alignment = region_profile.page_number_alignment
                actual_alignments = tuple(
                    _story_paragraph_alignment(context, node)
                    for node in page_paragraphs
                )
                if expected_alignment not in actual_alignments:
                    yield AuditFinding(
                        "HEADER.FOOTER.PAGE_ALIGNMENT",
                        "violation",
                        location,
                        "Page-number alignment does not match the profile.",
                        True,
                        list(actual_alignments),
                        expected_alignment,
                    )


def _first_numbered_front_section(
    context: AuditContext, body_paragraph: int | None
) -> int | None:
    numbered_roles = {
        part.heading_role
        for part in context.profile.front_matter.parts
        if part.page_number_style != "none"
    }
    for node in context.semantic.paragraphs:
        paragraph_number = int(node.location.split(":")[1])
        if body_paragraph is not None and paragraph_number >= body_paragraph:
            break
        if node.role in numbered_roles or any(
            _style_role_matches(context, role, node.style_id)
            for role in numbered_roles
        ):
            return _section_for_paragraph(context, paragraph_number)
    return None


def _front_part_for_section(
    context: AuditContext,
    section_number: int,
    body_paragraph: int | None,
):
    nodes = tuple(
        node
        for node in context.semantic.paragraphs
        if (
            body_paragraph is None
            or int(node.location.split(":")[1]) < body_paragraph
        )
        and _section_for_paragraph(
            context, int(node.location.split(":")[1])
        )
        == section_number
    )
    return next(
        (
            part
            for part in context.profile.front_matter.parts
            if any(
                node.role == part.heading_role
                or _style_role_matches(
                    context, part.heading_role, node.style_id
                )
                for node in nodes
            )
        ),
        None,
    )


def _effective_story_targets(
    context: AuditContext, kind: str
) -> tuple[str | None, ...]:
    relationship_by_id = {
        relationship.id: resolve_relationship_target(
            relationship.source_part, relationship.target
        )
        for relationship in context.semantic.relationships
        if relationship.source_part == "word/document.xml"
        and relationship.type.rsplit("/", 1)[-1] == kind
        and relationship.target_mode != "External"
    }
    current: str | None = None
    targets: list[str | None] = []
    for section in context.section_elements:
        references = section.findall(f"w:{kind}Reference", namespaces=NS)
        default_reference = next(
            (
                reference
                for reference in references
                if (_attr(reference, "type") or "default") == "default"
            ),
            references[0] if references else None,
        )
        if default_reference is not None:
            relationship_id = default_reference.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            current = relationship_by_id.get(relationship_id)
        targets.append(current)
    return tuple(targets)


def _story_paragraph_alignment(context: AuditContext, node) -> str:
    paragraph_number = int(node.location.rsplit(":", 1)[1])
    root = context.package.xml(node.part_name)
    paragraphs = root.xpath(".//w:p", namespaces=NS)
    paragraph = paragraphs[paragraph_number - 1]
    return (
        _attr(_effective_paragraph_property(context, paragraph, "jc"), "val")
        or "left"
    )


def _styleref_targets(field: str, expected_styles: set[str]) -> bool:
    normalized = re.sub(r"\s+", " ", field).strip()
    match = re.match(
        r'^STYLEREF\s+"?([^"\\]+?)"?(?:\s+\\|$)',
        normalized,
        re.IGNORECASE,
    )
    return bool(
        match and match.group(1).strip().casefold() in expected_styles
    )


class PrivacyRule:
    rule_id = "PRIVACY"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        for node in (
            *context.semantic.paragraphs,
            *context.semantic.headers,
            *context.semantic.footers,
        ):
            text = node.raw_text
            for pattern in context.profile.privacy.generic_patterns:
                flags = re.NOFLAG
                for flag, value in {
                    "i": re.IGNORECASE,
                    "m": re.MULTILINE,
                    "u": re.UNICODE,
                }.items():
                    if flag in pattern.flags:
                        flags |= value
                if re.search(pattern.regex, text, flags):
                    yield AuditFinding(
                        f"PRIVACY.PATTERN.{pattern.id.upper().replace('-', '_')}",
                        "error",
                        node.location,
                        "Potential private value was found and redacted.",
                        True,
                        "[REDACTED]",
                        None,
                    )
            if any(
                re.search(pattern, text, re.IGNORECASE)
                for pattern in context.profile.privacy.unresolved_placeholder_patterns
            ):
                yield AuditFinding(
                    "PRIVACY.UNRESOLVED_PLACEHOLDER",
                    "warning",
                    node.location,
                    "Unresolved placeholder was found and redacted.",
                    True,
                    "[REDACTED]",
                    None,
                )

        metadata_parts = (
            ("docProps/core.xml", {CP_NS, DC_NS}),
            ("docProps/app.xml", {EP_NS}),
        )
        forbidden = {
            name.casefold()
            for name in context.profile.privacy.forbidden_metadata_keys
        }
        for part_name, namespaces in metadata_parts:
            if part_name not in context.package.parts:
                continue
            root = context.package.xml(part_name)
            for element in root.iter():
                if not isinstance(element.tag, str) or not (element.text or "").strip():
                    continue
                tag = etree.QName(element)
                if tag.namespace in namespaces and tag.localname.casefold() in forbidden:
                    yield AuditFinding(
                        "PRIVACY.METADATA",
                        "error",
                        f"part:{part_name}",
                        "Forbidden document metadata was found and redacted.",
                        True,
                        {
                            "metadata_key": tag.localname,
                            "value": "[REDACTED]",
                        },
                        None,
                    )


DEFAULT_RULES = RuleRegistry(
    (
        PageRule(),
        SemanticRule(),
        StyleRule(),
        NumberingRule(),
        FieldRule(),
        FigureRule(),
        TableRule(),
        ReferenceRule(),
        HeaderFooterRule(),
        PrivacyRule(),
    )
)


def _context(path: Path, profile: FormatProfile) -> AuditContext:
    package = OoxmlPackage.open(path)
    root = package.xml("word/document.xml")
    body = root.find("w:body", namespaces=NS)
    if body is None:
        raise ValueError("word/document.xml has no body")
    return AuditContext(
        path=path,
        profile=profile,
        package=package,
        semantic=inspect_document(path, profile),
        document_root=root,
        paragraph_elements=tuple(body.xpath(".//w:p", namespaces=NS)),
        table_elements=tuple(body.xpath(".//w:tbl", namespaces=NS)),
        section_elements=tuple(root.xpath(".//w:sectPr", namespaces=NS)),
    )


def _created_at(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None:
        raise ValueError("injected clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def audit_document(
    path: str | Path,
    profile: FormatProfile,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    registry: RuleRegistry = DEFAULT_RULES,
    input_name: str | None = None,
) -> dict[str, object]:
    """Audit a DOCX and return the exact Task 2 audit contract."""

    document_path = Path(path)
    context = _context(document_path, profile)
    raw_findings = registry.audit(context)
    findings: list[dict[str, object]] = [
        {
            "finding_id": "",
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "location": finding.location,
            "message": finding.message,
            "repairable": finding.repairable,
            "repaired": finding.repaired,
            "before": finding.before,
            "after": finding.after,
        }
        for finding in raw_findings
    ]
    digests = [_finding_digest("1.0", finding) for finding in findings]
    if len(set(digests)) != len(digests):
        raise ValueError("audit rules produced duplicate semantic findings")
    for finding, finding_id in zip(
        findings, shortest_unique_digest_prefixes(digests), strict=True
    ):
        finding["finding_id"] = finding_id
    findings.sort(
        key=lambda finding: (
            _location_key(str(finding["location"])),
            SEVERITY_ORDER[str(finding["severity"])],
            str(finding["rule_id"]),
            str(finding["finding_id"]),
        )
    )
    counts = Counter(str(finding["severity"]) for finding in findings)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "tool_version": __version__,
        "created_at": _created_at(clock),
        "document_sha256": hashlib.sha256(document_path.read_bytes()).hexdigest(),
        "input": input_name or document_path.name,
        "profile": profile.profile.id,
        "summary": {
            "errors": counts["error"],
            "violations": counts["violation"],
            "warnings": counts["warning"],
        },
        "findings": findings,
    }
    validate_audit(report)
    return report


def _redact_text(rendered: str) -> str:
    rendered = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[REDACTED]",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(r"\b\d{8,14}\b", "[REDACTED]", rendered)
    rendered = re.sub(
        r"\{\{[^{}]+\}\}|\[[A-Z_]+\]|\b(?:TODO|TBD)\b",
        "[REDACTED]",
        rendered,
    )
    return rendered


def _redacted_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, str) and value == "[REDACTED]":
        return value
    rendered = _redact_text(
        value if isinstance(value, str) else canonical_json(value).strip()
    )
    return _markdown_cell(rendered)


def _markdown_cell(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def render_audit_markdown(report: dict[str, object]) -> str:
    """Render a deterministic Markdown summary without exposing matched secrets."""

    validate_audit(report)
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Thesis formatting audit",
        "",
        f"- Profile: `{report['profile']}`",
        f"- Document SHA-256: `{report['document_sha256']}`",
        f"- Errors: {summary['errors']}",
        f"- Violations: {summary['violations']}",
        f"- Warnings: {summary['warnings']}",
        "",
        "| Severity | Rule | Location | Message | Before | After |",
        "|---|---|---|---|---|---|",
    ]
    findings = report["findings"]
    assert isinstance(findings, list)
    for finding in findings:
        assert isinstance(finding, dict)
        lines.append(
            "| {severity} | `{rule_id}` | `{location}` | {message} | {before} | {after} |".format(
                severity=finding["severity"],
                rule_id=finding["rule_id"],
                location=finding["location"],
                message=_markdown_cell(_redact_text(str(finding["message"]))),
                before=_redacted_value(finding["before"]),
                after=_redacted_value(finding["after"]),
            )
        )
    return "\n".join(lines) + "\n"


audit_to_markdown = render_audit_markdown
audit = audit_document
to_markdown = render_audit_markdown
DEFAULT_REGISTRY = DEFAULT_RULES


__all__ = [
    "AuditContext",
    "AuditFinding",
    "AuditRule",
    "DEFAULT_REGISTRY",
    "DEFAULT_RULES",
    "Rule",
    "RuleRegistry",
    "audit",
    "audit_document",
    "audit_to_markdown",
    "render_audit_markdown",
    "to_markdown",
]
