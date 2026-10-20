from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from zipfile import ZipFile

import pytest

from thesis_format.ooxml import OoxmlError, OoxmlPackage
from thesis_format.profile import load_profile
from thesis_format.semantic import inspect_document

from helpers.docx_factory import build_docx, build_minimal_roles_fixture


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "minimal-roles.docx"
PROFILE = load_profile(ROOT / "rules" / "apple-university.yaml")


@pytest.fixture(scope="module", autouse=True)
def minimal_fixture() -> None:
    build_minimal_roles_fixture(FIXTURE)


def find_text(document, text: str):
    return next(node for node in document.paragraphs if node.raw_text == text)


def test_semantic_document_and_nodes_are_immutable_and_one_based() -> None:
    document = inspect_document(FIXTURE, PROFILE)
    node = document.paragraphs[0]
    assert node.location == "paragraph:1"
    assert node.raw_text == "第一章 绪论"
    assert node.style_id == "AppleHeading1"
    assert node.style_name == "AppleHeading1"
    assert (node.role, node.role_source) == ("heading_1", "word_style")
    with pytest.raises(FrozenInstanceError):
        node.role = "body"


def test_role_resolution_prefers_mapped_word_style(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "style.docx",
        [{"text": "not a heading pattern", "style": "苹果大学标题1"}],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.role == "heading_1"
    assert node.role_source == "word_style"
    assert node.repairable is True


def test_explicit_fields_bookmarks_and_numbering_are_enumerated(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "explicit.docx",
        [
            {
                "text": "A caption",
                "field": " SEQ Figure \\* ARABIC ",
                "bookmark": "demo_figure",
            },
            {"text": "Numbered heading", "numbering_level": 1},
        ],
    )
    document = inspect_document(path, PROFILE)
    caption, heading = document.paragraphs
    assert caption.role == "figure_caption"
    assert caption.role_source == "explicit_structure"
    assert caption.fields == ("SEQ Figure \\* ARABIC",)
    assert caption.bookmarks == ("demo_figure",)
    assert heading.role == "heading_2"
    assert heading.role_source == "explicit_structure"


def test_text_patterns_use_fullmatch(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "patterns.docx",
        [
            {"text": "第二章 方法"},
            {"text": "前言 第二章 方法 后记"},
        ],
    )
    matched, embedded = inspect_document(path, PROFILE).paragraphs
    assert (matched.role, matched.role_source) == ("heading_1", "text_pattern")
    assert embedded.role is None
    assert embedded.warning == "ROLE.AMBIGUOUS"


def test_document_position_only_recognizes_reference_entries(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "position.docx",
        [
            {"text": "第一章 正文"},
            {"text": "参考文献"},
            {"text": "Apple Research Group. Orchard study."},
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert node.role == "reference"
    assert node.role_source == "document_position"


def test_conflicting_evidence_is_preserved_as_warning(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "conflict.docx",
        [{"text": "1.1 标题", "style": "苹果大学标题1"}],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.role is None
    assert node.repairable is False
    assert node.warning == "ROLE.CONFLICT"


def test_ambiguous_paragraph_is_not_guessed() -> None:
    node = find_text(inspect_document(FIXTURE, PROFILE), "可能是标题也可能是正文")
    assert node.role is None
    assert node.warning == "ROLE.AMBIGUOUS"


def test_skipped_heading_level_is_not_auto_repaired(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "skipped.docx",
        [
            {"text": "第一章 正文"},
            {"text": "1.1.1 跳级标题"},
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert node.role == "heading_3"
    assert node.repairable is False
    assert "ROLE.SKIPPED_HEADING_LEVEL" in node.warnings


def test_enumerates_tables_sections_headers_footers_relationships() -> None:
    document = inspect_document(FIXTURE, PROFILE)
    assert len(document.tables) == 1
    assert document.tables[0].location == "table:1"
    assert document.tables[0].raw_text == "A\tB"
    assert document.sections
    assert document.headers[0].raw_text == "Header text"
    assert "PAGE" in document.footers[0].fields[0]
    assert document.relationships
    assert all(relationship.identity for relationship in document.relationships)


def test_ooxml_roundtrip_preserves_unsupported_parts(tmp_path: Path) -> None:
    output = tmp_path / "roundtrip.docx"
    package = OoxmlPackage.open(FIXTURE)
    package.write(output)
    with ZipFile(output) as archive:
        assert archive.read("customXml/unsupported.bin") == b"\x00opaque\xff"


@pytest.mark.parametrize("kind", ["not_zip", "missing_part", "corrupt_xml"])
def test_invalid_or_corrupt_ooxml_has_explicit_error(
    tmp_path: Path, kind: str
) -> None:
    path = tmp_path / f"{kind}.docx"
    if kind == "not_zip":
        path.write_bytes(b"not a zip")
    elif kind == "missing_part":
        with ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
    else:
        build_docx(path, [{"text": "valid"}])
        replacement = tmp_path / "replacement.docx"
        with ZipFile(path) as source, ZipFile(replacement, "w") as target:
            for info in source.infolist():
                data = (
                    b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><x>&e;</x>"
                    if info.filename == "word/document.xml"
                    else source.read(info.filename)
                )
                target.writestr(info, data)
        replacement.replace(path)

    with pytest.raises(OoxmlError):
        inspect_document(path, PROFILE)
