"""Validated, immutable thesis format profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from thesis_format.contracts import ContractError, validate_format_profile


@dataclass(frozen=True, slots=True)
class ProfileIdentity:
    id: str
    display_name: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class Metadata:
    description: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Paper:
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class Margins:
    top_mm: float
    bottom_mm: float
    left_mm: float
    right_mm: float


@dataclass(frozen=True, slots=True)
class SectionStart:
    body: str
    major_back_matter: str


@dataclass(frozen=True, slots=True)
class Page:
    paper: Paper
    body: Margins
    header_distance_mm: float
    footer_distance_mm: float
    section_start: SectionStart


@dataclass(frozen=True, slots=True)
class LineSpacing:
    type: str
    value: float | None = None
    value_pt: float | None = None


@dataclass(frozen=True, slots=True)
class ParagraphStyle:
    alignment: str
    line_spacing: LineSpacing
    space_before_pt: float
    space_after_pt: float
    first_line_chars: float
    left_indent_mm: float
    hanging_indent_mm: float
    keep_with_next: bool
    page_break_before: bool


@dataclass(frozen=True, slots=True)
class RunStyle:
    font_zh: str
    font_latin: str
    size_pt: float
    bold: bool
    italic: bool


@dataclass(frozen=True, slots=True)
class Style:
    paragraph: ParagraphStyle
    run: RunStyle
    word_styles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Styles(Mapping[str, Style]):
    title_zh: Style
    title_en: Style
    front_heading: Style
    heading_1: Style
    heading_2: Style
    heading_3: Style
    body: Style
    abstract_zh: Style
    abstract_en: Style
    keywords: Style
    figure_caption: Style
    table_caption: Style
    source_note: Style
    table_body: Style
    reference: Style
    appendix_heading: Style

    def __getitem__(self, key: str) -> Style:
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self):
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class TextPattern:
    pattern: str
    flags: tuple[str, ...]
    priority: int


@dataclass(frozen=True, slots=True)
class PositionConstraint:
    section: str
    min_index: int
    max_index: int | None
    first_page_only: bool


@dataclass(frozen=True, slots=True)
class RoleDetection:
    text_patterns: Mapping[str, tuple[TextPattern, ...]]
    position_constraints: Mapping[str, tuple[PositionConstraint, ...]]


@dataclass(frozen=True, slots=True)
class NumberingRule:
    format: str
    separator: str
    restart_scope: str


@dataclass(frozen=True, slots=True)
class Numbering:
    chapters: NumberingRule
    sections: NumberingRule
    appendices: NumberingRule
    figures: NumberingRule
    tables: NumberingRule


@dataclass(frozen=True, slots=True)
class FrontMatterPart:
    id: str
    heading_role: str
    required: bool
    starts_section: bool
    page_number_style: str
    show_header: bool


@dataclass(frozen=True, slots=True)
class FrontMatter:
    parts: tuple[FrontMatterPart, ...]


@dataclass(frozen=True, slots=True)
class TocLevels:
    min: int
    max: int


@dataclass(frozen=True, slots=True)
class TocField:
    required: bool
    field_code: str
    levels: TocLevels


@dataclass(frozen=True, slots=True)
class CaptionListField:
    required: bool
    field_code: str
    levels: None


@dataclass(frozen=True, slots=True)
class PageNumberField:
    front_start: int
    body_start: int
    alignment: str


@dataclass(frozen=True, slots=True)
class CrossReferencesField:
    require_existing_target: bool
    mark_dirty_on_write: bool


@dataclass(frozen=True, slots=True)
class Fields:
    toc: TocField
    list_of_figures: CaptionListField
    list_of_tables: CaptionListField
    page_number: PageNumberField
    cross_references: CrossReferencesField


@dataclass(frozen=True, slots=True)
class HeaderFooterRegion:
    header_enabled: bool
    header_source: str
    header_style_role: str
    page_number_enabled: bool
    page_number_style: str
    page_number_alignment: str
    header_text: str | None = None


@dataclass(frozen=True, slots=True)
class SectionLinking:
    link_body_headers: bool
    link_body_footers: bool
    link_appendix_headers: bool
    link_appendix_footers: bool


@dataclass(frozen=True, slots=True)
class HeadersFooters:
    front_matter: HeaderFooterRegion
    body: HeaderFooterRegion
    appendix: HeaderFooterRegion
    section_linking: SectionLinking


@dataclass(frozen=True, slots=True)
class Figures:
    max_width_mm: float
    alignment: str
    caption_position: str
    caption_keep_with_object: bool
    source_note_required_for_non_original: bool


@dataclass(frozen=True, slots=True)
class Tables:
    caption_position: str
    repeat_header: bool
    allow_row_split: bool
    border_model: str
    continued_table_policy: str


@dataclass(frozen=True, slots=True)
class References:
    citation_system: str
    line_spacing_pt: float
    space_before_pt: float
    space_after_pt: float
    hanging_indent_mm: float


@dataclass(frozen=True, slots=True)
class FictionalValues:
    institution_zh: str
    institution_en: str
    author: str
    student_id: str
    adviser: str


@dataclass(frozen=True, slots=True)
class PrivacyPattern:
    id: str
    regex: str
    flags: str


@dataclass(frozen=True, slots=True)
class Privacy:
    fictional_values: FictionalValues
    forbidden_metadata_keys: tuple[str, ...]
    generic_patterns: tuple[PrivacyPattern, ...]
    unresolved_placeholder_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormatProfile:
    profile: ProfileIdentity
    metadata: Metadata
    page: Page
    styles: Styles
    role_detection: RoleDetection
    numbering: Numbering
    front_matter: FrontMatter
    fields: Fields
    headers_footers: HeadersFooters
    figures: Figures
    tables: Tables
    references: References
    privacy: Privacy


def _line_spacing(data: Mapping[str, Any]) -> LineSpacing:
    return LineSpacing(
        type=data["type"],
        value=data.get("value"),
        value_pt=data.get("value_pt"),
    )


def _style(data: Mapping[str, Any]) -> Style:
    paragraph = data["paragraph"]
    run = data["run"]
    return Style(
        paragraph=ParagraphStyle(
            alignment=paragraph["alignment"],
            line_spacing=_line_spacing(paragraph["line_spacing"]),
            space_before_pt=paragraph["space_before_pt"],
            space_after_pt=paragraph["space_after_pt"],
            first_line_chars=paragraph["first_line_chars"],
            left_indent_mm=paragraph["left_indent_mm"],
            hanging_indent_mm=paragraph["hanging_indent_mm"],
            keep_with_next=paragraph["keep_with_next"],
            page_break_before=paragraph["page_break_before"],
        ),
        run=RunStyle(**run),
        word_styles=tuple(data["word_styles"]),
    )


def _region(data: Mapping[str, Any]) -> HeaderFooterRegion:
    return HeaderFooterRegion(
        header_enabled=data["header_enabled"],
        header_source=data["header_source"],
        header_style_role=data["header_style_role"],
        header_text=data.get("header_text"),
        page_number_enabled=data["page_number_enabled"],
        page_number_style=data["page_number_style"],
        page_number_alignment=data["page_number_alignment"],
    )


def _numbering_rule(data: Mapping[str, Any]) -> NumberingRule:
    return NumberingRule(**data)


def _build_profile(data: Mapping[str, Any]) -> FormatProfile:
    page = data["page"]
    role_detection = data["role_detection"]
    numbering = data["numbering"]
    fields = data["fields"]
    headers_footers = data["headers_footers"]
    privacy = data["privacy"]
    return FormatProfile(
        profile=ProfileIdentity(**data["profile"]),
        metadata=Metadata(
            description=data["metadata"]["description"],
            notes=tuple(data["metadata"].get("notes", ())),
        ),
        page=Page(
            paper=Paper(**page["paper"]),
            body=Margins(**page["body"]),
            header_distance_mm=page["header_distance_mm"],
            footer_distance_mm=page["footer_distance_mm"],
            section_start=SectionStart(**page["section_start"]),
        ),
        styles=Styles(
            **{role: _style(style) for role, style in data["styles"].items()}
        ),
        role_detection=RoleDetection(
            text_patterns=MappingProxyType(
                {
                    role: tuple(TextPattern(**pattern) for pattern in patterns)
                    for role, patterns in role_detection["text_patterns"].items()
                }
            ),
            position_constraints=MappingProxyType(
                {
                    role: tuple(
                        PositionConstraint(**constraint) for constraint in constraints
                    )
                    for role, constraints in role_detection[
                        "position_constraints"
                    ].items()
                }
            ),
        ),
        numbering=Numbering(
            chapters=_numbering_rule(numbering["chapters"]),
            sections=_numbering_rule(numbering["sections"]),
            appendices=_numbering_rule(numbering["appendices"]),
            figures=_numbering_rule(numbering["figures"]),
            tables=_numbering_rule(numbering["tables"]),
        ),
        front_matter=FrontMatter(
            parts=tuple(FrontMatterPart(**part) for part in data["front_matter"]["parts"])
        ),
        fields=Fields(
            toc=TocField(
                required=fields["toc"]["required"],
                field_code=fields["toc"]["field_code"],
                levels=TocLevels(**fields["toc"]["levels"]),
            ),
            list_of_figures=CaptionListField(**fields["list_of_figures"]),
            list_of_tables=CaptionListField(**fields["list_of_tables"]),
            page_number=PageNumberField(**fields["page_number"]),
            cross_references=CrossReferencesField(**fields["cross_references"]),
        ),
        headers_footers=HeadersFooters(
            front_matter=_region(headers_footers["front_matter"]),
            body=_region(headers_footers["body"]),
            appendix=_region(headers_footers["appendix"]),
            section_linking=SectionLinking(**headers_footers["section_linking"]),
        ),
        figures=Figures(**data["figures"]),
        tables=Tables(**data["tables"]),
        references=References(**data["references"]),
        privacy=Privacy(
            fictional_values=FictionalValues(**privacy["fictional_values"]),
            forbidden_metadata_keys=tuple(privacy["forbidden_metadata_keys"]),
            generic_patterns=tuple(
                PrivacyPattern(**pattern) for pattern in privacy["generic_patterns"]
            ),
            unresolved_placeholder_patterns=tuple(
                privacy["unresolved_placeholder_patterns"]
            ),
        ),
    )


def load_profile(path: str | Path) -> FormatProfile:
    """Load a YAML profile, validate the Task 2 contract, and freeze its values."""

    profile_path = Path(path)
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ContractError(f"invalid YAML: {error}", cause=error) from error
    if not isinstance(data, dict):
        raise ContractError("format profile YAML must contain an object")
    validate_format_profile(data)
    if data["page"]["section_start"]["body"] == "continuous":
        raise ContractError(
            "body section start for decimal page-number restart may not be continuous",
            ("page", "section_start", "body"),
        )
    return _build_profile(data)
