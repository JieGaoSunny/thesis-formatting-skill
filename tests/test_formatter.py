from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from thesis_format.audit import audit_document
from thesis_format.contracts import validate_transformation_result
from thesis_format.demo.build import build_template
from thesis_format.demo.defects import DEFECTS
from thesis_format.format import format_document
from thesis_format.ooxml import OoxmlPackage
from thesis_format.profile import load_profile

from helpers.docx_factory import build_docx


ROOT = Path(__file__).parents[1]
PROFILE = load_profile(ROOT / "rules" / "apple-university.yaml")
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


@pytest.mark.parametrize(
    ("defect_name", "repaired_rule"),
    (
        ("wrong_paper_size", "PAGE.PAPER.SIZE"),
        ("wrong_body_margins", "PAGE.MARGIN.BODY"),
        ("wrong_section_start", "PAGE.SECTION.START"),
        ("mixed_fonts", "STYLE.DEFINITION"),
        ("manual_heading_numbers", "NUMBERING.MANUAL_HEADING"),
        ("unreliable_heading_styles", "STYLE.ROLE.MAPPING"),
        ("inconsistent_spacing", "STYLE.DEFINITION"),
        ("missing_page_numbers", "HEADER.FOOTER.PAGE_NUMBER"),
        ("broken_headers_footers", "HEADER.FOOTER.HEADER_SOURCE"),
        ("malformed_toc", "FIELD.TOC.REQUIRED"),
        ("caption_positions", "FIGURE.CAPTION.POSITION"),
        ("oversized_figure", "FIGURE.DIMENSIONS.MAX_WIDTH"),
        ("table_border_noise", "TABLE.BORDERS.THREE_LINE"),
        ("table_page_behavior", "TABLE.REPEAT_HEADER"),
        ("reference_indent", "REFERENCE.PARAGRAPH_FORMAT"),
        ("direct_formatting", "STYLE.DIRECT_FORMATTING"),
    ),
)
def test_formatter_repairs_each_demo_defect_without_content_loss(
    tmp_path: Path,
    defect_name: str,
    repaired_rule: str,
) -> None:
    source = build_template(tmp_path / "source.docx", PROFILE)
    DEFECTS[defect_name](source, source)
    before = source.read_bytes()
    output = tmp_path / "formatted.docx"

    report = format_document(source, output, PROFILE, clock=lambda: NOW)

    validate_transformation_result(report)
    assert source.read_bytes() == before
    assert report["content_comparison"]["equivalent"] is True
    assert repaired_rule not in {
        finding["rule_id"] for finding in report["post_audit"]["findings"]
    }


def test_full_repair_is_stable_preserves_unsupported_parts_and_clears_mandatory_findings(
    tmp_path: Path,
) -> None:
    source = build_template(tmp_path / "source.docx", PROFILE)
    for defect in DEFECTS.values():
        defect(source, source)
    with ZipFile(source, "a") as archive:
        archive.writestr("customXml/unsupported.bin", b"\x00opaque\xff")
    source_bytes = source.read_bytes()
    output = tmp_path / "formatted.docx"

    report = format_document(source, output, PROFILE, clock=lambda: NOW)

    validate_transformation_result(report)
    assert source.read_bytes() == source_bytes
    with ZipFile(output) as archive:
        assert archive.read("customXml/unsupported.bin") == b"\x00opaque\xff"
    assert report["content_comparison"]["equivalent"] is True
    assert report["post_audit"]["summary"]["violations"] == 0
    assert report["post_audit"]["summary"]["errors"] == 0
    assert report["changes"] == sorted(
        report["changes"],
        key=lambda change: (
            _location_key(change["location"]),
            change["rule_id"],
            change["change_id"],
        ),
    )

    second = format_document(
        source,
        tmp_path / "formatted-again.docx",
        PROFILE,
        clock=lambda: NOW,
    )
    assert [
        {key: value for key, value in change.items() if key != "change_id"}
        for change in report["changes"]
    ] == [
        {key: value for key, value in change.items() if key != "change_id"}
        for change in second["changes"]
    ]


def test_ambiguous_paragraph_is_untouched_and_reported_as_skipped(
    tmp_path: Path,
) -> None:
    source = build_docx(
        tmp_path / "ambiguous.docx",
        [{"text": "可能是标题也可能是正文"}],
        unsupported_part=True,
    )
    before_root = OoxmlPackage.open(source).xml("word/document.xml")
    before_xml = before_root.xpath(
        "string(.//w:p[1])", namespaces=NS
    )

    report = format_document(
        source,
        tmp_path / "formatted.docx",
        PROFILE,
        clock=lambda: NOW,
    )

    after_root = OoxmlPackage.open(tmp_path / "formatted.docx").xml(
        "word/document.xml"
    )
    assert after_root.xpath("string(.//w:p[1])", namespaces=NS) == before_xml
    assert any(
        change["status"] == "skipped"
        and change["rule_id"] == "SEMANTIC.AMBIGUOUS_ROLE"
        for change in report["changes"]
    )


def test_missing_cross_reference_target_is_not_invented(
    tmp_path: Path,
) -> None:
    source = build_docx(
        tmp_path / "crossref.docx",
        [{"text": "参见", "field": " REF missing_target "}],
    )

    report = format_document(
        source,
        tmp_path / "formatted.docx",
        PROFILE,
        clock=lambda: NOW,
    )

    assert "missing_target" not in OoxmlPackage.open(
        tmp_path / "formatted.docx"
    ).xml("word/document.xml").xpath(
        ".//w:bookmarkStart/@w:name", namespaces=NS
    )
    assert any(
        finding["rule_id"] == "FIELD.CROSS_REFERENCE.TARGET"
        for finding in report["post_audit"]["findings"]
    )
    assert any(
        change["rule_id"] == "FIELD.CROSS_REFERENCE.TARGET"
        and change["status"] == "skipped"
        for change in report["changes"]
    )


def test_output_contains_profile_numbering_fields_tables_and_page_geometry(
    tmp_path: Path,
) -> None:
    source = build_template(tmp_path / "source.docx", PROFILE)
    for defect in DEFECTS.values():
        defect(source, source)

    output = tmp_path / "formatted.docx"
    format_document(source, output, PROFILE, clock=lambda: NOW)
    package = OoxmlPackage.open(output)
    document = package.xml("word/document.xml")
    numbering = package.xml("word/numbering.xml")
    styles = package.xml("word/styles.xml")

    assert document.xpath(
        "count(.//w:sectPr/w:pgSz[@w:w='11906'][@w:h='16838'])",
        namespaces=NS,
    ) == len(document.xpath(".//w:sectPr", namespaces=NS))
    assert numbering.xpath(
        ".//w:lvl[w:numFmt[@w:val='chineseCounting']]"
        "[w:lvlText[@w:val='第%1章']]",
        namespaces=NS,
    )
    assert document.xpath(
        ".//w:p[w:pPr/w:pStyle[@w:val='AppleFigureCaption']]"
        "[.//w:instrText[contains(., 'STYLEREF')]]"
        "[.//w:instrText[contains(., 'SEQ')]]",
        namespaces=NS,
    )
    assert styles.xpath(
        ".//w:style[@w:styleId='AppleBody']"
        "/w:pPr/w:spacing[@w:lineRule='exact'][@w:line='400']",
        namespaces=NS,
    )
    table = document.xpath(".//w:tbl", namespaces=NS)[0]
    assert table.xpath("./w:tr[1]/w:trPr/w:tblHeader", namespaces=NS)
    assert not table.xpath(
        ".//w:tr[not(w:trPr/w:cantSplit)]", namespaces=NS
    )
    assert not table.xpath(
        "./w:tblPr/w:tblBorders/*"
        "[not(self::w:top or self::w:bottom)]",
        namespaces=NS,
    )


def test_table_caption_is_moved_above_with_bound_object_identity(
    tmp_path: Path,
) -> None:
    source = build_template(tmp_path / "source.docx", PROFILE)
    package = OoxmlPackage.open(source)
    root = package.xml("word/document.xml")
    body = root.find("w:body", namespaces=NS)
    table = body.find("w:tbl", namespaces=NS)
    caption = table.getprevious()
    body.remove(caption)
    body.insert(body.index(table) + 1, caption)
    package.write(source, {"word/document.xml": root})

    report = format_document(
        source,
        tmp_path / "formatted.docx",
        PROFILE,
        clock=lambda: NOW,
    )

    assert report["content_comparison"]["equivalent"] is True
    change = next(
        change
        for change in report["changes"]
        if change["rule_id"] == "TABLE.CAPTION.POSITION"
    )
    assert change["operation"] == "move_caption"
    assert change["status"] == "applied"
    assert change["node_id"]
    assert len(change["relationship_sha256"]) == 64


def _location_key(location: str) -> tuple[object, ...]:
    order = {
        "document": 0,
        "section": 1,
        "paragraph": 2,
        "table": 3,
        "cell": 4,
        "header": 5,
        "footer": 6,
        "part": 7,
    }
    if location == "document":
        return (0,)
    kind, value = location.split(":", 1)
    if kind == "cell":
        return (order[kind], *(int(item) for item in value.split("/")))
    if kind == "part":
        return (order[kind], value)
    return (order[kind], int(value))
