from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

from thesis_format import cli
from thesis_format.contracts import stable_id


ROOT = Path(__file__).parents[1]
PROFILE = ROOT / "rules" / "apple-university.yaml"
FIXTURE = ROOT / "tests" / "fixtures" / "minimal-roles.docx"
RENDER_MANIFEST_FIXTURE = (
    ROOT / "tests" / "fixtures" / "contracts" / "render-manifest.json"
)
PDF_FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "render-output.pdf"


def _manifest_bytes(*, mode: str) -> bytes:
    manifest = json.loads(RENDER_MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest["environment"] = {
        "mode": mode,
        "canonical": mode == "canonical",
    }
    manifest["render_id"] = stable_id(
        {key: value for key, value in manifest.items() if key != "render_id"}
    )
    return (json.dumps(manifest) + "\n").encode()


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "thesis_format", "--version"],
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


def test_preview_help_explicitly_accepts_pdf_and_manifest() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "thesis_format", "preview", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "INPUT.pdf" in result.stdout
    assert "PDF" in result.stdout
    assert "--manifest" in result.stdout
    assert "DOCX preview" not in result.stdout


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


@pytest.mark.parametrize("alias_kind", ("hardlink", "symlink"))
def test_format_rejects_source_alias_as_output_before_writing(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(FIXTURE.read_bytes())
    before = source.read_bytes()
    output = tmp_path / "formatted.docx"
    if alias_kind == "hardlink":
        output.hardlink_to(source)
    else:
        output.symlink_to(source)
    report = tmp_path / "transformation.json"

    result = cli.main(
        [
            "format",
            str(source),
            "--profile",
            str(PROFILE),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )

    assert result == 2
    assert source.read_bytes() == before
    assert not report.exists()


@pytest.mark.parametrize("alias_kind", ("hardlink", "symlink"))
def test_format_rejects_output_report_alias_before_writing(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(FIXTURE.read_bytes())
    output = tmp_path / "formatted.docx"
    output.write_bytes(b"existing artifact")
    report = tmp_path / "transformation.json"
    if alias_kind == "hardlink":
        report.hardlink_to(output)
    else:
        report.symlink_to(output)

    result = cli.main(
        [
            "format",
            str(source),
            "--profile",
            str(PROFILE),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )

    assert result == 2
    assert output.read_bytes() == b"existing artifact"
    assert report.read_bytes() == b"existing artifact"


def test_collision_guard_rejects_resolved_report_manifest_alias(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    alias = tmp_path / "reports-alias"
    alias.symlink_to(reports, target_is_directory=True)

    with pytest.raises(ValueError, match="report.*manifest"):
        cli._reject_path_collisions(
            ("report", reports / "render.json"),
            ("manifest", alias / "render.json"),
        )


@pytest.mark.parametrize("alias_kind", ("direct", "hardlink", "symlink"))
@pytest.mark.parametrize(
    ("command", "artifact_option"),
    (
        ("audit", "--report"),
        ("audit", "--markdown"),
        ("format", "--output"),
        ("format", "--report"),
        ("release-check", "--report"),
    ),
)
def test_profile_input_cannot_alias_command_artifacts(
    tmp_path: Path,
    alias_kind: str,
    command: str,
    artifact_option: str,
) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(FIXTURE.read_bytes())
    profile = tmp_path / "profile.yaml"
    profile.write_bytes(PROFILE.read_bytes())
    profile_before = profile.read_bytes()
    artifact = profile
    if alias_kind != "direct":
        artifact = tmp_path / f"{command}-{artifact_option[2:]}"
        if alias_kind == "hardlink":
            artifact.hardlink_to(profile)
        else:
            artifact.symlink_to(profile)

    arguments = [
        command,
        str(source),
        "--profile",
        str(profile),
    ]
    if command == "audit":
        arguments.extend(
            [
                "--report",
                str(
                    artifact
                    if artifact_option == "--report"
                    else tmp_path / "audit.json"
                ),
                "--markdown",
                str(
                    artifact
                    if artifact_option == "--markdown"
                    else tmp_path / "audit.md"
                ),
            ]
        )
    elif command == "format":
        arguments.extend(
            [
                "--output",
                str(
                    artifact
                    if artifact_option == "--output"
                    else tmp_path / "formatted.docx"
                ),
                "--report",
                str(
                    artifact
                    if artifact_option == "--report"
                    else tmp_path / "transformation.json"
                ),
            ]
        )
    else:
        arguments.extend(["--report", str(artifact)])

    result = cli.main(
        arguments,
        dependencies=cli.CliDependencies(
            privacy_check=lambda _source, _profile: pytest.fail(
                "release check must not run after a profile collision"
            )
        ),
    )

    assert result == 2
    assert profile.read_bytes() == profile_before


@pytest.mark.parametrize("alias_kind", ("direct", "hardlink", "symlink"))
def test_collision_guard_rejects_profile_manifest_alias(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text("immutable profile", encoding="utf-8")
    manifest = profile
    if alias_kind != "direct":
        manifest = tmp_path / "manifest.json"
        if alias_kind == "hardlink":
            manifest.hardlink_to(profile)
        else:
            manifest.symlink_to(profile)

    with pytest.raises(ValueError, match="profile.*manifest"):
        cli._reject_path_collisions(
            ("profile", profile),
            ("manifest", manifest),
        )


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
        (
            "release-check",
            (
                "input.docx",
                "--profile",
                "profile.yaml",
                "--report",
                "privacy.json",
            ),
            "thesis_format.privacy.release_check",
        ),
    ),
)
def test_missing_optional_tools_report_clear_exit_2_errors(
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


def test_default_optional_tool_wrappers_lazy_import_and_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")
    calls: list[tuple[str, tuple[Path, ...]]] = []

    render = ModuleType("thesis_format.render")

    def export_document(document: Path, output: Path, manifest: Path) -> list[Path]:
        calls.append(("export", (document, output, manifest)))
        output.write_bytes(PDF_FIXTURE.read_bytes())
        manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [output, manifest]

    def preview_pdf(
        document: Path,
        output_directory: Path,
        *,
        manifest_path: Path,
    ) -> list[Path]:
        calls.append(("preview", (document, output_directory, manifest_path)))
        output_directory.mkdir()
        image = output_directory / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    render.export_document = export_document  # type: ignore[attr-defined]
    render.preview_pdf = preview_pdf  # type: ignore[attr-defined]
    privacy = ModuleType("thesis_format.privacy")

    def release_check(document: Path, profile_path: Path) -> dict[str, object]:
        calls.append(("privacy", (document, profile_path)))
        return json.loads(
            (
                ROOT / "tests" / "fixtures" / "contracts" / "privacy-report.json"
            ).read_text(encoding="utf-8")
        )

    privacy.release_check = release_check  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "thesis_format.render", render)
    monkeypatch.setitem(sys.modules, "thesis_format.privacy", privacy)

    pdf = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    preview_dir = tmp_path / "preview"
    privacy_report = tmp_path / "privacy.json"
    assert (
        cli.main(
            [
                "export",
                str(source),
                "--output",
                str(pdf),
                "--manifest",
                str(manifest),
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                "preview",
                str(PDF_FIXTURE),
                "--manifest",
                str(RENDER_MANIFEST_FIXTURE),
                "--output-dir",
                str(preview_dir),
            ]
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
            ]
        )
        == 1
    )

    assert [name for name, _ in calls] == ["export", "preview", "privacy"]


def test_export_preview_and_release_check_use_injected_functions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")
    calls: list[tuple[str, tuple[Path, ...]]] = []

    def export(document: Path, output: Path, manifest: Path) -> list[Path]:
        calls.append(("export", (document, output, manifest)))
        output.write_bytes(PDF_FIXTURE.read_bytes())
        manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [output, manifest]

    def preview(
        document: Path, output_directory: Path, manifest: Path
    ) -> list[Path]:
        calls.append(("preview", (document, output_directory, manifest)))
        output_directory.mkdir()
        image = output_directory / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    def privacy(document: Path, profile_path: Path) -> dict[str, object]:
        calls.append(("privacy", (document, profile_path)))
        return json.loads(
            (
                ROOT / "tests" / "fixtures" / "contracts" / "privacy-report.json"
            ).read_text(encoding="utf-8")
        )

    dependencies = cli.CliDependencies(
        export_document=export,
        preview_document=preview,
        privacy_check=privacy,
    )
    pdf = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    preview_dir = tmp_path / "preview"
    privacy_report = tmp_path / "privacy.json"

    assert (
        cli.main(
            [
                "export",
                str(source),
                "--output",
                str(pdf),
                "--manifest",
                str(manifest),
            ],
            dependencies=dependencies,
        )
        == 0
    )
    assert (
        cli.main(
            [
                "preview",
                str(PDF_FIXTURE),
                "--manifest",
                str(RENDER_MANIFEST_FIXTURE),
                "--output-dir",
                str(preview_dir),
            ],
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
    assert manifest.is_file()
    assert (preview_dir / "page-1.png").is_file()
    assert json.loads(privacy_report.read_text(encoding="utf-8"))["summary"][
        "errors"
    ] == 1
    stdout = capsys.readouterr().out
    for requested in (pdf, preview_dir, privacy_report):
        assert str(requested) in stdout


def test_export_rejects_noncanonical_manifest_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(_manifest_bytes(mode="local"))
        return [pdf, report]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 2
    assert "noncanonical" in capsys.readouterr().err
    assert not output.exists()
    assert not manifest.exists()


def test_export_allows_explicit_noncanonical_development_manifest_with_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(_manifest_bytes(mode="local"))
        return [pdf, report]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
            "--allow-noncanonical",
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "WARNING" in captured.err
    assert "noncanonical" in captured.err
    assert "development" in captured.err
    assert output.is_file()
    assert manifest.is_file()


def test_export_accepts_canonical_manifest_without_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(_manifest_bytes(mode="canonical"))
        return [pdf, report]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 0
    assert capsys.readouterr().err == ""


def test_export_stages_provider_outputs_before_validation_and_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "published" / "output.pdf"
    manifest = tmp_path / "reports" / "render-manifest.json"
    source.write_bytes(b"docx")
    staged_paths: list[Path] = []

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        assert pdf != output
        assert report != manifest
        assert pdf.parent.parent == output.parent
        assert report.parent.parent == manifest.parent
        assert not output.exists()
        assert not manifest.exists()
        assert pdf.parent.stat().st_mode & 0o077 == 0
        assert report.parent.stat().st_mode & 0o077 == 0
        staged_paths.extend((pdf, report))
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    real_validate = cli._validate_render_manifest_file

    def validate_before_publish(path: Path) -> Mapping[str, object]:
        assert path == staged_paths[1]
        assert not output.exists()
        assert not manifest.exists()
        return real_validate(path)

    monkeypatch.setattr(cli, "_validate_render_manifest_file", validate_before_publish)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 0
    assert output.read_bytes() == PDF_FIXTURE.read_bytes()
    assert manifest.read_bytes() == RENDER_MANIFEST_FIXTURE.read_bytes()
    assert all(not path.exists() for path in staged_paths)
    assert not list(output.parent.glob(".thesis-export-*"))
    assert not list(manifest.parent.glob(".thesis-export-*"))


def test_export_publishes_validated_descriptors_after_staged_paths_are_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    replacement_pdf = b"replacement PDF pathname"
    replacement_manifest = b'{"replacement": true}'

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    real_open_staged = cli._open_staged_artifact
    replacements = {
        output: replacement_pdf,
        manifest: replacement_manifest,
    }

    def open_with_staged_replacement(
        path: Path, destination: Path
    ) -> cli._StagedArtifact:
        artifact = real_open_staged(path, destination)
        path.unlink()
        path.write_bytes(replacements[destination])
        return artifact

    monkeypatch.setattr(cli, "_open_staged_artifact", open_with_staged_replacement)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 0
    assert output.read_bytes() == PDF_FIXTURE.read_bytes()
    assert manifest.read_bytes() == RENDER_MANIFEST_FIXTURE.read_bytes()


def test_export_reserves_both_destinations_before_copying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    competitor = b"competitor manifest"
    copy_calls = 0

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    real_open = os.open
    real_copyfileobj = shutil.copyfileobj

    def open_with_manifest_collision(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        selected = Path(path)
        if selected == output and flags & os.O_EXCL and not manifest.exists():
            manifest.write_bytes(competitor)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def counted_copyfileobj(*args: object, **kwargs: object) -> None:
        nonlocal copy_calls
        copy_calls += 1
        real_copyfileobj(*args, **kwargs)

    monkeypatch.setattr(
        os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError(errno.EXDEV, "cross-device link")
        ),
    )
    monkeypatch.setattr(os, "open", open_with_manifest_collision)
    monkeypatch.setattr(shutil, "copyfileobj", counted_copyfileobj)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 2
    assert copy_calls == 0
    assert not output.exists()
    assert manifest.read_bytes() == competitor


def test_export_detects_final_path_replacement_without_deleting_competitor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    competitor = b"competitor replacement"

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    real_copyfileobj = shutil.copyfileobj
    replaced = False

    def copy_with_final_replacement(*args: object, **kwargs: object) -> None:
        nonlocal replaced
        real_copyfileobj(*args, **kwargs)
        if not replaced:
            output.unlink()
            output.write_bytes(competitor)
            replaced = True

    monkeypatch.setattr(shutil, "copyfileobj", copy_with_final_replacement)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 2
    assert output.read_bytes() == competitor
    assert not manifest.exists()


@pytest.mark.parametrize("competing_destination", ("pdf", "manifest"))
def test_export_final_window_race_fails_without_touching_competitor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    competing_destination: str,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    competitor = b"competitor-owned artifact"

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    raced_destination = output if competing_destination == "pdf" else manifest
    real_reserve = cli._reserve_destination

    def reserve_with_race(
        destination: Path, expected_sha256: str
    ) -> cli._PublishedArtifact:
        if destination == raced_destination:
            raced_destination.write_bytes(competitor)
        return real_reserve(destination, expected_sha256)

    monkeypatch.setattr(cli, "_reserve_destination", reserve_with_race)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 2
    assert raced_destination.read_bytes() == competitor
    other = manifest if competing_destination == "pdf" else output
    assert not other.exists()


def test_export_rollback_removes_only_the_exact_published_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    competitor = b"competitor replacement"

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    real_reserve = cli._reserve_destination

    def reserve_with_replacement(
        destination: Path, expected_sha256: str
    ) -> cli._PublishedArtifact:
        if destination == manifest:
            output.unlink()
            output.write_bytes(competitor)
            manifest.write_bytes(b"other competitor")
        return real_reserve(destination, expected_sha256)

    monkeypatch.setattr(cli, "_reserve_destination", reserve_with_replacement)

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 2
    assert output.read_bytes() == competitor
    assert manifest.read_bytes() == b"other competitor"


def test_export_copies_to_restrictive_exclusive_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def export(_source: Path, pdf: Path, report: Path) -> list[Path]:
        pdf.write_bytes(PDF_FIXTURE.read_bytes())
        report.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [pdf, report]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=export),
    )

    assert result == 0
    assert output.read_bytes() == PDF_FIXTURE.read_bytes()
    assert manifest.read_bytes() == RENDER_MANIFEST_FIXTURE.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    assert manifest.stat().st_mode & 0o777 == 0o600


def test_preview_warns_for_noncanonical_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pdf = tmp_path / "input.pdf"
    manifest = tmp_path / "input.render-manifest.json"
    output_directory = tmp_path / "preview"
    pdf.write_bytes(PDF_FIXTURE.read_bytes())
    manifest.write_bytes(_manifest_bytes(mode="local"))

    def preview(
        _source: Path, directory: Path, _manifest: Path
    ) -> list[Path]:
        directory.mkdir()
        image = directory / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    result = cli.main(
        ["preview", str(pdf), "--output-dir", str(output_directory)],
        dependencies=cli.CliDependencies(preview_document=preview),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "WARNING" in captured.err
    assert "noncanonical" in captured.err
    assert "compliance" in captured.err
    assert "publication" in captured.err


def test_preview_derives_sibling_render_manifest(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "thesis.pdf"
    pdf.write_bytes(PDF_FIXTURE.read_bytes())
    manifest = tmp_path / "thesis.render-manifest.json"
    manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
    output_directory = tmp_path / "preview"
    received: list[tuple[Path, Path, Path]] = []

    def preview(
        source: Path, output: Path, manifest_path: Path
    ) -> list[Path]:
        received.append((source, output, manifest_path))
        output.mkdir()
        image = output / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    result = cli.main(
        ["preview", str(pdf), "--output-dir", str(output_directory)],
        dependencies=cli.CliDependencies(preview_document=preview),
    )

    assert result == 0
    assert received == [(pdf, output_directory, manifest)]


@pytest.mark.parametrize("provider_result", ({}, None))
def test_release_check_rejects_missing_or_malformed_provider_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    provider_result: object,
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    report = tmp_path / "privacy.json"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")

    result = cli.main(
        [
            "release-check",
            str(source),
            "--profile",
            str(profile),
            "--report",
            str(report),
        ],
        dependencies=cli.CliDependencies(
            privacy_check=lambda _source, _profile: provider_result  # type: ignore[arg-type]
        ),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert not report.exists()
    assert str(report) not in captured.out


def test_release_check_rejects_semantically_invalid_provider_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    report = tmp_path / "privacy.json"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")
    invalid_report = json.loads(
        (ROOT / "tests" / "fixtures" / "contracts" / "privacy-report.json").read_text(
            encoding="utf-8"
        )
    )
    invalid_report["summary"]["errors"] = 0

    result = cli.main(
        [
            "release-check",
            str(source),
            "--profile",
            str(profile),
            "--report",
            str(report),
        ],
        dependencies=cli.CliDependencies(
            privacy_check=lambda _source, _profile: invalid_report
        ),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert not report.exists()
    assert str(report) not in captured.out


@pytest.mark.parametrize(
    "provider",
    (
        lambda _source, _output, _manifest: None,
        lambda _source, _output, _manifest: {},
        lambda _source, output, _manifest: output,
        lambda _source, output, _manifest: output.write_bytes(b"") or output,
    ),
)
def test_export_rejects_noop_or_empty_artifact_provider(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    provider: object,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out
    assert not output.exists()
    assert not manifest.exists()
    assert not list(tmp_path.glob(".thesis-export-*"))


def test_export_rejects_existing_pdf_before_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    output.write_bytes(b"stale pdf")

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(
            export_document=lambda _source, _output, _manifest: pytest.fail(
                "export provider must not run for an existing PDF destination"
            )
        ),
    )

    assert result == 2
    assert output.read_bytes() == b"stale pdf"


def test_export_rejects_existing_manifest_before_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    manifest.write_bytes(
        (
            ROOT / "tests" / "fixtures" / "contracts" / "render-manifest.json"
        ).read_bytes()
    )

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(
            export_document=lambda _source, _output, _manifest: pytest.fail(
                "export provider must not run for an existing manifest destination"
            )
        ),
    )

    assert result == 2


def test_export_provider_failure_removes_only_private_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    staged_paths: list[Path] = []

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        staged_paths.extend((requested_output, requested_manifest))
        requested_output.write_bytes(b"partial provider output")
        raise RuntimeError("provider failed")

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    assert result == 2
    assert not output.exists()
    assert not manifest.exists()
    assert all(not path.exists() for path in staged_paths)


def test_export_rejects_invalid_returned_render_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(b"pdf")
        requested_manifest.write_text("{}", encoding="utf-8")
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out
    assert not output.exists()
    assert not manifest.exists()


@pytest.mark.parametrize("competing_destination", ("pdf", "manifest"))
def test_export_validation_race_preserves_competing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    competing_destination: str,
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")
    competitor = b"competitor replacement"

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(PDF_FIXTURE.read_bytes())
        requested_manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [requested_output, requested_manifest]

    real_validate = cli._validate_render_manifest_artifact

    def validate_with_race(
        artifact: cli._StagedArtifact,
    ) -> Mapping[str, object]:
        destination = output if competing_destination == "pdf" else manifest
        destination.write_bytes(competitor)
        return real_validate(artifact)

    monkeypatch.setattr(
        cli, "_validate_render_manifest_artifact", validate_with_race
    )

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    destination = output if competing_destination == "pdf" else manifest
    other = manifest if competing_destination == "pdf" else output
    assert result == 2
    assert destination.read_bytes() == competitor
    assert not other.exists()


def test_export_rejects_arbitrary_text_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.txt"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(b"pdf")
        requested_manifest.write_text("not a render manifest", encoding="utf-8")
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out
    assert not output.exists()
    assert not manifest.exists()


def test_export_accepts_valid_json_text_manifest(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.txt"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(PDF_FIXTURE.read_bytes())
        requested_manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    assert result == 0


def test_export_rejects_manifest_hash_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(PDF_FIXTURE.read_bytes())
        stale_manifest = json.loads(
            RENDER_MANIFEST_FIXTURE.read_text(encoding="utf-8")
        )
        stale_manifest["raw_pdf_sha256"] = "0" * 64
        stale_manifest["render_id"] = stable_id(
            {
                key: value
                for key, value in stale_manifest.items()
                if key != "render_id"
            }
        )
        requested_manifest.write_text(
            json.dumps(stale_manifest), encoding="utf-8"
        )
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out
    assert not output.exists()
    assert not manifest.exists()


def test_export_rejects_truncated_pdf(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        pdf_bytes = PDF_FIXTURE.read_bytes()
        requested_output.write_bytes(pdf_bytes[: len(pdf_bytes) // 2])
        requested_manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out


def test_export_rejects_stale_manifest_for_new_pdf(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(PDF_FIXTURE.read_bytes() + b"\n")
        requested_manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output) not in captured.out


def test_export_accepts_new_pdf_and_manifest_destinations(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(PDF_FIXTURE.read_bytes())
        requested_manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
        return [requested_output, requested_manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    assert result == 0


def test_export_rejects_missing_returned_render_manifest(tmp_path: Path) -> None:
    source = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    manifest = tmp_path / "missing-render-manifest.json"
    source.write_bytes(b"docx")

    def provider(
        _source: Path, requested_output: Path, _requested_manifest: Path
    ) -> list[Path]:
        requested_output.write_bytes(b"pdf")
        return [requested_output, manifest]

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        dependencies=cli.CliDependencies(export_document=provider),
    )

    assert result == 2


@pytest.mark.parametrize(
    "provider",
    (
        lambda _source, _directory, _manifest: None,
        lambda _source, _directory, _manifest: {},
        lambda _source, directory, _manifest: directory.mkdir() or [],
        lambda _source, directory, _manifest: [directory / "missing.png"],
        lambda _source, directory, _manifest: (
            directory.mkdir(),
            (directory / "page-1.png").write_bytes(b""),
            [directory / "page-1.png"],
        )[-1],
    ),
)
def test_preview_rejects_noop_missing_or_empty_artifact_provider(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    provider: object,
) -> None:
    source = tmp_path / "input.pdf"
    manifest = tmp_path / "input.render-manifest.json"
    output_directory = tmp_path / "preview"
    source.write_bytes(PDF_FIXTURE.read_bytes())
    manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())

    result = cli.main(
        ["preview", str(source), "--output-dir", str(output_directory)],
        dependencies=cli.CliDependencies(preview_document=provider),  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert str(output_directory) not in captured.out


def test_preview_rejects_existing_nonempty_directory_before_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.pdf"
    manifest = tmp_path / "input.render-manifest.json"
    output_directory = tmp_path / "preview"
    stale_image = output_directory / "page-1.png"
    source.write_bytes(PDF_FIXTURE.read_bytes())
    manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
    output_directory.mkdir()
    stale_image.write_bytes(b"stale png")

    result = cli.main(
        ["preview", str(source), "--output-dir", str(output_directory)],
        dependencies=cli.CliDependencies(
            preview_document=lambda _source, _directory, _manifest: pytest.fail(
                "preview provider must not run for a nonempty output directory"
            )
        ),
    )

    assert result == 2
    assert stale_image.read_bytes() == b"stale png"


def test_preview_accepts_new_images_created_in_output_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.pdf"
    manifest = tmp_path / "input.render-manifest.json"
    output_directory = tmp_path / "preview"
    source.write_bytes(PDF_FIXTURE.read_bytes())
    manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())

    def provider(_source: Path, directory: Path, _manifest: Path) -> None:
        directory.mkdir()
        (directory / "page-1.png").write_bytes(b"png")

    result = cli.main(
        ["preview", str(source), "--output-dir", str(output_directory)],
        dependencies=cli.CliDependencies(preview_document=provider),
    )

    assert result == 0


def test_release_check_rejects_existing_report_before_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.docx"
    profile = tmp_path / "profile.yaml"
    report = tmp_path / "privacy.json"
    source.write_bytes(b"docx")
    profile.write_text("unused", encoding="utf-8")
    report.write_bytes(b"stale report")

    result = cli.main(
        [
            "release-check",
            str(source),
            "--profile",
            str(profile),
            "--report",
            str(report),
        ],
        dependencies=cli.CliDependencies(
            privacy_check=lambda _source, _profile: pytest.fail(
                "release provider must not run for an existing report destination"
            )
        ),
    )

    assert result == 2
    assert report.read_bytes() == b"stale report"


def test_preview_passes_explicit_manifest_to_provider(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.pdf"
    output_directory = tmp_path / "preview"
    manifest = tmp_path / "render-manifest.json"
    source.write_bytes(PDF_FIXTURE.read_bytes())
    manifest.write_bytes(RENDER_MANIFEST_FIXTURE.read_bytes())
    received: list[Path] = []

    def provider(
        _source: Path, directory: Path, manifest_path: Path
    ) -> list[Path]:
        received.append(manifest_path)
        directory.mkdir()
        image = directory / "page-1.png"
        image.write_bytes(b"png")
        return [image]

    result = cli.main(
        [
            "preview",
            str(source),
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_directory),
        ],
        dependencies=cli.CliDependencies(preview_document=provider),
    )

    assert result == 0
    assert received == [manifest]
