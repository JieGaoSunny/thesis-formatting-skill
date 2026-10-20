from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path

import fitz
import pikepdf
import pytest
import yaml
from pikepdf.models.metadata import PdfMetadata

from thesis_format import cli
from thesis_format.contracts import validate_privacy_report
from thesis_format.privacy import release_check, render_privacy_markdown


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "rules" / "apple-university.yaml"
DENYLIST = ROOT / "tests" / "fixtures" / "privacy" / "synthetic-denylist.txt"


def _write_docx(path: Path, parts: dict[str, str], media: tuple[str, ...] = ()) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        for name, content in parts.items():
            package.writestr(name, content)
        for name in media:
            package.writestr(name, b"image")


def _rules(report: dict[str, object]) -> list[str]:
    return [finding["rule_id"] for finding in report["findings"]]  # type: ignore[index]


def _profile_without_forbidden_key(
    tmp_path: Path,
    key: str,
) -> Path:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    profile["privacy"]["forbidden_metadata_keys"] = [
        value
        for value in profile["privacy"]["forbidden_metadata_keys"]
        if value.casefold() != key.casefold()
    ]
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _profile_with_forbidden_keys(
    tmp_path: Path,
    *keys: str,
) -> Path:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    profile["privacy"]["forbidden_metadata_keys"] = list(keys)
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _write_pdf_metadata(path: Path, key: str, value: str) -> None:
    document = pikepdf.Pdf.new()
    document.add_blank_page()
    document.docinfo[pikepdf.Name(key)] = value
    document.save(path)


def _write_pdf_xmp(
    path: Path,
    key: str,
    value: str | list[str],
) -> None:
    PdfMetadata.register_xml_namespace(
        "https://example.test/privacy-metadata/1.0/",
        "privacytest",
    )
    document = pikepdf.Pdf.new()
    document.add_blank_page()
    with document.open_metadata(
        set_pikepdf_as_editor=False,
        update_docinfo=False,
    ) as metadata:
        metadata[key] = value
    document.save(path)


def _write_pdf_with_malformed_xmp(path: Path) -> None:
    document = pikepdf.Pdf.new()
    document.add_blank_page()
    metadata = pikepdf.Stream(document, b"<x:xmpmeta><broken>")
    metadata.Type = pikepdf.Name.Metadata
    metadata.Subtype = pikepdf.Name.XML
    document.Root.Metadata = metadata
    document.save(path, fix_metadata_version=False)


def test_denylist_is_literal_casefolded_nfc_and_normalizes_path_separators(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "literal.txt").write_text(
        "SECRET STUDENT\nCafe\u0301\nC:\\Users\\secret-user\\thesis.docx\n",
        encoding="utf-8",
    )

    report = release_check(repository, PROFILE, DENYLIST)

    assert _rules(report).count("PRIVACY.DENYLIST") == 3
    assert all(
        finding["redacted_match_sha256"]
        for finding in report["findings"]  # type: ignore[index]
    )
    validate_privacy_report(report)


def test_denylist_rejects_missing_empty_unreadable_and_invalid_utf8(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    empty = tmp_path / "empty.txt"
    empty.write_text("# only a comment\n\n", encoding="utf-8")
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff")
    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_text("private", encoding="utf-8")
    unreadable.chmod(0)
    try:
        for path in (tmp_path / "missing.txt", empty, invalid, unreadable):
            with pytest.raises(ValueError, match="denylist configuration is invalid"):
                release_check(source, PROFILE, path)
    finally:
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_scans_docx_hidden_parts_relationships_properties_and_media_names(
    tmp_path: Path,
) -> None:
    document = tmp_path / "thesis.docx"
    private = "private@example.test"
    _write_docx(
        document,
        {
            "word/document.xml": f"<document>{private}</document>",
            "word/header1.xml": f"<header>{private}</header>",
            "word/footer1.xml": f"<footer>{private}</footer>",
            "word/comments.xml": f"<comments>{private}</comments>",
            "word/_rels/document.xml.rels": (
                f'<Relationships><Relationship Target="{private}"/></Relationships>'
            ),
            "docProps/core.xml": f"<core>{private}</core>",
            "docProps/app.xml": f"<app>{private}</app>",
            "docProps/custom.xml": f"<props>{private}</props>",
        },
        (f"word/media/{private}.png",),
    )

    report = release_check(document, PROFILE, DENYLIST)

    locations = {finding["location"] for finding in report["findings"]}  # type: ignore[index]
    assert {
        "part:word/document.xml",
        "part:word/header1.xml",
        "part:word/footer1.xml",
        "part:word/comments.xml",
        "part:word/_rels/document.xml.rels",
        "part:docProps/core.xml",
        "part:docProps/app.xml",
        "part:docProps/custom.xml",
        "part:word/media/[REDACTED].png",
    } <= locations


def test_required_ooxml_entry_names_are_not_treated_as_placeholders(
    tmp_path: Path,
) -> None:
    document = tmp_path / "thesis.docx"
    _write_docx(
        document,
        {
            "_rels/.rels": "<Relationships/>",
            "word/document.xml": "<document/>",
            "word/_rels/document.xml.rels": "<Relationships/>",
        },
    )

    report = release_check(document, PROFILE, DENYLIST)

    assert "PRIVACY.UNRESOLVED_PLACEHOLDER" not in _rules(report)


def test_docx_forbidden_metadata_keys_come_from_profile_for_all_property_parts(
    tmp_path: Path,
) -> None:
    document = tmp_path / "thesis.docx"
    _write_docx(
        document,
        {
            "docProps/core.xml": (
                '<cp:coreProperties '
                'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:creator>艾苹</dc:creator>"
                "<cp:lastModifiedBy>艾苹</cp:lastModifiedBy>"
                "</cp:coreProperties>"
            ),
            "docProps/app.xml": (
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/'
                '2006/extended-properties">'
                "<Company>Apple University</Company>"
                "</Properties>"
            ),
            "docProps/custom.xml": (
                '<Properties '
                'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
                'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
                '<property name="manager"><vt:lpwstr>艾苹</vt:lpwstr></property>'
                "</Properties>"
            ),
        },
    )

    report = release_check(document, PROFILE, DENYLIST)

    metadata_findings = [
        finding
        for finding in report["findings"]  # type: ignore[index]
        if finding["rule_id"] == "PRIVACY.METADATA"
    ]
    assert len(metadata_findings) == 4
    assert {finding["location"] for finding in metadata_findings} == {
        "part:docProps/core.xml:metadata:creator",
        "part:docProps/core.xml:metadata:lastModifiedBy",
        "part:docProps/app.xml:metadata:Company",
        "part:docProps/custom.xml:metadata:manager",
    }
    assert not any(
        rule.startswith("PRIVACY.IDENTITY.") for rule in _rules(report)
    )


def test_permitted_docx_identity_metadata_must_use_fictional_value(
    tmp_path: Path,
) -> None:
    profile = _profile_without_forbidden_key(tmp_path, "creator")
    real_document = tmp_path / "real.docx"
    fictional_document = tmp_path / "fictional.docx"
    core_template = (
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:creator>{author}</dc:creator>"
        "</cp:coreProperties>"
    )
    _write_docx(
        real_document,
        {"docProps/core.xml": core_template.format(author="Real Person")},
    )
    _write_docx(
        fictional_document,
        {"docProps/core.xml": core_template.format(author="艾苹")},
    )

    real_report = release_check(real_document, profile, DENYLIST)
    fictional_report = release_check(fictional_document, profile, DENYLIST)

    assert "PRIVACY.IDENTITY.AUTHOR" in _rules(real_report)
    assert "PRIVACY.METADATA" not in _rules(real_report)
    assert not any(
        rule.startswith(("PRIVACY.IDENTITY.", "PRIVACY.METADATA"))
        for rule in _rules(fictional_report)
    )


def test_scans_symlink_target_text_without_following_including_broken_links(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    targets = {
        "absolute-link": "/Users/private-person/Documents/thesis.docx",
        "denylist-link": "../Secret Student/materials",
        "pattern-link": "../private@example.test/materials",
        "safe-link": "../public-assets/figure.png",
    }
    for name, target in targets.items():
        (repository / name).symlink_to(target)

    report = release_check(repository, PROFILE, DENYLIST)

    findings_by_path = {
        finding["path"]: finding["rule_id"]
        for finding in report["findings"]  # type: ignore[index]
    }
    assert findings_by_path["absolute-link"] == "PRIVACY.ABSOLUTE_PATH"
    assert findings_by_path["denylist-link"] == "PRIVACY.DENYLIST"
    assert findings_by_path["pattern-link"] in {
        "PRIVACY.EMAIL",
        "PRIVACY.PATTERN.EMAIL",
    }
    assert "safe-link" not in findings_by_path
    assert set(targets) <= set(report["scanned_files"])  # type: ignore[arg-type]
    serialized = json.dumps(report)
    assert all(target not in serialized for target in targets.values())


def test_contained_symlink_scans_target_string_without_following_target(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private@example.test", encoding="utf-8")
    (repository / "safe-link").symlink_to("../outside.txt")

    report = release_check(repository, PROFILE, DENYLIST)

    assert _rules(report) == []
    assert report["scanned_files"] == ["safe-link"]


def test_rejects_top_level_source_symlink_with_cli_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "source"
    source.symlink_to(target, target_is_directory=True)
    report_path = tmp_path / "privacy.json"

    with pytest.raises(ValueError, match="privacy scan source is invalid"):
        release_check(source, PROFILE, DENYLIST)

    result = cli.main(
        [
            "release-check",
            str(source),
            "--profile",
            str(PROFILE),
            "--denylist",
            str(DENYLIST),
            "--report",
            str(report_path),
        ]
    )

    assert result == 2
    assert "privacy scan source is invalid" in capsys.readouterr().err
    assert not report_path.exists()


def test_scans_pdf_text_and_metadata(tmp_path: Path) -> None:
    pdf = tmp_path / "thesis.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "private@example.test")
    document.set_metadata({"author": "Secret Student", "title": "safe"})
    document.save(pdf)
    document.close()

    report = release_check(pdf, PROFILE, DENYLIST)

    locations = {finding["location"] for finding in report["findings"]}  # type: ignore[index]
    assert "page:1" in locations
    assert "metadata:author" in locations


@pytest.mark.parametrize(
    ("configured_key", "pdf_key", "private_value"),
    [
        ("CrEaToR", "/Creator", "艾苹"),
        ("/producer", "/Producer", "Private PDF producer"),
        ("creator", "/Author", "Private PDF author"),
        ("company", "/Company", "Private PDF company"),
        ("customowner", "/CustomOwner", "Private custom owner"),
    ],
)
def test_pdf_forbidden_metadata_keys_are_casefolded_aliased_and_redacted(
    tmp_path: Path,
    configured_key: str,
    pdf_key: str,
    private_value: str,
) -> None:
    pdf = tmp_path / "metadata.pdf"
    _write_pdf_metadata(pdf, pdf_key, private_value)
    profile = _profile_with_forbidden_keys(tmp_path, configured_key)

    report = release_check(pdf, profile, DENYLIST)
    markdown = render_privacy_markdown(report)

    metadata_findings = [
        finding
        for finding in report["findings"]  # type: ignore[index]
        if finding["rule_id"] == "PRIVACY.METADATA"
    ]
    assert len(metadata_findings) == 1
    assert metadata_findings[0]["location"] == (
        f"metadata:{pdf_key.lstrip('/').casefold()}"
    )
    assert private_value not in json.dumps(report, ensure_ascii=False)
    assert private_value not in markdown


@pytest.mark.parametrize(
    ("configured_key", "xmp_key", "xmp_value", "expected_key", "private_value"),
    [
        (
            "creator",
            "xmp:CreatorTool",
            "XMP-only private creator tool",
            "creatortool",
            "XMP-only private creator tool",
        ),
        (
            "creator",
            "dc:creator",
            ["XMP-only private author"],
            "creator",
            "XMP-only private author",
        ),
        (
            "producer",
            "pdf:Producer",
            "XMP-only private producer",
            "producer",
            "XMP-only private producer",
        ),
        (
            "customowner",
            "privacytest:CustomOwner",
            "XMP-only private custom owner",
            "customowner",
            "XMP-only private custom owner",
        ),
    ],
)
def test_pdf_xmp_only_forbidden_metadata_is_normalized_redacted_and_does_not_leak(
    tmp_path: Path,
    configured_key: str,
    xmp_key: str,
    xmp_value: str | list[str],
    expected_key: str,
    private_value: str,
) -> None:
    pdf = tmp_path / "xmp-only.pdf"
    _write_pdf_xmp(pdf, xmp_key, xmp_value)
    profile = _profile_with_forbidden_keys(tmp_path, configured_key)

    with pikepdf.open(pdf) as document:
        assert not document.docinfo

    report = release_check(pdf, profile, DENYLIST)
    markdown = render_privacy_markdown(report)

    metadata_findings = [
        finding
        for finding in report["findings"]  # type: ignore[index]
        if finding["rule_id"] == "PRIVACY.METADATA"
    ]
    assert len(metadata_findings) == 1
    assert metadata_findings[0]["location"] == f"metadata:{expected_key}"
    assert private_value not in json.dumps(report, ensure_ascii=False)
    assert private_value not in markdown


def test_malformed_pdf_xmp_fails_closed_as_unreadable(tmp_path: Path) -> None:
    pdf = tmp_path / "malformed-xmp.pdf"
    _write_pdf_with_malformed_xmp(pdf)

    report = release_check(pdf, PROFILE, DENYLIST)

    unreadable = [
        finding
        for finding in report["findings"]  # type: ignore[index]
        if finding["rule_id"] == "PRIVACY.UNREADABLE"
    ]
    assert len(unreadable) == 1
    assert unreadable[0]["location"] == "pdf"


def test_detects_generic_private_values_fictional_mismatches_and_placeholders(
    tmp_path: Path,
) -> None:
    source = tmp_path / "thesis.txt"
    source.write_text(
        "\n".join(
            (
                "Author: Real Person",
                "Student ID: 202412345678",
                "Company: Real Company",
                "Phone: +86 138-0013-8000",
                "Email: someone@example.com",
                "/Users/real-person/Documents/thesis.docx",
                "【填写姓名】",
                "TBD",
            )
        ),
        encoding="utf-8",
    )

    report = release_check(source, PROFILE, DENYLIST)

    rules = set(_rules(report))
    assert "PRIVACY.ABSOLUTE_PATH" in rules
    assert "PRIVACY.PATTERN.EMAIL" in rules
    assert "PRIVACY.PHONE" in rules
    assert "PRIVACY.IDENTITY.AUTHOR" in rules
    assert "PRIVACY.IDENTITY.STUDENT_ID" in rules
    assert "PRIVACY.IDENTITY.COMPANY" in rules
    assert "PRIVACY.UNRESOLVED_PLACEHOLDER" in rules


def test_windows_path_detection_excludes_uri_schemes_but_catches_drive_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "thesis.txt"
    source.write_text(
        "Documentation: https://example.test/privacy\n"
        "Local file: C:\\Users\\real-person\\thesis.docx\n",
        encoding="utf-8",
    )

    report = release_check(source, PROFILE, DENYLIST)

    absolute_paths = [
        finding
        for finding in report["findings"]  # type: ignore[index]
        if finding["rule_id"] == "PRIVACY.ABSOLUTE_PATH"
    ]
    assert len(absolute_paths) == 1


def test_identity_match_in_filename_redacts_the_entire_segment(tmp_path: Path) -> None:
    source = tmp_path / "Author-Real Person.txt"
    source.write_text("safe", encoding="utf-8")

    report = release_check(source, PROFILE, DENYLIST)

    assert "PRIVACY.IDENTITY.AUTHOR" in _rules(report)
    assert {finding["path"] for finding in report["findings"]} == {  # type: ignore[index]
        "[REDACTED].txt"
    }
    assert "Real Person" not in json.dumps(report)


def test_required_apple_university_values_are_clean_where_identity_fields_exist(
    tmp_path: Path,
) -> None:
    source = tmp_path / "thesis.txt"
    source.write_text(
        "Institution: Apple University\n"
        "作者: 艾苹\n"
        "Student ID: APPLE-0001\n"
        "Adviser: 林果教授\n",
        encoding="utf-8",
    )

    report = release_check(source, PROFILE, DENYLIST)

    assert not any(rule.startswith("PRIVACY.IDENTITY.") for rule in _rules(report))


def test_private_values_never_leak_in_report_markdown_or_cli_streams(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "private@example.test"
    repository.mkdir()
    (repository / "Secret Student.txt").write_text(
        "private@example.test", encoding="utf-8"
    )
    report_path = tmp_path / "privacy.json"
    markdown_path = tmp_path / "privacy.md"

    result = cli.main(
        [
            "release-check",
            str(repository),
            "--profile",
            str(PROFILE),
            "--denylist",
            str(DENYLIST),
            "--report",
            str(report_path),
            "--markdown",
            str(markdown_path),
        ]
    )

    captured = capsys.readouterr()
    outputs = (
        report_path.read_text(encoding="utf-8"),
        markdown_path.read_text(encoding="utf-8"),
        captured.out,
        captured.err,
        render_privacy_markdown(release_check(repository, PROFILE, DENYLIST)),
    )
    assert result == 1
    for output in outputs:
        assert "private@example.test" not in output.casefold()
        assert "secret student" not in output.casefold()
    report = json.loads(outputs[0])
    assert "[REDACTED].txt" in {item["path"] for item in report["findings"]}


def test_unreadable_in_scope_file_is_a_finding_and_order_is_deterministic(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    first = repository / "b.txt"
    first.write_text("private@example.test", encoding="utf-8")
    second = repository / "a.txt"
    second.write_text("Secret Student", encoding="utf-8")
    unreadable = repository / "locked.txt"
    unreadable.write_text("safe", encoding="utf-8")
    unreadable.chmod(0)
    try:
        report_one = release_check(repository, PROFILE, DENYLIST)
        report_two = release_check(repository, PROFILE, DENYLIST)
    finally:
        unreadable.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert report_one == report_two
    assert "PRIVACY.UNREADABLE" in _rules(report_one)
    assert report_one["findings"] == sorted(
        report_one["findings"],
        key=lambda item: (
            item["path"],
            item["location"],
            item["rule_id"],
            item["redacted_match_sha256"],
            item["finding_id"],
        ),
    )


def test_cli_defaults_to_repository_dot_privacy_denylist(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".privacy-denylist.txt").write_text(
        "Synthetic Private Name\n", encoding="utf-8"
    )
    (repository / "thesis.txt").write_text(
        "Synthetic Private Name", encoding="utf-8"
    )
    report_path = tmp_path / "privacy.json"

    result = cli.main(
        [
            "release-check",
            str(repository),
            "--profile",
            str(PROFILE),
            "--report",
            str(report_path),
        ]
    )

    assert result == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert _rules(report) == ["PRIVACY.DENYLIST"]
