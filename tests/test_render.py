from __future__ import annotations

import hashlib
import json
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


ROOT = Path(__file__).parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "render" / "baseline.json"
SOFFICE = Path("/opt/homebrew/bin/soffice")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_pdf(path: Path, *, pages: int = 3) -> None:
    document = fitz.open()
    for number in range(1, pages + 1):
        page = document.new_page(width=300, height=400)
        page.insert_text((36, 72), f"Demo page {number}", fontsize=14)
    document.save(path)
    document.close()


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
            "version": "test",
            "image_digest": image_digest,
        },
        "locale": "zh_CN.UTF-8",
        "timezone": "UTC",
        "soffice_path": str(SOFFICE),
        "timeout_seconds": 60,
    }


def test_inspect_pdf_produces_valid_manifest_and_matches_baseline(
    tmp_path: Path,
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


def test_inspect_pdf_rejects_corrupt_input(tmp_path: Path) -> None:
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not a pdf")

    with pytest.raises(RenderError, match="invalid PDF"):
        inspect_pdf(pdf, _environment())


def test_inspect_pdf_requires_canonical_image_digest(tmp_path: Path) -> None:
    pdf = tmp_path / "demo.pdf"
    _make_pdf(pdf)

    with pytest.raises(CanonicalEnvironmentError, match="image digest"):
        inspect_pdf(pdf, _environment(image_digest=None))


def test_cli_export_fails_canonical_acceptance_while_digest_is_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"docx")

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
    assert "pinned container image digest" in capsys.readouterr().err
    assert not (tmp_path / "output.pdf").exists()


def test_render_environment_and_dockerfile_do_not_claim_unpublished_image() -> None:
    environment = json.loads(
        (ROOT / "render-environment.json").read_text(encoding="utf-8")
    )
    dockerfile = (ROOT / "Dockerfile.render").read_text(encoding="utf-8")

    assert environment["renderer"]["image_digest"] is None
    assert environment["canonical_container_status"] == "pending-release-ci"
    assert (
        "python:3.12.11-slim-bookworm@sha256:"
        "519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
        in dockerfile
    )
    assert "uv sync --frozen" in dockerfile
    assert "fonts-noto-cjk" in dockerfile
    assert "TZ=UTC" in dockerfile


def test_preview_pdf_supports_numeric_and_semantic_selectors(tmp_path: Path) -> None:
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
    tmp_path: Path, selector: str
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


def test_preview_pdf_rejects_manifest_pdf_mismatch(tmp_path: Path) -> None:
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


def test_preview_pdf_rejects_missing_destination(tmp_path: Path) -> None:
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


@pytest.mark.integration
@pytest.mark.skipif(not SOFFICE.is_file(), reason="local LibreOffice unavailable")
def test_local_soffice_exports_real_docx(tmp_path: Path) -> None:
    source = ROOT / "templates" / "apple-university-template.docx"
    environment = _environment(
        image_digest="sha256:" + hashlib.sha256(SOFFICE.read_bytes()).hexdigest()
    )

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
