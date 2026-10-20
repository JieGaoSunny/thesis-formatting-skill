from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from thesis_format import cli


ROOT = Path(__file__).parents[1]
PROFILE = ROOT / "rules" / "apple-university.yaml"
FIXTURE = ROOT / "tests" / "fixtures" / "minimal-roles.docx"


def test_cli_version() -> None:
    result = subprocess.run(
        ["uv", "run", "thesis-format", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "thesis-formatting-skill 0.1.0"


def test_module_help_lists_every_task10_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "thesis_format", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "usage: thesis-format" in result.stdout
    for command in ("audit", "format", "export", "preview", "release-check"):
        assert command in result.stdout


def test_audit_subprocess_writes_requested_reports_and_returns_noncompliance(
    tmp_path: Path,
) -> None:
    json_report = tmp_path / "audit.json"
    markdown_report = tmp_path / "audit.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesis_format",
            "audit",
            str(FIXTURE),
            "--profile",
            str(PROFILE),
            "--report",
            str(json_report),
            "--markdown",
            str(markdown_report),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert json.loads(json_report.read_text(encoding="utf-8"))["findings"]
    assert markdown_report.read_text(encoding="utf-8").startswith(
        "# Thesis formatting audit"
    )
    assert str(json_report) in result.stdout
    assert str(markdown_report) in result.stdout


def test_format_never_overwrites_source_and_writes_requested_report(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(FIXTURE.read_bytes())
    before = source.read_bytes()
    output = tmp_path / "formatted.docx"
    report = tmp_path / "transformation.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesis_format",
            "format",
            str(source),
            "--profile",
            str(PROFILE),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode in {0, 1}
    assert source.read_bytes() == before
    assert output.is_file()
    assert json.loads(report.read_text(encoding="utf-8"))["output_path"] == str(
        output
    )
    assert str(output) in result.stdout
    assert str(report) in result.stdout


def test_format_rejects_source_as_output_without_modifying_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(FIXTURE.read_bytes())
    before = source.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesis_format",
            "format",
            str(source),
            "--profile",
            str(PROFILE),
            "--output",
            str(source),
            "--report",
            str(tmp_path / "report.json"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert source.read_bytes() == before
    assert "must differ" in result.stderr


def test_missing_input_is_invalid_input_exit_2(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "thesis_format",
            "audit",
            str(tmp_path / "missing.docx"),
            "--profile",
            str(PROFILE),
            "--report",
            str(tmp_path / "audit.json"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "does not exist" in result.stderr


@pytest.mark.parametrize(
    ("command", "arguments", "message"),
    (
        ("export", ("input.docx", "--output", "output.pdf"), "Task 11"),
        ("preview", ("input.docx", "--output-dir", "preview"), "Task 11"),
        (
            "release-check",
            (
                "input.docx",
                "--profile",
                "profile.yaml",
                "--report",
                "privacy.json",
            ),
            "Task 12",
        ),
    ),
)
def test_deferred_commands_report_clear_tooling_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    arguments: tuple[str, ...],
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("input.docx").write_bytes(b"docx")
    Path("profile.yaml").write_text("profile: invalid", encoding="utf-8")

    result = cli.main([command, *arguments])

    assert result == 2
    assert message in capsys.readouterr().err


def test_export_preview_and_release_check_use_injected_functions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")
    calls: list[tuple[str, tuple[Path, ...]]] = []

    def export(document: Path, output: Path) -> Path:
        calls.append(("export", (document, output)))
        output.write_bytes(b"pdf")
        return output

    def preview(document: Path, output_directory: Path) -> list[Path]:
        calls.append(("preview", (document, output_directory)))
        output_directory.mkdir()
        image = output_directory / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    def privacy(document: Path, profile_path: Path) -> dict[str, object]:
        calls.append(("privacy", (document, profile_path)))
        return {
            "schema_version": "1.0",
            "summary": {"errors": 0, "violations": 1, "warnings": 0},
            "findings": [],
        }

    dependencies = cli.CliDependencies(
        export_document=export,
        preview_document=preview,
        privacy_check=privacy,
    )
    pdf = tmp_path / "output.pdf"
    preview_dir = tmp_path / "preview"
    privacy_report = tmp_path / "privacy.json"

    assert (
        cli.main(
            ["export", str(source), "--output", str(pdf)],
            dependencies=dependencies,
        )
        == 0
    )
    assert (
        cli.main(
            ["preview", str(source), "--output-dir", str(preview_dir)],
            dependencies=dependencies,
        )
        == 0
    )
    assert (
        cli.main(
            [
                "release-check",
                str(source),
                "--profile",
                str(profile),
                "--report",
                str(privacy_report),
            ],
            dependencies=dependencies,
        )
        == 1
    )

    assert [name for name, _ in calls] == ["export", "preview", "privacy"]
    assert pdf.is_file()
    assert (preview_dir / "page-1.png").is_file()
    assert json.loads(privacy_report.read_text(encoding="utf-8"))["summary"][
        "violations"
    ] == 1
    stdout = capsys.readouterr().out
    for requested in (pdf, preview_dir, privacy_report):
        assert str(requested) in stdout
