from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import fitz
import pikepdf
import pytest

from thesis_format import cli
from thesis_format.contracts import validate_render_manifest
from thesis_format.render import (
    CanonicalEnvironmentError,
    RenderError,
    RenderTimeoutError,
    export_document,
    inspect_pdf,
    preview_pdf,
)
from thesis_format import render


ROOT = Path(__file__).parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "render" / "baseline.json"
SOFFICE = Path("/opt/homebrew/bin/soffice")
CANONICAL_IMAGE_DIGEST = (
    "sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79"
)
CANONICAL_IMAGE_REFERENCE = (
    "ghcr.io/jiegaosunny/thesis-formatting-skill-render@"
    f"{CANONICAL_IMAGE_DIGEST}"
)
CANONICAL_SOURCE_COMMIT = "9e29b0eb77a4749e330fac4902be10597330ce92"
DEBIAN_SNAPSHOT = "20250203T000000Z"
FONT_QUERIES = ["Liberation Serif", "Noto Serif CJK SC"]
SOFFICE_VERSION = "LibreOffice 24.2.7.2 actual-build"
FONT_OBSERVATIONS = [
    {
        "query": "Liberation Serif",
        "family": "Liberation Serif",
        "style": "Regular",
        "file": "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    },
    {
        "query": "Noto Serif CJK SC",
        "family": "Noto Serif CJK SC",
        "style": "Regular",
        "file": "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_pdf(path: Path, *, pages: int = 3) -> None:
    document = fitz.open()
    for number in range(1, pages + 1):
        page = document.new_page(width=300, height=400)
        page.insert_text((36, 72), f"Demo page {number}", fontsize=14)
    document.save(path)
    document.close()


def test_pdf_privacy_scrub_removes_docinfo_and_xmp(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, pages=1)
    with pikepdf.open(source, allow_overwriting_input=True) as document:
        document.docinfo["/Author"] = "艾苹"
        document.docinfo["/Creator"] = "Writer"
        document.docinfo["/Producer"] = "LibreOffice"
        with document.open_metadata(
            set_pikepdf_as_editor=False,
            update_docinfo=False,
        ) as metadata:
            metadata["dc:creator"] = ["艾苹"]
            metadata["xmp:CreatorTool"] = "Writer"
            metadata["pdf:Producer"] = "LibreOffice"
        document.save(source)

    render._scrub_pdf_metadata(source, output)

    with pikepdf.open(output) as document:
        assert not document.docinfo
        assert "/Metadata" not in document.Root
    with fitz.open(output) as document:
        assert all(
            not value
            for key, value in document.metadata.items()
            if key in {"author", "creator", "producer"}
        )


def _add_destinations(path: Path, destinations: list[tuple[str, int]]) -> None:
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        names = pikepdf.Array()
        for name, page_index in destinations:
            names.extend(
                [
                    pikepdf.String(name),
                    pikepdf.Array(
                        [pdf.pages[page_index].obj, pikepdf.Name("/XYZ"), 0, 400, 0]
                    ),
                ]
            )
        pdf.Root.Names = pikepdf.Dictionary(
            Dests=pikepdf.Dictionary(Names=names)
        )
        pdf.save(path)


def _environment(*, image_digest: str | None = "sha256:" + "a" * 64) -> dict:
    return {
        "schema_version": "1.0",
        "renderer": {
            "name": "LibreOffice",
            "expected_source_snapshot": "debian-bookworm@20250203T000000Z",
            "local_detected_version": "LibreOffice local-test",
            "image_digest": image_digest,
        },
        "locale": "zh_CN.UTF-8",
        "timezone": "UTC",
        "soffice_path": str(SOFFICE),
        "timeout_seconds": 60,
        "canonical_image_digest": CANONICAL_IMAGE_DIGEST,
        "canonical_image_reference": CANONICAL_IMAGE_REFERENCE,
        "canonical_source_commit": CANONICAL_SOURCE_COMMIT,
        "canonical_build_inputs": {
            "debian_snapshot": DEBIAN_SNAPSHOT,
            "font_queries": FONT_QUERIES,
        },
    }


@pytest.fixture
def detected_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: SOFFICE_VERSION,
    )


@pytest.fixture(autouse=True)
def canonical_runtime_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    marker = tmp_path / "canonical-container.json"
    marker.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_commit": CANONICAL_SOURCE_COMMIT,
                "debian_snapshot": DEBIAN_SNAPSHOT,
                "soffice_version_sha256": hashlib.sha256(
                    SOFFICE_VERSION.encode("utf-8")
                ).hexdigest(),
                "font_input_fingerprint": hashlib.sha256(
                    render.canonical_json(FONT_OBSERVATIONS).encode("utf-8")
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", CANONICAL_IMAGE_DIGEST)
    monkeypatch.delenv("THESIS_RENDER_MODE", raising=False)
    monkeypatch.setattr(render, "_canonical_marker_path", lambda: marker)
    monkeypatch.setattr(
        render, "_observe_font_inputs", lambda _environment: FONT_OBSERVATIONS
    )
    return marker


def test_inspect_pdf_produces_valid_manifest_and_matches_baseline(
    tmp_path: Path, detected_version: None
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    _add_destinations(
        pdf,
        [("demo_cover", 0), ("demo_body", 1), ("demo_appendix", 2)],
    )

    manifest = inspect_pdf(pdf, _environment())

    validate_render_manifest(manifest)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert {
        "page_count": len(manifest["pages"]),
        "page_dimensions": manifest["page_dimensions"],
        "destination_pages": {
            item["name"]: item["page"] for item in manifest["named_destinations"]
        },
        "page_numbers": [item["page"] for item in manifest["pages"]],
    } == baseline
    assert manifest["raw_pdf_sha256"] == _sha256(pdf)
    assert len(manifest["structural_hash"]) == 64
    assert len(manifest["extracted_text_hash"]) == 64
    assert all(len(page["perceptual_hash"]) == 16 for page in manifest["pages"])
    assert manifest["renderer"] == {
        "name": "LibreOffice",
        "version": "LibreOffice 24.2.7.2 actual-build",
        "image_digest": CANONICAL_IMAGE_DIGEST,
    }


def test_inspect_pdf_rejects_corrupt_input(tmp_path: Path) -> None:
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not a pdf")

    with pytest.raises(RenderError, match="invalid PDF"):
        inspect_pdf(pdf, _environment())


def test_inspect_pdf_requires_canonical_image_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    monkeypatch.delenv("THESIS_RENDER_IMAGE_DIGEST")

    with pytest.raises(CanonicalEnvironmentError, match="THESIS_RENDER_IMAGE_DIGEST"):
        inspect_pdf(pdf, _environment(image_digest=None))


def test_canonical_image_digest_must_match_pinned_environment_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detected_version: None,
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    monkeypatch.delenv("THESIS_RENDER_IMAGE_DIGEST", raising=False)

    with pytest.raises(CanonicalEnvironmentError, match="THESIS_RENDER_IMAGE_DIGEST"):
        inspect_pdf(pdf, _environment())

    monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", "sha256:" + "b" * 64)
    with pytest.raises(CanonicalEnvironmentError, match="pinned canonical digest"):
        inspect_pdf(pdf, _environment())

    monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", CANONICAL_IMAGE_DIGEST)
    manifest = inspect_pdf(pdf, _environment())

    assert manifest["renderer"]["image_digest"] == CANONICAL_IMAGE_DIGEST
    assert manifest["environment"] == {
        "mode": "canonical",
        "canonical": True,
    }


def test_spoofed_digest_without_container_marker_is_noncanonical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detected_version: None,
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    monkeypatch.setattr(
        render, "_canonical_marker_path", lambda: tmp_path / "missing-marker.json"
    )

    with pytest.raises(CanonicalEnvironmentError, match="container marker"):
        inspect_pdf(pdf, _environment())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_commit", "b" * 40, "source commit"),
        ("debian_snapshot", "20250101T000000Z", "Debian snapshot"),
        ("soffice_version_sha256", "0" * 64, "LibreOffice version"),
        ("font_input_fingerprint", "0" * 64, "font input"),
    ],
)
def test_canonical_container_marker_rejects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detected_version: None,
    field: str,
    value: str,
    message: str,
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    marker_path = render._canonical_marker_path()
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker[field] = value
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(CanonicalEnvironmentError, match=message):
        inspect_pdf(pdf, _environment())


def test_runtime_font_observation_must_match_container_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detected_version: None,
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    monkeypatch.setattr(
        render,
        "_observe_font_inputs",
        lambda _environment: [
            {
                **FONT_OBSERVATIONS[0],
                "file": "/unexpected/LiberationSerif-Regular.ttf",
            },
            FONT_OBSERVATIONS[1],
        ],
    )

    with pytest.raises(CanonicalEnvironmentError, match="font input"):
        inspect_pdf(pdf, _environment())


def test_explicit_local_mode_records_noncanonical_renderer_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detected_version: None,
) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)
    environment = _environment(image_digest=None)
    environment["render_mode"] = "local"
    monkeypatch.delenv("THESIS_RENDER_IMAGE_DIGEST", raising=False)
    monkeypatch.setattr(
        render, "_canonical_marker_path", lambda: tmp_path / "missing-marker.json"
    )

    first = inspect_pdf(pdf, environment)
    second = inspect_pdf(pdf, environment)

    assert first["renderer"]["image_digest"].startswith("sha256:")
    assert first["renderer"]["image_digest"] == second["renderer"]["image_digest"]
    assert first["environment"] == {"mode": "local", "canonical": False}
    with pytest.raises(CanonicalEnvironmentError, match="noncanonical"):
        render.require_canonical_render_manifest(first)


def test_cli_export_fails_canonical_acceptance_while_digest_is_pending(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    monkeypatch.delenv("THESIS_RENDER_IMAGE_DIGEST")

    result = cli.main(
        [
            "export",
            str(source),
            "--output",
            str(tmp_path / "output.pdf"),
            "--manifest",
            str(tmp_path / "manifest.json"),
        ]
    )

    assert result == 2
    assert "THESIS_RENDER_IMAGE_DIGEST" in capsys.readouterr().err
    assert not (tmp_path / "output.pdf").exists()


def test_render_environment_marks_rebuild_pending_and_defines_attestation() -> None:
    environment = json.loads(
        (ROOT / "render-environment.json").read_text(encoding="utf-8")
    )
    dockerfile = (ROOT / "Dockerfile.render").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "image_digest" not in environment["renderer"]
    assert "version" not in environment["renderer"]
    assert environment["renderer"]["expected_source_snapshot"].endswith(
        "20250203T000000Z"
    )
    assert environment["renderer"]["local_detected_version"].startswith(
        "LibreOffice "
    )
    assert environment["canonical_container_status"] == "published-pinned"
    assert environment["canonical_image_digest"] == CANONICAL_IMAGE_DIGEST
    assert environment["canonical_image_reference"] == CANONICAL_IMAGE_REFERENCE
    assert environment["canonical_source_commit"] == CANONICAL_SOURCE_COMMIT
    assert environment["canonical_build_inputs"] == {
        "debian_snapshot": DEBIAN_SNAPSHOT,
        "font_queries": FONT_QUERIES,
    }
    assert CANONICAL_IMAGE_REFERENCE in environment["release_ci_instructions"]
    assert f"THESIS_RENDER_IMAGE_DIGEST={CANONICAL_IMAGE_DIGEST}" in readme
    assert CANONICAL_IMAGE_REFERENCE in readme
    assert f"THESIS_RENDER_IMAGE_DIGEST={CANONICAL_IMAGE_DIGEST}" in readme_zh
    assert CANONICAL_IMAGE_REFERENCE in readme_zh
    assert (
        "python:3.12.11-slim-bookworm@sha256:"
        "519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
        in dockerfile
    )
    assert "uv sync --frozen" in dockerfile
    assert "fonts-noto-cjk" in dockerfile
    assert "TZ=UTC" in dockerfile
    assert "rm -f /etc/apt/sources.list.d/debian.sources" in dockerfile
    assert "soffice --version | tee" in dockerfile
    assert "test -s /usr/local/share/thesis-format/soffice-version.txt" in dockerfile
    assert "ARG SOURCE_COMMIT" in dockerfile
    assert "canonical-container.json" in dockerfile
    assert "source_commit" in dockerfile
    assert "soffice_version_sha256" in dockerfile
    assert "font_input_fingerprint" in dockerfile
    assert "chown root:root" in dockerfile
    assert "chmod 0444" in dockerfile
    assert "COPY render-environment.json" not in dockerfile
    assert "THESIS_RENDER_IMAGE_DIGEST" not in dockerfile
    assert "render-environment.json" in (
        ROOT / ".dockerignore"
    ).read_text(encoding="utf-8").splitlines()
    workflow = (
        ROOT / ".github" / "workflows" / "render-image.yml"
    ).read_text(encoding="utf-8")
    assert "SOURCE_COMMIT=${{ github.sha }}" in workflow


def test_detect_soffice_version_records_command_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def completed(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout="LibreOffice 24.2.7.2 420(Build:2)\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", completed)

    assert (
        render._detect_soffice_version(_environment())
        == "LibreOffice 24.2.7.2 420(Build:2)"
    )


def test_preview_pdf_supports_numeric_and_semantic_selectors(
    tmp_path: Path, detected_version: None
) -> None:
    pdf = tmp_path / "demo.pdf"
    output = tmp_path / "previews"
    manifest_path = tmp_path / "manifest.json"
    _make_pdf(pdf)
    _add_destinations(pdf, [("demo_cover", 0), ("demo_body", 2)])
    manifest_path.write_text(
        json.dumps(inspect_pdf(pdf, _environment())), encoding="utf-8"
    )

    rendered = preview_pdf(
        pdf,
        output,
        selectors=["1", "3", "demo_body"],
        manifest_path=manifest_path,
        dpi=144,
    )

    assert [path.name for path in rendered] == [
        "page-001.png",
        "page-003.png",
        "demo_body-page-003.png",
    ]
    assert all(path.read_bytes().startswith(b"\x89PNG") for path in rendered)
    assert all(path.stat().st_size > 100 for path in rendered)


@pytest.mark.parametrize("selector", ["0", "-1", "x", "4"])
def test_preview_pdf_rejects_invalid_numeric_selectors(
    tmp_path: Path, selector: str, detected_version: None
) -> None:
    pdf = tmp_path / "demo.pdf"
    manifest_path = tmp_path / "manifest.json"
    _make_pdf(pdf)
    manifest_path.write_text(
        json.dumps(inspect_pdf(pdf, _environment())), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="selector"):
        preview_pdf(
            pdf,
            tmp_path / "previews",
            selectors=[selector],
            manifest_path=manifest_path,
        )


def test_preview_pdf_rejects_manifest_pdf_mismatch(
    tmp_path: Path, detected_version: None
) -> None:
    pdf = tmp_path / "demo.pdf"
    other_pdf = tmp_path / "other.pdf"
    manifest_path = tmp_path / "manifest.json"
    _make_pdf(pdf)
    _make_pdf(other_pdf, pages=1)
    manifest_path.write_text(
        json.dumps(inspect_pdf(other_pdf, _environment())), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="raw SHA-256"):
        preview_pdf(
            pdf,
            tmp_path / "previews",
            selectors=["1"],
            manifest_path=manifest_path,
        )


@pytest.mark.parametrize(
    "destinations, message",
    [
        ([("demo_body", 0), ("demo_body", 1)], "unique|duplicate"),
        ([("demo_body", 3)], "missing page"),
    ],
)
def test_preview_pdf_rejects_invalid_destinations(
    tmp_path: Path,
    destinations: list[tuple[str, int]],
    message: str,
    detected_version: None,
) -> None:
    pdf = tmp_path / "demo.pdf"
    manifest_path = tmp_path / "manifest.json"
    _make_pdf(pdf)
    manifest = inspect_pdf(pdf, _environment())
    manifest["named_destinations"] = [
        {"name": name, "page": page + 1, "x_pt": 0, "y_pt": 0}
        for name, page in destinations
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        preview_pdf(
            pdf,
            tmp_path / "previews",
            selectors=["demo_body"],
            manifest_path=manifest_path,
        )


def test_preview_pdf_rejects_missing_destination(
    tmp_path: Path, detected_version: None
) -> None:
    pdf = tmp_path / "demo.pdf"
    manifest_path = tmp_path / "manifest.json"
    _make_pdf(pdf)
    manifest_path.write_text(
        json.dumps(inspect_pdf(pdf, _environment())), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="missing destination"):
        preview_pdf(
            pdf,
            tmp_path / "previews",
            selectors=["demo_body"],
            manifest_path=manifest_path,
        )


def test_export_document_rejects_noop_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    with pytest.raises(RenderError, match="produced no"):
        export_document(
            source,
            tmp_path / "output.pdf",
            tmp_path / "manifest.json",
            _environment(),
        )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RenderTimeoutError, match="timed out"):
        export_document(
            source,
            tmp_path / "timeout.pdf",
            tmp_path / "timeout.json",
            _environment(),
        )


def test_export_document_rejects_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(
            1, args[0], output="stdout", stderr="conversion failed"
        )

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(RenderError, match="conversion failed"):
        export_document(
            source,
            tmp_path / "output.pdf",
            tmp_path / "manifest.json",
            _environment(),
        )


def _fake_soffice_conversion(
    command: list[str], *, timeout_seconds: float, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    del timeout_seconds, environment
    output_directory = Path(command[command.index("--outdir") + 1])
    source = Path(command[-1])
    output_directory.mkdir(parents=True, exist_ok=True)
    if command[command.index("--convert-to") + 1].startswith("docx:"):
        shutil.copy2(source, output_directory / source.name)
    else:
        _make_pdf(output_directory / f"{source.stem}.pdf", pages=1)
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


@pytest.mark.parametrize("failure", ("inspection", "manifest"))
def test_export_document_failure_leaves_no_outputs_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_runtime_attestation: Path,
    failure: str,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )
    monkeypatch.setattr(
        render,
        "_canonical_marker_path",
        lambda: canonical_runtime_attestation,
    )
    monkeypatch.setattr(
        render, "_observe_font_inputs", lambda _environment: FONT_OBSERVATIONS
    )
    real_inspect = render.inspect_pdf

    if failure == "inspection":
        monkeypatch.setattr(
            render,
            "inspect_pdf",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RenderError("inspection failed")
            ),
        )
    else:
        monkeypatch.setattr(
            render,
            "validate_render_manifest",
            lambda _value: (_ for _ in ()).throw(
                ValueError("manifest failed")
            ),
        )

    with pytest.raises((RenderError, ValueError), match="failed"):
        export_document(source, output, manifest_path, _environment())

    assert not output.exists()
    assert not manifest_path.exists()
    assert not list(tmp_path.glob(".render-*"))

    if failure == "inspection":
        monkeypatch.setattr(render, "inspect_pdf", real_inspect)
    else:
        monkeypatch.undo()
        monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", CANONICAL_IMAGE_DIGEST)
        monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
        monkeypatch.setattr(
            render,
            "_detect_soffice_version",
            lambda _environment: "LibreOffice 24.2.7.2 actual-build",
        )
        monkeypatch.setattr(
            render,
            "_canonical_marker_path",
            lambda: canonical_runtime_attestation,
        )
        monkeypatch.setattr(
            render, "_observe_font_inputs", lambda _environment: FONT_OBSERVATIONS
        )

    assert export_document(source, output, manifest_path, _environment()) == [
        output,
        manifest_path,
    ]
    assert output.is_file()
    assert manifest_path.is_file()


def test_export_document_records_pinned_runtime_image_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", CANONICAL_IMAGE_DIGEST)
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )

    export_document(source, output, manifest_path, _environment())

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["renderer"]["image_digest"] == CANONICAL_IMAGE_DIGEST
    assert manifest["environment"] == {
        "mode": "canonical",
        "canonical": True,
    }


def test_export_document_publishes_opened_staged_descriptors_after_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )
    real_open_staged = render._open_staged_artifact

    def open_with_replacement(path: Path) -> render._StagedArtifact:
        artifact = real_open_staged(path)
        path.unlink()
        path.write_bytes(
            b"replacement PDF pathname"
            if path.suffix == ".pdf"
            else b'{"replacement": true}'
        )
        return artifact

    monkeypatch.setattr(render, "_open_staged_artifact", open_with_replacement)

    export_document(source, output, manifest_path, _environment())

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert output.read_bytes().startswith(b"%PDF-")
    assert manifest["raw_pdf_sha256"] == _sha256(output)


def test_export_document_reserves_both_destinations_before_copying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    competitor = b"competitor manifest"
    copy_calls = 0
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )
    real_open = os.open
    real_copyfileobj = shutil.copyfileobj

    def open_with_manifest_collision(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == output and flags & os.O_EXCL and not manifest_path.exists():
            manifest_path.write_bytes(competitor)
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

    with pytest.raises(RenderError, match="already exists"):
        export_document(source, output, manifest_path, _environment())

    assert copy_calls == 0
    assert not output.exists()
    assert manifest_path.read_bytes() == competitor


@pytest.mark.parametrize("competing_destination", ("pdf", "manifest"))
def test_export_document_never_clobbers_racing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    competing_destination: str,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    competitor = b"competitor-owned artifact"
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )
    monkeypatch.setenv("THESIS_RENDER_IMAGE_DIGEST", CANONICAL_IMAGE_DIGEST)
    real_inspect = render.inspect_pdf

    def inspect_with_race(*args, **kwargs):
        manifest = real_inspect(*args, **kwargs)
        destination = output if competing_destination == "pdf" else manifest_path
        destination.write_bytes(competitor)
        return manifest

    monkeypatch.setattr(render, "inspect_pdf", inspect_with_race)

    with pytest.raises(RenderError, match="already exists"):
        export_document(source, output, manifest_path, _environment())

    destination = output if competing_destination == "pdf" else manifest_path
    other = manifest_path if competing_destination == "pdf" else output
    assert destination.read_bytes() == competitor
    assert not other.exists()
    assert not list(tmp_path.glob(".render-*"))


def test_second_publication_failure_does_not_remove_replacement_first_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")
    output = tmp_path / "output.pdf"
    manifest_path = tmp_path / "manifest.json"
    replacement = b"competitor replacement"
    blocker = b"competitor manifest"
    monkeypatch.setattr(render, "_run_soffice", _fake_soffice_conversion)
    monkeypatch.setattr(
        render,
        "_detect_soffice_version",
        lambda _environment: "LibreOffice 24.2.7.2 actual-build",
    )
    real_reserve = render._reserve_destination

    def reserve_with_replacement(destination: Path, expected_sha256: str):
        if destination == manifest_path:
            output.unlink()
            output.write_bytes(replacement)
            manifest_path.write_bytes(blocker)
        return real_reserve(destination, expected_sha256)

    monkeypatch.setattr(render, "_reserve_destination", reserve_with_replacement)

    with pytest.raises(RenderError, match="already exists"):
        export_document(source, output, manifest_path, _environment())

    assert output.read_bytes() == replacement
    assert manifest_path.read_bytes() == blocker
    assert not list(tmp_path.glob(".render-*"))


@pytest.mark.integration
@pytest.mark.skipif(not SOFFICE.is_file(), reason="local LibreOffice unavailable")
def test_local_soffice_exports_real_docx(tmp_path: Path) -> None:
    source = ROOT / "templates" / "apple-university-template.docx"
    environment = _environment(image_digest=None)
    environment["render_mode"] = "local"

    outputs = export_document(
        source,
        tmp_path / "template.pdf",
        tmp_path / "render-manifest.json",
        environment,
    )

    assert outputs == [tmp_path / "template.pdf", tmp_path / "render-manifest.json"]
    manifest = json.loads(
        (tmp_path / "render-manifest.json").read_text(encoding="utf-8")
    )
    validate_render_manifest(manifest)
    assert {
        destination["name"]
        for destination in manifest["named_destinations"]
        if destination["name"].startswith("demo_")
    } >= {
        "demo_cover",
        "demo_toc",
        "demo_body",
        "demo_figure",
        "demo_table",
        "demo_references",
        "demo_appendix",
    }
    assert manifest["font_manifest"]
    assert all(font["embedded"] for font in manifest["font_manifest"])
    assert shutil.which("pdftoppm")
