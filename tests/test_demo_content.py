from __future__ import annotations

import hashlib
import inspect
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from thesis_format.demo import (
    Appendix,
    Chapter,
    DEFAULT_SCALE_INPUTS,
    Figure,
    FigureFontError,
    Paragraph,
    Reference,
    SIMULATED_OBSERVATIONS,
    Section,
    Table,
    Thesis,
    build_demo_thesis,
    calculate_reported_statistics,
    generate_demo_figures,
    resolve_cjk_font,
    sensitivity_envelope,
)
from thesis_format.demo import figures as demo_figures
from thesis_format.demo import study as demo_study


def _all_paragraph_text(thesis: Thesis) -> str:
    texts = [thesis.abstract_zh, thesis.abstract_en, thesis.acknowledgements]
    for chapter in thesis.chapters:
        texts.extend(paragraph.text for paragraph in chapter.paragraphs)
        for section in chapter.sections:
            texts.extend(paragraph.text for paragraph in section.paragraphs)
    texts.extend(paragraph.text for paragraph in thesis.appendix.paragraphs)
    return "\n".join(texts)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_demo_models_are_frozen_dataclasses() -> None:
    thesis = build_demo_thesis()
    instances = (
        Paragraph("正文"),
        Section("小节"),
        Chapter("章节"),
        Figure("图 1-1", "x.png", "替代文本"),
        Table("表 1-1", ("列",), (("值",),)),
        Reference(1, "虚构作者", "虚构题名", 2024, "虚构出版物"),
        Appendix("附录"),
        thesis,
    )

    for instance in instances:
        with pytest.raises(FrozenInstanceError):
            setattr(instance, next(iter(instance.__dataclass_fields__)), "changed")


def test_demo_thesis_has_complete_bilingual_front_matter() -> None:
    thesis = build_demo_thesis()

    assert thesis.title_zh == "单株苹果树叶片数量的估算方法研究"
    assert (
        thesis.title_en
        == "Estimating the Number of Leaves on an Individual Apple Tree"
    )
    assert len(thesis.abstract_zh) >= 400
    assert len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", thesis.abstract_en)) >= 150
    assert 3 <= len(thesis.keywords_zh) <= 5
    assert len(thesis.keywords_zh) == len(thesis.keywords_en)
    assert all(zh.strip() and en.strip() for zh, en in thesis.paired_keywords)


def test_demo_thesis_has_renderable_structure_and_volume() -> None:
    thesis = build_demo_thesis()
    all_text = _all_paragraph_text(thesis)

    assert 3 <= len(thesis.chapters) <= 4
    assert [chapter.number for chapter in thesis.chapters] == list(
        range(1, len(thesis.chapters) + 1)
    )
    assert all(chapter.sections for chapter in thesis.chapters)
    assert len(thesis.figures) >= 2
    assert len(thesis.tables) >= 2
    assert thesis.appendix.paragraphs
    assert len(thesis.acknowledgements) >= 120
    assert len(all_text) >= 10_000


def test_simulated_data_disclosure_is_explicit_and_repeated() -> None:
    thesis = build_demo_thesis()
    all_text = _all_paragraph_text(thesis)

    assert "模拟数据" in thesis.data_disclosure
    assert "不代表任何真实" in thesis.data_disclosure
    assert thesis.data_disclosure in all_text
    assert "simulated data" in thesis.abstract_en.lower()
    assert "模拟数据" in thesis.abstract_zh


def test_citations_are_sequential_and_exactly_cover_references() -> None:
    thesis = build_demo_thesis()
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", _all_paragraph_text(thesis))]
    reference_numbers = [reference.number for reference in thesis.references]

    assert reference_numbers == list(range(1, len(thesis.references) + 1))
    assert citations == reference_numbers
    assert all(
        reference.author
        and reference.title
        and reference.year
        and reference.publication
        for reference in thesis.references
    )


def test_tables_are_rectangular_and_marked_as_simulated() -> None:
    thesis = build_demo_thesis()

    assert [table.number for table in thesis.tables] == ["表 2-1", "表 3-1"]
    for table in thesis.tables:
        assert table.headers
        assert table.rows
        assert all(len(row) == len(table.headers) for row in table.rows)
        assert "模拟" in table.note


def test_appendix_contains_complete_observations_and_scale_inputs() -> None:
    thesis = build_demo_thesis()
    tables = {table.number: table for table in thesis.appendix.tables}

    assert len(SIMULATED_OBSERVATIONS) == 18
    assert len(
        {(row.round_id, row.quadrat_id) for row in SIMULATED_OBSERVATIONS}
    ) == 18
    assert len(tables["表 A-2"].rows) == 18
    assert tables["表 A-3"].rows == (
        ("单样方面积/m²", "0.25"),
        ("整株等效尺度/m²", "11.0048691418"),
        ("模拟真值/片", "4320"),
        ("上层权重/可见比例", "0.24 / 0.91"),
        ("中层权重/可见比例", "0.46 / 0.82"),
        ("下层权重/可见比例", "0.30 / 0.88"),
        ("变异系数标准差", "样本标准差（n-1）"),
    )


def test_reported_estimates_biases_cvs_and_sensitivity_are_recomputed() -> None:
    statistics = calculate_reported_statistics(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    )

    assert statistics["simple"].rounded_estimate == 4018
    assert statistics["simple"].bias_percent == pytest.approx(-6.99, abs=0.01)
    assert statistics["simple"].cv_percent == pytest.approx(5.8, abs=0.05)
    assert statistics["stratified"].rounded_estimate == 4172
    assert statistics["stratified"].bias_percent == pytest.approx(-3.42, abs=0.01)
    assert statistics["stratified"].cv_percent == pytest.approx(4.2, abs=0.05)
    assert statistics["corrected"].rounded_estimate == 4286
    assert statistics["corrected"].bias_percent == pytest.approx(-0.79, abs=0.01)
    assert statistics["corrected"].cv_percent == pytest.approx(3.1, abs=0.05)
    assert sensitivity_envelope(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    ).rounded_bounds == (4242, 4330)

    thesis = build_demo_thesis()
    thesis_text = "\n".join(
        (
            _all_paragraph_text(thesis),
            *(cell for table in thesis.tables for row in table.rows for cell in row),
        )
    )
    for reported in ("4018", "4172", "4286", "5.8%", "4.2%", "3.1%", "4242", "4330"):
        assert reported in thesis_text
    assert "敏感性区间" in thesis_text
    assert "置信区间" not in thesis_text


def test_leave_one_layer_out_is_recomputed_from_full_dataset_and_exposed() -> None:
    results = demo_study.leave_one_layer_out(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    )

    assert tuple(results) == ("上层", "中层", "下层")
    assert results["上层"].rounded_estimate == 4737
    assert results["上层"].rounded_change == 451
    assert results["中层"].rounded_estimate == 3989
    assert results["中层"].rounded_change == -297
    assert results["下层"].rounded_estimate == 4025
    assert results["下层"].rounded_change == -261

    thesis_text = _all_paragraph_text(build_demo_thesis())
    for reported in ("+451", "-297", "-261"):
        assert reported in thesis_text
    assert "下层后变化较小" not in thesis_text
    assert "中层承担了主要信息量" not in thesis_text


def test_sensitivity_is_named_multi_factor_scenario_envelope_everywhere() -> None:
    thesis_text = _all_paragraph_text(build_demo_thesis())

    assert "多因素情景敏感性包络" in thesis_text
    assert "单因素" not in thesis_text
    assert "one-factor-at-a-time" not in inspect.getdoc(sensitivity_envelope)


def test_figures_have_chinese_labels_and_accessible_alt_text() -> None:
    thesis = build_demo_thesis()

    assert [figure.number for figure in thesis.figures] == ["图 2-1", "图 3-1"]
    assert all(re.search(r"[\u4e00-\u9fff]", figure.alt_text) for figure in thesis.figures)
    assert all(len(figure.alt_text) >= 20 for figure in thesis.figures)


def _available_cjk_font() -> Path:
    candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/opt/homebrew/share/fonts/NotoSansCJK-Regular.ttc"),
        Path("/Library/Fonts/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    )
    return next(path for path in candidates if path.is_file())


def test_resolved_font_renders_chinese_differently_from_missing_glyph() -> None:
    font = resolve_cjk_font(_available_cjk_font(), size=48)
    chinese = Image.new("L", (200, 80))
    missing = Image.new("L", (200, 80))
    ImageDraw.Draw(chinese).text((0, 0), "树冠", font=font, fill=255)
    ImageDraw.Draw(missing).text((0, 0), "\u0378\u0378", font=font, fill=255)

    assert chinese.getbbox() is not None
    assert ImageChops.difference(chinese, missing).getbbox() is not None


def test_missing_cjk_font_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("THESIS_FIGURE_FONT", raising=False)
    monkeypatch.setattr(demo_figures, "_KNOWN_CJK_FONT_PATHS", ())

    with pytest.raises(FigureFontError, match="THESIS_FIGURE_FONT"):
        resolve_cjk_font()


def test_partial_font_missing_any_diagram_label_glyph_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    required = {
        character
        for labels in demo_figures.DIAGRAM_LABEL_SETS
        for label in labels
        for character in label
        if not character.isascii()
    }
    omitted = "围"
    assert omitted in required

    class Mask(bytes):
        def getbbox(self) -> tuple[int, int, int, int] | None:
            return (0, 0, 1, 1) if self else None

    class PartialFont:
        path = "partial-font.ttf"

        def getmask(self, character: str) -> Mask:
            if character in {"\u0378", omitted}:
                return Mask(b"missing")
            return Mask(character.encode("utf-8"))

    font_path = tmp_path / "partial-font.ttf"
    font_path.write_bytes(b"mock")
    monkeypatch.setattr(
        demo_figures.ImageFont,
        "truetype",
        lambda *_args, **_kwargs: PartialFont(),
    )

    with pytest.raises(FigureFontError, match="required Chinese glyphs"):
        resolve_cjk_font(font_path)


def test_demo_figures_are_deterministic_pngs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    font_path = _available_cjk_font()

    first_paths = generate_demo_figures(first, font_path=font_path)
    second_paths = generate_demo_figures(second, font_path=font_path)

    assert [path.name for path in first_paths] == [
        "crown-layer-sampling.png",
        "leaf-count-estimation-workflow.png",
    ]
    assert [_sha256(path) for path in first_paths] == [
        _sha256(path) for path in second_paths
    ]
    for path in first_paths:
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (1800, 1200)
            assert image.mode == "RGB"
            background = Image.new("RGB", image.size, "white")
            assert ImageChops.difference(image, background).getbbox() is not None


def test_default_figure_output_is_under_build_demo_assets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    paths = generate_demo_figures(font_path=_available_cjk_font())

    assert all(path.parent == tmp_path / "build" / "demo-assets" for path in paths)
