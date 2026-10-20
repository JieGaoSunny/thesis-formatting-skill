from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from jsonschema import Draft202012Validator

from thesis_format.contracts import canonical_json, load_schema
from thesis_format.profile import load_profile
from thesis_format.snapshot import (
    assign_node_ids,
    compare_snapshots,
    extract_snapshot,
    normalize_text,
    strip_manual_numbering,
    write_content_reports,
)


ROOT = Path(__file__).parents[1]
PROFILE = load_profile(ROOT / "rules" / "apple-university.yaml")


def _field(paragraph, instruction: str, result: str) -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction_node = OxmlElement("w:instrText")
    instruction_node.text = instruction
    separator = OxmlElement("w:fldChar")
    separator.set(qn("w:fldCharType"), "separate")
    begin_run._r.extend((begin, instruction_node, separator))
    paragraph.add_run(result)
    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


def _save(document: Document, path: Path) -> Path:
    document.save(path)
    return path


def _add_image_relationship(path: Path, media: bytes = b"same-image") -> None:
    replacement = path.with_suffix(".replacement.docx")
    with ZipFile(path) as source, ZipFile(
        replacement, "w", compression=ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "word/document.xml":
                marker = b"</w:p>"
                drawing = (
                    '<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
                    'drawingml/2006/wordprocessingDrawing"><wp:docPr id="7" name="Picture 7" '
                    'descr="  Cafe\u0301\u00a0tree  "/><a:graphic xmlns:a="http://schemas.'
                    'openxmlformats.org/drawingml/2006/main"><a:graphicData><pic:pic '
                    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                    '<pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships" r:embed="rIdSnapshotImage"/>'
                    "</pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline>"
                    "</w:drawing></w:r>"
                ).encode()
                data = data.replace(marker, drawing + marker, 1)
            elif info.filename == "word/_rels/document.xml.rels":
                relationship = (
                    b'<Relationship Id="rIdSnapshotImage" '
                    b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    b'relationships/image" Target="media/snapshot.bin"/>'
                )
                data = data.replace(b"</Relationships>", relationship + b"</Relationships>")
            target.writestr(info, data)
        target.writestr("word/media/snapshot.bin", media)
    replacement.replace(path)


def _snapshot(nodes: list[dict[str, object]]) -> dict[str, object]:
    return _snapshot_stories(body=nodes)


def _snapshot_stories(
    *,
    body: list[dict[str, object]] | None = None,
    headers: list[dict[str, object]] | None = None,
    footers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "snapshot_id": "0" * 16,
        "document_sha256": "a" * 64,
        "body": body or [],
        "headers": headers or [],
        "footers": footers or [],
    }


def _node(
    node_id: str,
    text: str,
    index: int,
    *,
    node_type: str = "paragraph",
    relationship_hash: str | None = None,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "source_location": {
            "part": "word/document.xml",
            "path": f"/w:document/w:body/*[{index + 1}]",
            "index": index,
        },
        "normalized_text": text,
        "relationship_hash": relationship_hash,
    }


def test_normalizes_unicode_line_endings_and_all_whitespace() -> None:
    assert normalize_text("  Cafe\u0301\r\n\u00a0\t中文  ") == "Café 中文"
    assert normalize_text("，\u2003。") == "， 。"


def test_strips_manual_numbering_only_for_confirmed_profile_role() -> None:
    assert strip_manual_numbering("1.2 研究背景", "heading_2", PROFILE) == "研究背景"
    assert strip_manual_numbering("1.2 研究背景", None, PROFILE) == "1.2 研究背景"
    assert strip_manual_numbering("图 1-2 苹果树", "figure_caption", PROFILE) == "苹果树"
    assert strip_manual_numbering("[12] Apple study.", "reference", PROFILE) == "Apple study."


def test_extracts_fields_tables_references_headers_footers_and_empty_cells(
    tmp_path: Path,
) -> None:
    document = Document()
    document.add_paragraph("")
    toc = document.add_paragraph("目录 ")
    _field(toc, ' TOC \\o "1-3" ', "第一章 绪论 1")
    caption = document.add_paragraph("图 ")
    _field(caption, " SEQ Figure ", "1-1")
    caption.add_run(" 苹果树")
    prose = document.add_paragraph("结果见")
    _field(prose, " REF target ", "图 1-1")
    prose.add_run("。")
    document.add_paragraph("参考文献")
    reference = document.add_paragraph("[1] Apple Research Group.")
    reference.style = document.styles["Normal"]
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = ""
    table.cell(1, 0).text = "C"
    table.cell(1, 1).text = "D"
    document.sections[0].header.paragraphs[0].text = "Header One"
    footer = document.sections[0].footer.paragraphs[0]
    _field(footer, " PAGE ", "9")
    footer.add_run(" Footer")
    path = _save(document, tmp_path / "story.docx")

    snapshot = extract_snapshot(path, PROFILE)

    Draft202012Validator(load_schema("content-snapshot")).validate(snapshot)
    texts = [node["normalized_text"] for node in snapshot["body"]]
    assert "" not in [
        node["normalized_text"]
        for node in snapshot["body"]
        if node["node_type"] == "paragraph"
    ]
    assert texts[:5] == ["目录", "苹果树", "结果见。", "参考文献", "Apple Research Group."]
    assert snapshot["body"][1]["node_type"] == "caption"
    cells = [node["normalized_text"] for node in snapshot["body"] if node["node_type"] == "table"]
    assert cells == ["A", "", "C", "D"]
    assert [node["normalized_text"] for node in snapshot["headers"]] == ["Header One"]
    assert [node["normalized_text"] for node in snapshot["footers"]] == ["Footer"]


def test_extracts_figure_alt_text_and_target_sha256(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("anchor")
    path = _save(document, tmp_path / "figure.docx")
    _add_image_relationship(path)

    snapshot = extract_snapshot(path, PROFILE)
    image = next(node for node in snapshot["body"] if node["node_type"] == "image")

    import hashlib

    assert image["normalized_text"] == "Café tree"
    assert image["relationship_hash"] == hashlib.sha256(b"same-image").hexdigest()


def test_duplicate_nodes_get_ordinals_and_prefix_collisions_extend() -> None:
    payload = ["1.0", "paragraph", "same", "", 0]
    duplicate = ["1.0", "paragraph", "same", "", 1]
    digests = iter(
        [
            "0123456789abcdef1111" + "0" * 44,
            "0123456789abcdef2222" + "0" * 44,
        ]
    )

    ids = assign_node_ids([payload, duplicate], digest_function=lambda _: next(digests))

    assert ids == ["0123456789abcdef1111", "0123456789abcdef2222"]


def test_duplicate_paragraphs_and_section_stories_remain_distinct(
    tmp_path: Path,
) -> None:
    document = Document()
    document.add_paragraph("Repeated")
    document.add_paragraph("Repeated")
    first = document.sections[0]
    first.header.paragraphs[0].text = "First header"
    first.footer.paragraphs[0].text = "First footer"
    second = document.add_section()
    second.header.is_linked_to_previous = False
    second.footer.is_linked_to_previous = False
    second.header.paragraphs[0].text = "Second header"
    second.footer.paragraphs[0].text = "Second footer"

    snapshot = extract_snapshot(_save(document, tmp_path / "sections.docx"), PROFILE)

    repeated_ids = [
        node["node_id"]
        for node in snapshot["body"]
        if node["normalized_text"] == "Repeated"
    ]
    assert len(repeated_ids) == 2
    assert len(set(repeated_ids)) == 2
    assert [node["normalized_text"] for node in snapshot["headers"]] == [
        "First header",
        "Second header",
    ]
    assert [node["normalized_text"] for node in snapshot["footers"]] == [
        "First footer",
        "Second footer",
    ]
    assert snapshot["headers"][0]["source_location"]["path"].startswith("/section[1]/")
    assert snapshot["headers"][1]["source_location"]["path"].startswith("/section[2]/")


def test_compare_allows_only_declared_caption_move_adjacent_to_same_object() -> None:
    object_hash = "b" * 64
    caption = _node("c" * 16, "Apple tree", 0, node_type="caption")
    image = _node(
        "d" * 16,
        "Apple tree image",
        1,
        node_type="image",
        relationship_hash=object_hash,
    )
    before = _snapshot([caption, image])
    after = _snapshot(
        [
            {**image, "source_location": {**image["source_location"], "index": 0}},
            {**caption, "source_location": {**caption["source_location"], "index": 1}},
        ]
    )

    comparison = compare_snapshots(
        before,
        after,
        changes=[
            {
                "rule_id": "FIGURE.CAPTION.POSITION",
                "operation": "move_caption",
                "status": "applied",
                "node_id": caption["node_id"],
                "relationship_sha256": object_hash,
            }
        ],
    )

    assert comparison["equivalent"] is True
    assert comparison["differences"] == []


@pytest.mark.parametrize(
    "change",
    [
        {
            "rule_id": "FIGURE.CAPTION.POSITION",
            "operation": "move_caption",
            "status": "applied",
            "relationship_sha256": "b" * 64,
        },
        {
            "rule_id": "FIGURE.CAPTION.POSITION",
            "operation": "move_caption",
            "status": "applied",
            "node_id": "e" * 16,
            "relationship_sha256": "b" * 64,
        },
        {
            "rule_id": "FIGURE.CAPTION.POSITION",
            "operation": "move_caption",
            "status": "applied",
            "node_id": "c" * 16,
            "relationship_sha256": "f" * 64,
        },
        {
            "rule_id": "FIGURE.UNRELATED",
            "operation": "move_caption",
            "status": "applied",
            "node_id": "c" * 16,
            "relationship_sha256": "b" * 64,
        },
    ],
)
def test_compare_rejects_caption_move_without_exact_transformation_binding(
    change: dict[str, object],
) -> None:
    object_hash = "b" * 64
    caption = _node("c" * 16, "Apple tree", 0, node_type="caption")
    image = _node(
        "d" * 16,
        "Apple tree image",
        1,
        node_type="image",
        relationship_hash=object_hash,
    )
    after = [
        {**image, "source_location": {**image["source_location"], "index": 0}},
        {**caption, "source_location": {**caption["source_location"], "index": 1}},
    ]

    comparison = compare_snapshots(
        _snapshot([caption, image]),
        _snapshot(after),
        changes=[change],
    )

    assert comparison["equivalent"] is False
    assert {difference["kind"] for difference in comparison["differences"]} == {
        "reordered"
    }


def test_compare_rejects_caption_exemption_for_paragraph_or_nonadjacent_object() -> None:
    object_hash = "b" * 64
    paragraph = _node("c" * 16, "Apple tree", 0)
    image = _node(
        "d" * 16,
        "Apple tree image",
        1,
        node_type="image",
        relationship_hash=object_hash,
    )
    spacer = _node("e" * 16, "Unrelated prose", 2)
    change = {
        "rule_id": "FIGURE.CAPTION.POSITION",
        "operation": "move_caption",
        "status": "applied",
        "node_id": paragraph["node_id"],
        "relationship_sha256": object_hash,
    }

    paragraph_comparison = compare_snapshots(
        _snapshot([paragraph, image]),
        _snapshot(
            [
                {**image, "source_location": {**image["source_location"], "index": 0}},
                {**paragraph, "source_location": {**paragraph["source_location"], "index": 1}},
            ]
        ),
        changes=[change],
    )
    caption = {**paragraph, "node_type": "caption"}
    nonadjacent_comparison = compare_snapshots(
        _snapshot([caption, spacer, image]),
        _snapshot(
            [
                {**image, "source_location": {**image["source_location"], "index": 0}},
                spacer,
                {**caption, "source_location": {**caption["source_location"], "index": 2}},
            ]
        ),
        changes=[change],
    )

    assert paragraph_comparison["equivalent"] is False
    assert nonadjacent_comparison["equivalent"] is False


def test_extracts_notes_and_equations_deterministically(tmp_path: Path) -> None:
    document = Document()
    document.add_paragraph("Body")
    path = _save(document, tmp_path / "notes-and-equations.docx")
    replacement = path.with_suffix(".replacement.docx")
    math = (
        b'<w:p><m:oMathPara xmlns:m="http://schemas.openxmlformats.org/'
        b'officeDocument/2006/math"><m:oMath><m:r><m:t>x + 1</m:t></m:r>'
        b"</m:oMath></m:oMathPara></w:p>"
    )
    footnotes = (
        b'<w:footnotes xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:footnote w:id="-1"><w:p><w:r>'
        b"<w:t>separator</w:t></w:r></w:p></w:footnote>"
        b'<w:footnote w:id="2"><w:p><w:r><w:t>Second note</w:t></w:r></w:p>'
        b'</w:footnote><w:footnote w:id="1"><w:p><w:r><w:t>First note</w:t>'
        b"</w:r></w:p></w:footnote></w:footnotes>"
    )
    endnotes = (
        b'<w:endnotes xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:endnote w:id="3"><w:p><w:r>'
        b"<w:t>End note</w:t></w:r></w:p></w:endnote></w:endnotes>"
    )
    with ZipFile(path) as source, ZipFile(
        replacement, "w", compression=ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "word/document.xml":
                data = data.replace(b"<w:sectPr", math + b"<w:sectPr", 1)
            target.writestr(info, data)
        target.writestr("word/footnotes.xml", footnotes)
        target.writestr("word/endnotes.xml", endnotes)
    replacement.replace(path)

    first = extract_snapshot(path, PROFILE)
    second = extract_snapshot(path, PROFILE)

    assert first == second
    assert [
        (node["node_type"], node["normalized_text"])
        for node in first["body"]
    ] == [
        ("paragraph", "Body"),
        ("equation", "x + 1"),
        ("footnote", "First note"),
        ("footnote", "Second note"),
        ("endnote", "End note"),
    ]


def test_compare_treats_body_to_header_move_as_remove_and_add() -> None:
    body_node = _node("1" * 16, "Moved text", 0)
    header_node = {
        **body_node,
        "node_type": "header",
        "source_location": {
            "part": "word/header1.xml",
            "path": "/w:hdr/w:p[1]",
            "index": 0,
        },
    }

    comparison = compare_snapshots(
        _snapshot_stories(body=[body_node]),
        _snapshot_stories(headers=[header_node]),
    )

    assert comparison["equivalent"] is False
    assert [difference["kind"] for difference in comparison["differences"]] == [
        "removed",
        "added",
    ]


def test_compare_rejects_prose_change_and_reports_explicit_kinds() -> None:
    before = _snapshot([_node("1" * 16, "Original prose.", 0)])
    after = _snapshot([_node("2" * 16, "Changed prose.", 0)])

    comparison = compare_snapshots(before, after)

    assert comparison["equivalent"] is False
    assert comparison["differences"][0]["kind"] == "changed"
    assert comparison["differences"][0]["before"]["normalized_text"] == "Original prose."
    assert comparison["differences"][0]["after"]["normalized_text"] == "Changed prose."


def test_compare_reports_added_removed_and_reordered() -> None:
    first = _node("1" * 16, "First", 0)
    second = _node("2" * 16, "Second", 1)
    removed = _node("3" * 16, "Removed", 2)
    added = _node("4" * 16, "Added", 2)
    before = _snapshot([first, second, removed])
    after = _snapshot(
        [
            {**second, "source_location": {**second["source_location"], "index": 0}},
            {**first, "source_location": {**first["source_location"], "index": 1}},
            added,
        ]
    )

    kinds = {difference["kind"] for difference in compare_snapshots(before, after)["differences"]}

    assert kinds == {"added", "removed", "reordered"}


def test_writes_canonical_snapshots_and_markdown_diff(tmp_path: Path) -> None:
    before = _snapshot([_node("1" * 16, "Before", 0)])
    after = _snapshot([_node("2" * 16, "After", 0)])
    comparison = compare_snapshots(before, after)

    paths = write_content_reports(tmp_path, before, after, comparison)

    assert paths == {
        "before": tmp_path / "content-before.json",
        "after": tmp_path / "content-after.json",
        "diff": tmp_path / "content-diff.md",
    }
    assert paths["before"].read_text(encoding="utf-8") == canonical_json(before)
    assert json.loads(paths["after"].read_text(encoding="utf-8")) == after
    markdown = paths["diff"].read_text(encoding="utf-8")
    assert "# Content preservation diff" in markdown
    assert "changed" in markdown
