from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType
from zipfile import ZipFile

import pytest
from lxml import etree

from thesis_format.ooxml import OoxmlError, OoxmlPackage, parse_xml
from thesis_format.profile import RoleDetection, TextPattern, load_profile
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


def replace_zip_part(path: Path, part_name: str, replacement: bytes) -> None:
    rewritten = path.with_suffix(".rewrite.docx")
    with ZipFile(path) as source, ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            target.writestr(
                info,
                replacement
                if info.filename == part_name
                else source.read(info.filename),
            )
    rewritten.replace(path)


def link_numbering_level_to_style(
    path: Path,
    *,
    num_id: str,
    level: int,
    style_id: str,
) -> None:
    with ZipFile(path) as archive:
        numbering = etree.fromstring(archive.read("word/numbering.xml"))
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    word = f"{{{namespaces['w']}}}"
    abstract_ids = numbering.xpath(
        f"./w:num[@w:numId='{num_id}']/w:abstractNumId/@w:val",
        namespaces=namespaces,
    )
    assert abstract_ids
    abstract = numbering.xpath(
        f"./w:abstractNum[@w:abstractNumId='{abstract_ids[0]}']",
        namespaces=namespaces,
    )[0]
    levels = abstract.xpath(
        f"./w:lvl[@w:ilvl='{level}']",
        namespaces=namespaces,
    )
    if levels:
        level_element = levels[0]
    else:
        level_element = etree.SubElement(
            abstract,
            f"{word}lvl",
            {f"{word}ilvl": str(level)},
        )
    for existing in level_element.xpath("./w:pStyle", namespaces=namespaces):
        level_element.remove(existing)
    for existing in level_element.xpath("./w:numFmt", namespaces=namespaces):
        level_element.remove(existing)
    etree.SubElement(
        level_element,
        f"{word}numFmt",
        {f"{word}val": "decimal"},
    )
    etree.SubElement(
        level_element,
        f"{word}pStyle",
        {f"{word}val": style_id},
    )
    replace_zip_part(
        path,
        "word/numbering.xml",
        etree.tostring(
            numbering,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        ),
    )


def set_numbering_level_format(
    path: Path,
    *,
    num_id: str,
    level: int,
    value: str = "decimal",
) -> None:
    with ZipFile(path) as archive:
        numbering = etree.fromstring(archive.read("word/numbering.xml"))
    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    word = f"{{{namespaces['w']}}}"
    abstract_id = numbering.xpath(
        f"./w:num[@w:numId='{num_id}']/w:abstractNumId/@w:val",
        namespaces=namespaces,
    )[0]
    levels = numbering.xpath(
        f"./w:abstractNum[@w:abstractNumId='{abstract_id}']"
        f"/w:lvl[@w:ilvl='{level}']",
        namespaces=namespaces,
    )
    level_element = (
        levels[0]
        if levels
        else etree.SubElement(
            numbering.xpath(
                f"./w:abstractNum[@w:abstractNumId='{abstract_id}']",
                namespaces=namespaces,
            )[0],
            f"{word}lvl",
            {f"{word}ilvl": str(level)},
        )
    )
    for existing in level_element.xpath("./w:numFmt", namespaces=namespaces):
        level_element.remove(existing)
    etree.SubElement(
        level_element,
        f"{word}numFmt",
        {f"{word}val": value},
    )
    replace_zip_part(
        path,
        "word/numbering.xml",
        etree.tostring(
            numbering,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        ),
    )


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
            {
                "text": "Numbered heading",
                "numbering_level": 1,
                "outline_level": 1,
            },
        ],
    )
    set_numbering_level_format(path, num_id="1", level=1)
    document = inspect_document(path, PROFILE)
    caption, heading = document.paragraphs
    assert caption.role == "figure_caption"
    assert caption.role_source == "explicit_structure"
    assert caption.fields == ("SEQ Figure \\* ARABIC",)
    assert caption.bookmarks == ("demo_figure",)
    assert heading.role == "heading_2"
    assert heading.role_source == "explicit_structure"


@pytest.mark.parametrize("numbering_level", [0, 1])
def test_ordinary_numbered_list_is_not_classified_as_heading(
    tmp_path: Path,
    numbering_level: int,
) -> None:
    path = build_docx(
        tmp_path / f"ordinary-list-{numbering_level}.docx",
        [
            {
                "text": "Ordinary numbered list item",
                "numbering_level": numbering_level,
            }
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.role is None
    assert node.repairable is False


def test_numbering_with_matching_anchored_pattern_is_explicit_heading(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "pattern-numbered-heading.docx",
        [
            {"text": "第一章 正文"},
            {"text": "1.1 Genuine heading", "numbering_level": 1},
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert (node.role, node.role_source) == ("heading_2", "text_pattern")
    assert node.repairable is True


def test_numbering_at_wrong_hierarchy_does_not_conflict_with_heading_pattern(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "mismatched-numbered-heading.docx",
        [
            {"text": "第一章 正文"},
            {"text": "1.1 Genuine heading", "numbering_level": 0},
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert (node.role, node.role_source) == ("heading_2", "text_pattern")
    assert node.repairable is True


def test_numbering_with_matching_outline_level_is_explicit_heading(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "outline-numbered-heading.docx",
        [
            {"text": "第一章 正文"},
            {
                "text": "Genuine numbered heading",
                "numbering_level": 1,
                "outline_level": 1,
            },
        ],
    )
    set_numbering_level_format(path, num_id="1", level=1)
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert (node.role, node.role_source) == (
        "heading_2",
        "explicit_structure",
    )
    assert node.repairable is True


def test_numbering_level_style_metadata_can_confirm_heading(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "numbering-style-heading.docx",
        [
            {"text": "第一章 正文"},
            {"text": "Style declaration", "style": "AppleHeading2"},
            {"text": "Metadata-confirmed heading", "numbering_level": 1},
        ],
    )
    link_numbering_level_to_style(
        path,
        num_id="1",
        level=1,
        style_id="AppleHeading2",
    )
    node = inspect_document(path, PROFILE).paragraphs[-1]
    assert (node.role, node.role_source) == (
        "heading_2",
        "explicit_structure",
    )
    assert node.repairable is True


def test_multiple_complex_fields_are_enumerated_separately_in_order(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "multiple-fields.docx",
        [
            {
                "text": "Two captions",
                "fields": [
                    " SEQ Figure \\* ARABIC ",
                    " SEQ Table \\* ARABIC ",
                ],
            }
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.fields == (
        "SEQ Figure \\* ARABIC",
        "SEQ Table \\* ARABIC",
    )


def test_conflicting_fields_are_preserved_as_conflict(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "field-conflict.docx",
        [
            {
                "text": "Conflicting fields",
                "fields": ["SEQ Figure", "SEQ Table"],
            }
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.role is None
    assert node.warning == "ROLE.CONFLICT"


def test_conflicting_bookmarks_are_preserved_as_conflict(tmp_path: Path) -> None:
    path = build_docx(
        tmp_path / "bookmark-conflict.docx",
        [
            {
                "text": "Conflicting bookmarks",
                "bookmarks": [
                    "thesis-role-figure_caption",
                    "thesis-role-table_caption",
                ],
            }
        ],
    )
    node = inspect_document(path, PROFILE).paragraphs[0]
    assert node.role is None
    assert node.warning == "ROLE.CONFLICT"


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


def test_text_pattern_highest_priority_wins(tmp_path: Path) -> None:
    path = build_docx(tmp_path / "priority.docx", [{"text": "Overlap"}])
    profile = replace(
        PROFILE,
        role_detection=RoleDetection(
            text_patterns=MappingProxyType(
                {
                    "figure_caption": (
                        TextPattern("^Overlap$", ("unicode",), 10),
                    ),
                    "table_caption": (
                        TextPattern("^Overlap$", ("unicode",), 20),
                    ),
                }
            ),
            position_constraints=MappingProxyType({}),
        ),
    )
    node = inspect_document(path, profile).paragraphs[0]
    assert (node.role, node.role_source) == ("table_caption", "text_pattern")


def test_text_pattern_priority_tie_between_roles_is_ambiguous(
    tmp_path: Path,
) -> None:
    path = build_docx(tmp_path / "priority-tie.docx", [{"text": "Overlap"}])
    profile = replace(
        PROFILE,
        role_detection=RoleDetection(
            text_patterns=MappingProxyType(
                {
                    "figure_caption": (
                        TextPattern("^Overlap$", ("unicode",), 20),
                    ),
                    "table_caption": (
                        TextPattern("^Overlap$", ("unicode",), 20),
                    ),
                }
            ),
            position_constraints=MappingProxyType({}),
        ),
    )
    node = inspect_document(path, profile).paragraphs[0]
    assert node.role is None
    assert node.warning == "ROLE.AMBIGUOUS"


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


def test_section_start_paragraph_tracks_paragraph_and_final_sectpr(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "sections.docx",
        [
            {"text": "Section one, paragraph one"},
            {"text": "Section one, paragraph two", "section_break": True},
            {"text": "Section two, paragraph one"},
            {"text": "Section two, paragraph two"},
        ],
    )
    sections = inspect_document(path, PROFILE).sections
    assert [section.start_paragraph for section in sections] == [1, 4]


def test_ooxml_roundtrip_preserves_unsupported_parts(tmp_path: Path) -> None:
    output = tmp_path / "roundtrip.docx"
    package = OoxmlPackage.open(FIXTURE)
    package.write(output)
    with ZipFile(output) as archive:
        assert archive.read("customXml/unsupported.bin") == b"\x00opaque\xff"


@pytest.mark.parametrize("declaration", [b"<!DOCTYPE root>", b"<!ENTITY x 'y'>"])
def test_unsafe_xml_declaration_after_long_prefix_is_rejected(
    declaration: bytes,
) -> None:
    data = b" " * 5000 + declaration + b"<root/>"
    with pytest.raises(OoxmlError, match="unsafe XML declaration"):
        parse_xml(data, part_name="word/document.xml")


def test_relationship_comments_are_ignored(tmp_path: Path) -> None:
    path = build_docx(tmp_path / "relationship-comment.docx", [{"text": "Text"}])
    with ZipFile(path) as archive:
        relationships = archive.read("_rels/.rels")
    relationships = relationships.replace(
        b">", b"><!-- legal package relationship comment -->", 1
    )
    replace_zip_part(path, "_rels/.rels", relationships)
    assert OoxmlPackage.open(path).relationships()


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
