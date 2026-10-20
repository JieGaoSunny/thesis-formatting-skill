"""Deterministic, read-only auditing of thesis DOCX formatting."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
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
from thesis_format.ooxml import OoxmlPackage
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


def _all_fields(context: AuditContext) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    for node in (
        *context.semantic.paragraphs,
        *context.semantic.headers,
        *context.semantic.footers,
    ):
        fields.extend((node.location, field) for field in node.fields)
    return tuple(fields)


def _style_role_matches(context: AuditContext, role: str, style_id: str | None) -> bool:
    if style_id is None:
        return False
    style = context.profile.styles[role]
    names = {name.casefold() for name in style.word_styles}
    return style_id.casefold() in names


def _section_for_paragraph(context: AuditContext, paragraph_number: int) -> int:
    section_number = 1
    for index, section in enumerate(context.semantic.sections, start=1):
        if section.start_paragraph <= paragraph_number:
            section_number = index
        else:
            break
    return section_number


def _on(element: etree._Element | None) -> bool:
    value = _attr(element, "val")
    return element is not None and value not in {"0", "false", "off"}


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


def _style_snapshot(
    context: AuditContext, role: str, style_id: str
) -> dict[str, object]:
    chain = _effective_style(_style_elements(context), style_id)
    spacing = _latest(chain, "w:pPr/w:spacing")
    ind = _latest(chain, "w:pPr/w:ind")
    fonts = _latest(chain, "w:rPr/w:rFonts")
    size = _latest(chain, "w:rPr/w:sz")
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
        "role": role,
        "paragraph": {
            "alignment": _attr(_latest(chain, "w:pPr/w:jc"), "val"),
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
            "keep_with_next": _on(_latest(chain, "w:pPr/w:keepNext")),
            "page_break_before": _on(
                _latest(chain, "w:pPr/w:pageBreakBefore")
            ),
        },
        "run": {
            "font_zh": _attr(fonts, "eastAsia"),
            "font_latin": _attr(fonts, "ascii") or _attr(fonts, "hAnsi"),
            "size_pt": (
                None
                if _attr(size, "val") is None
                else float(_attr(size, "val")) / 2
            ),
            "bold": _on(_latest(chain, "w:rPr/w:b")),
            "italic": _on(_latest(chain, "w:rPr/w:i")),
        },
    }


def _float_attr_value(
    element: etree._Element | None, name: str
) -> float | None:
    value = _attr(element, name)
    return None if value is None else float(value)


def _expected_style_snapshot(context: AuditContext, role: str) -> dict[str, object]:
    style = context.profile.styles[role]
    spacing = style.paragraph.line_spacing
    line_spacing: dict[str, object] = {"type": spacing.type}
    if spacing.type == "exact":
        line_spacing["value_pt"] = spacing.value_pt
    else:
        line_spacing["value"] = spacing.value
    return {
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
            if index > 1 and actual_start != "nextPage":
                yield AuditFinding(
                    "PAGE.SECTION.START",
                    "violation",
                    location,
                    "Major sections must start on a new page.",
                    True,
                    actual_start,
                    "nextPage",
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
            if (
                node.role is None
                or node.role in checked
                or not _style_role_matches(context, node.role, node.style_id)
                or node.style_id not in available_styles
            ):
                continue
            checked.add(node.role)
            actual = _style_snapshot(context, node.role, node.style_id)
            expected = _expected_style_snapshot(context, node.role)
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
            if not node.manual_number_token:
                continue
            has_numbering = bool(
                paragraph.xpath("./w:pPr/w:numPr", namespaces=NS)
            )
            has_sequence = any(
                field.upper().startswith(("SEQ ", "STYLEREF "))
                for field in node.fields
            )
            if node.role in {"heading_1", "heading_2", "heading_3"} and not (
                has_numbering or has_sequence
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
                has_numbering or has_sequence
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
            elif node.role in {"figure_caption", "table_caption"} and not has_sequence:
                yield AuditFinding(
                    "NUMBERING.MANUAL_CAPTION",
                    "violation",
                    node.location,
                    "Caption number is typed manually instead of generated.",
                    True,
                    node.manual_number_token,
                    "SEQ field",
                )


class FieldRule:
    rule_id = "FIELD"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        fields = _all_fields(context)
        normalized = tuple(re.sub(r"\s+", " ", code).strip() for _, code in fields)
        required = (
            ("FIELD.TOC.REQUIRED", context.profile.fields.toc.field_code),
            (
                "FIELD.LIST_OF_FIGURES.REQUIRED",
                context.profile.fields.list_of_figures.field_code,
            ),
            (
                "FIELD.LIST_OF_TABLES.REQUIRED",
                context.profile.fields.list_of_tables.field_code,
            ),
        )
        for rule_id, field_code in required:
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
        for location, field in fields:
            match = re.match(r"^(?:REF|PAGEREF)\s+(\S+)", field, re.IGNORECASE)
            if match and match.group(1) not in bookmarks:
                target_digest = hashlib.sha256(
                    match.group(1).encode("utf-8")
                ).hexdigest()
                yield AuditFinding(
                    "FIELD.CROSS_REFERENCE.TARGET",
                    "error",
                    location,
                    "Cross-reference target does not exist.",
                    True,
                    {"missing_target_sha256": target_digest},
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
            justification = _attr(
                paragraph.find("w:pPr/w:jc", namespaces=NS), "val"
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
            caption_index = index + 1
            caption = (
                context.semantic.paragraphs[caption_index - 1]
                if caption_index <= len(context.semantic.paragraphs)
                else None
            )
            if caption is None or caption.role != "figure_caption":
                yield AuditFinding(
                    "FIGURE.CAPTION.POSITION",
                    "violation",
                    location,
                    "Figure must have a caption immediately below it.",
                    True,
                    False,
                    "caption below",
                )


class TableRule:
    rule_id = "TABLE"

    def audit(self, context: AuditContext) -> Iterable[AuditFinding]:
        body_children = [
            child
            for child in context.document_root.find("w:body", namespaces=NS)
            if isinstance(child.tag, str)
        ]
        table_number = 0
        for child_index, table in enumerate(body_children):
            if etree.QName(table).localname != "tbl":
                continue
            table_number += 1
            location = f"table:{table_number}"
            previous = body_children[child_index - 1] if child_index else None
            previous_is_caption = False
            if previous is not None and etree.QName(previous).localname == "p":
                paragraph_position = sum(
                    1
                    for item in body_children[:child_index]
                    if etree.QName(item).localname == "p"
                )
                if paragraph_position:
                    previous_is_caption = (
                        context.semantic.paragraphs[paragraph_position - 1].role
                        == "table_caption"
                    )
            if not previous_is_caption:
                yield AuditFinding(
                    "TABLE.CAPTION.POSITION",
                    "violation",
                    location,
                    "Table must have a caption immediately above it.",
                    True,
                    False,
                    "caption above",
                )

            first_row = table.find("w:tr", namespaces=NS)
            repeat_header = (
                first_row is not None
                and first_row.find("w:trPr/w:tblHeader", namespaces=NS) is not None
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
                row.find("w:trPr/w:cantSplit", namespaces=NS) is None
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
            has_three_line = (
                borders is not None
                and borders.find("w:top", namespaces=NS) is not None
                and borders.find("w:bottom", namespaces=NS) is not None
                and borders.find("w:insideH", namespaces=NS) is not None
                and borders.find("w:insideV", namespaces=NS) is None
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
            spacing = paragraph.find("w:pPr/w:spacing", namespaces=NS)
            ind = paragraph.find("w:pPr/w:ind", namespaces=NS)
            actual = {
                "line_spacing_pt": _pt_from_twips(_attr(spacing, "line")),
                "space_before_pt": _pt_from_twips(_attr(spacing, "before")) or 0,
                "space_after_pt": _pt_from_twips(_attr(spacing, "after")) or 0,
                "hanging_indent_mm": _mm_from_twips(_attr(ind, "hanging")) or 0,
            }
            wanted = {
                "line_spacing_pt": expected.line_spacing_pt,
                "space_before_pt": expected.space_before_pt,
                "space_after_pt": expected.space_after_pt,
                "hanging_indent_mm": expected.hanging_indent_mm,
            }
            if any(not _close(actual[key], value) for key, value in wanted.items()):
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
        page_fields = [
            (location, field)
            for location, field in _all_fields(context)
            if re.match(r"^PAGE(?:\s|$)", field, re.IGNORECASE)
        ]
        if not page_fields:
            yield AuditFinding(
                "HEADER.FOOTER.PAGE_NUMBER",
                "violation",
                "document",
                "No generated page-number field was found.",
                True,
                False,
                True,
            )
        if not context.semantic.headers:
            yield AuditFinding(
                "HEADER.FOOTER.HEADER_REQUIRED",
                "violation",
                "document",
                "No generated thesis header was found.",
                True,
                False,
                True,
            )
        if not context.semantic.footers:
            yield AuditFinding(
                "HEADER.FOOTER.FOOTER_REQUIRED",
                "violation",
                "document",
                "No thesis footer was found.",
                True,
                False,
                True,
            )

        body_paragraph = next(
            (
                int(node.location.split(":")[1])
                for node in context.semantic.paragraphs
                if node.role == "heading_1"
            ),
            None,
        )
        body_section = (
            _section_for_paragraph(context, body_paragraph)
            if body_paragraph is not None
            else len(context.section_elements) + 1
        )
        for index, section in enumerate(context.section_elements, start=1):
            location = f"section:{index}"
            header_refs = section.findall("w:headerReference", namespaces=NS)
            footer_refs = section.findall("w:footerReference", namespaces=NS)
            if index > 1 and (header_refs or footer_refs):
                yield AuditFinding(
                    "HEADER.FOOTER.LINKING",
                    "warning",
                    location,
                    "Explicit header or footer may break required section linking.",
                    True,
                    "explicit relationship",
                    "linked to previous",
                )

            page_number = section.find("w:pgNumType", namespaces=NS)
            if index == body_section:
                expected_start = context.profile.fields.page_number.body_start
            elif index == 1:
                expected_start = context.profile.fields.page_number.front_start
            else:
                expected_start = None
            if expected_start is not None and _attr(page_number, "start") != str(
                expected_start
            ):
                yield AuditFinding(
                    "HEADER.FOOTER.PAGE_RESET",
                    "violation",
                    location,
                    "Page numbering must reset at the configured region start.",
                    True,
                    _attr(page_number, "start"),
                    expected_start,
                )
            expected_format = "upperRoman" if index < body_section else "decimal"
            actual_format = _attr(page_number, "fmt")
            if actual_format != expected_format:
                yield AuditFinding(
                    "HEADER.FOOTER.PAGE_STYLE",
                    "violation",
                    location,
                    "Page-number style does not match the section region.",
                    True,
                    actual_format,
                    expected_format,
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
                flags = re.IGNORECASE if "i" in pattern.flags else 0
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
    rendered = _redact_text(canonical_json(value).strip())
    return rendered.replace("|", "\\|").replace("\n", " ")


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
                message=_redact_text(str(finding["message"])).replace(
                    "|", "\\|"
                ),
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
