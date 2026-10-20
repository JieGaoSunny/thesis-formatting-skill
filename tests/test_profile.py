from __future__ import annotations

import re
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest
import yaml

from thesis_format.contracts import ContractError
from thesis_format.profile import FormatProfile, load_profile


ROOT = Path(__file__).parents[1]
PROFILE_PATH = ROOT / "rules" / "apple-university.yaml"


def profile_data() -> dict:
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


def write_profile(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def set_path(data: dict, path: tuple[str | int, ...], value: object) -> None:
    target = data
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value


def test_loads_complete_immutable_apple_university_profile() -> None:
    profile = load_profile(PROFILE_PATH)

    assert isinstance(profile, FormatProfile)
    assert profile.profile.id == "apple-university-thesis"
    assert profile.profile.display_name == "Apple University Thesis"
    assert profile.profile.schema_version == "1.0"
    assert profile.privacy.fictional_values.institution_zh == "苹果大学"
    assert profile.privacy.fictional_values.institution_en == "Apple University"
    assert profile.privacy.fictional_values.author == "艾苹"
    assert profile.privacy.fictional_values.student_id == "APPLE-0001"
    assert profile.privacy.fictional_values.adviser == "林果教授"

    assert all(is_dataclass(getattr(profile, field)) for field in (
        "profile",
        "metadata",
        "page",
        "styles",
        "role_detection",
        "numbering",
        "front_matter",
        "fields",
        "headers_footers",
        "figures",
        "tables",
        "references",
        "privacy",
    ))
    with pytest.raises(FrozenInstanceError):
        profile.page.header_distance_mm = 20
    with pytest.raises(TypeError):
        profile.styles["body"] = profile.styles["heading_1"]
    with pytest.raises(TypeError):
        profile.role_detection.text_patterns["body"] = ()


def test_page_fonts_and_normative_style_values_are_exact() -> None:
    profile = load_profile(PROFILE_PATH)

    assert (profile.page.paper.width_mm, profile.page.paper.height_mm) == (210, 297)
    assert (
        profile.page.body.top_mm,
        profile.page.body.bottom_mm,
        profile.page.body.left_mm,
        profile.page.body.right_mm,
    ) == (30, 30, 30, 30)
    assert (profile.page.header_distance_mm, profile.page.footer_distance_mm) == (
        22,
        22,
    )

    expected = {
        "title_zh": ("center", "multiple", 1.25, 0, 0, 0, 26, True),
        "title_en": ("center", "multiple", 1.25, 0, 0, 0, 22, True),
        "front_heading": ("center", "multiple", 1, 24, 18, 0, 16, True),
        "heading_1": ("center", "multiple", 1, 24, 18, 0, 16, True),
        "appendix_heading": ("center", "multiple", 1, 24, 18, 0, 16, True),
        "heading_2": ("left", "exact", 20, 24, 6, 0, 14, True),
        "heading_3": ("left", "exact", 20, 12, 6, 0, 13, True),
        "body": ("justify", "exact", 20, 0, 0, 2, 12, False),
        "abstract_zh": ("justify", "exact", 20, 0, 0, 2, 12, False),
        "abstract_en": ("justify", "exact", 20, 0, 0, 0, 12, False),
        "keywords": ("left", "exact", 20, 0, 0, 0, 12, False),
        "figure_caption": ("center", "multiple", 1, 6, 12, 0, 11, False),
        "table_caption": ("center", "multiple", 1, 12, 6, 0, 11, False),
        "source_note": ("left", "multiple", 1, 6, 12, 0, 10.5, False),
        "table_body": ("left", "multiple", 1, 0, 0, 0, 11, False),
        "reference": ("left", "exact", 16, 0, 0, 0, 10.5, False),
    }
    for role, values in expected.items():
        style = profile.styles[role]
        spacing = style.paragraph.line_spacing
        spacing_value = (
            spacing.value_pt if spacing.type == "exact" else spacing.value
        )
        assert (
            style.paragraph.alignment,
            spacing.type,
            spacing_value,
            style.paragraph.space_before_pt,
            style.paragraph.space_after_pt,
            style.paragraph.first_line_chars,
            style.run.size_pt,
            style.run.bold,
        ) == values

    heading_roles = {
        "title_zh",
        "title_en",
        "front_heading",
        "heading_1",
        "heading_2",
        "heading_3",
        "appendix_heading",
    }
    for role, style in profile.styles.items():
        assert style.run.font_zh == (
            "Noto Sans CJK SC" if role in heading_roles else "Noto Serif CJK SC"
        )
        assert style.run.font_latin == (
            "Liberation Sans" if role in heading_roles else "Liberation Serif"
        )
    assert profile.styles["reference"].paragraph.hanging_indent_mm == 10


def test_numbering_front_matter_fields_headers_and_objects_are_exact() -> None:
    profile = load_profile(PROFILE_PATH)

    assert (
        profile.numbering.chapters.format,
        profile.numbering.sections.format,
        profile.numbering.sections.restart_scope,
        profile.numbering.appendices.format,
        profile.numbering.figures.restart_scope,
        profile.numbering.tables.restart_scope,
    ) == (
        "chinese_chapter",
        "decimal",
        "chapter",
        "upper_alpha",
        "chapter",
        "chapter",
    )
    assert tuple(part.id for part in profile.front_matter.parts) == (
        "title_zh",
        "title_en",
        "abstract_zh",
        "abstract_en",
        "toc",
        "list_of_figures",
        "list_of_tables",
        "abbreviations",
    )
    numbered = profile.front_matter.parts[2:]
    assert all(part.page_number_style == "upper_roman" for part in numbered)
    assert profile.fields.page_number.front_start == 1
    assert profile.fields.page_number.body_start == 1
    assert profile.headers_footers.body.header_source == "current_heading_1"
    assert (
        profile.headers_footers.appendix.header_source
        == "current_appendix_heading"
    )
    assert profile.figures.caption_position == "below"
    assert profile.tables.caption_position == "above"
    assert profile.figures.alignment == "center"


def test_aliases_are_unique_and_role_detection_is_anchored_and_positioned() -> None:
    profile = load_profile(PROFILE_PATH)

    aliases = [
        alias for style in profile.styles.values() for alias in style.word_styles
    ]
    assert len(aliases) == len(set(aliases))
    for role, patterns in profile.role_detection.text_patterns.items():
        for pattern in patterns:
            assert pattern.pattern.startswith("^"), role
            assert pattern.pattern.endswith("$"), role
    assert profile.role_detection.position_constraints["title_zh"][0].section == (
        "title_page"
    )
    assert profile.role_detection.position_constraints["reference"][0].section == (
        "references"
    )
    assert (
        profile.role_detection.position_constraints["appendix_heading"][0].section
        == "appendix"
    )


def test_reference_heading_has_reference_position_constraint() -> None:
    profile = load_profile(PROFILE_PATH)
    patterns = profile.role_detection.text_patterns["front_heading"]
    constraints = profile.role_detection.position_constraints["front_heading"]

    assert any(re.fullmatch(pattern.pattern, "参考文献") for pattern in patterns)
    assert any(constraint.section == "references" for constraint in constraints)
    assert all(constraint.section != "body" for constraint in constraints)


def test_acknowledgements_is_not_a_front_heading_text_alias() -> None:
    profile = load_profile(PROFILE_PATH)
    patterns = profile.role_detection.text_patterns["front_heading"]

    assert not any(re.fullmatch(pattern.pattern, "致谢") for pattern in patterns)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("page", "body", "left_mm"), 180),
        (("page", "body", "top_mm"), 267),
        (("page", "body", "bottom_mm"), 0),
        (("styles", "front_heading", "paragraph", "first_line_chars"), 1),
        (("styles", "heading_2", "paragraph", "left_indent_mm"), 1),
        (("styles", "appendix_heading", "paragraph", "hanging_indent_mm"), 1),
        (("figures", "max_width_mm"), 151),
        (("figures", "caption_position"), "above"),
        (("tables", "caption_position"), "below"),
        (("styles", "reference", "paragraph", "space_before_pt"), 1),
        (("styles", "reference", "paragraph", "space_after_pt"), 1),
        (("styles", "reference", "paragraph", "hanging_indent_mm"), 9),
        (
            ("styles", "reference", "paragraph", "line_spacing"),
            {"type": "exact", "value_pt": 15},
        ),
        (
            ("styles", "heading_2", "word_styles", 0),
            "AppleHeading1",
        ),
        (("fields", "toc", "levels"), {"min": 3, "max": 1}),
        (("headers_footers", "body", "page_number_alignment"), "right"),
        (("headers_footers", "body", "page_number_style"), "upper_roman"),
        (("fields", "page_number", "body_start"), 0),
        (("front_matter", "parts", 2, "starts_section"), False),
        (("front_matter", "parts", 2, "page_number_style"), "decimal"),
        (("front_matter", "parts", 0, "show_header"), True),
        (("headers_footers", "body", "header_style_role"), "missing"),
    ],
)
def test_loader_rejects_cross_field_failures(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    data = profile_data()
    set_path(data, path, value)

    with pytest.raises(ContractError):
        load_profile(write_profile(tmp_path, data))


def test_loader_rejects_figure_wider_than_changed_content_width(
    tmp_path: Path,
) -> None:
    data = profile_data()
    data["page"]["body"]["left_mm"] = 40

    with pytest.raises(ContractError, match="figure maximum width"):
        load_profile(write_profile(tmp_path, data))


@pytest.mark.parametrize("field_name", ["toc", "list_of_figures", "list_of_tables"])
def test_loader_rejects_required_field_without_matching_front_part(
    tmp_path: Path, field_name: str
) -> None:
    data = profile_data()
    data["front_matter"]["parts"] = [
        part for part in data["front_matter"]["parts"] if part["id"] != field_name
    ]

    with pytest.raises(ContractError, match="required field"):
        load_profile(write_profile(tmp_path, data))


def test_loader_rejects_disabled_header_with_active_source(tmp_path: Path) -> None:
    data = profile_data()
    data["headers_footers"]["appendix"]["header_enabled"] = False

    with pytest.raises(ContractError, match="header_source"):
        load_profile(write_profile(tmp_path, data))


def test_loader_rejects_front_show_header_mismatch(tmp_path: Path) -> None:
    data = profile_data()
    data["front_matter"]["parts"][3]["show_header"] = False

    with pytest.raises(ContractError, match="show_header"):
        load_profile(write_profile(tmp_path, data))
