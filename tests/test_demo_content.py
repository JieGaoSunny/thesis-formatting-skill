from __future__ import annotations

import hashlib
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from thesis_format.demo import (
    Appendix,
    Chapter,
    Figure,
    Paragraph,
    Reference,
    Section,
    Table,
    Thesis,
    build_demo_thesis,
    generate_demo_figures,
)


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


def test_figures_have_chinese_labels_and_accessible_alt_text() -> None:
    thesis = build_demo_thesis()

    assert [figure.number for figure in thesis.figures] == ["图 2-1", "图 3-1"]
    assert all(re.search(r"[\u4e00-\u9fff]", figure.alt_text) for figure in thesis.figures)
    assert all(len(figure.alt_text) >= 20 for figure in thesis.figures)


def test_demo_figures_are_deterministic_pngs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_paths = generate_demo_figures(first)
    second_paths = generate_demo_figures(second)

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

    paths = generate_demo_figures()

    assert all(path.parent == tmp_path / "build" / "demo-assets" for path in paths)
