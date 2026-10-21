from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image, ImageChops

from thesis_format.contracts import canonical_sha256
from thesis_format.demo.build import build_before
from thesis_format.ooxml import OoxmlPackage
from thesis_format.profile import load_profile
from thesis_format.render import preview_pdf
from thesis_format.snapshot import (
    extract_snapshot,
    write_content_reports,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "rules" / "apple-university.yaml"
PROFILE = load_profile(PROFILE_PATH)
EXAMPLES = ROOT / "examples"
REPORTS = EXAMPLES / "reports"
SCREENSHOTS = EXAMPLES / "screenshots"
BASELINES = ROOT / "tests" / "fixtures" / "demo"
SELECTORS = (
    "demo_cover",
    "demo_toc",
    "demo_body",
    "demo_figure",
    "demo_table",
    "demo_references",
    "demo_appendix",
)


def _run(*arguments: str, environment: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "thesis_format", *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert completed.returncode in {0, 1}, completed.stdout + completed.stderr


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_render_manifest(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": manifest["schema_version"],
        "locale": manifest["locale"],
        "page_dimensions": manifest["page_dimensions"],
        "named_destinations": manifest["named_destinations"],
        "extracted_text_hash": manifest["extracted_text_hash"],
        "pages": manifest["pages"],
    }


def _docx_structural_hashes(path: Path) -> dict[str, object]:
    with ZipFile(path) as package:
        parts = {
            name: hashlib.sha256(package.read(name)).hexdigest()
            for name in sorted(package.namelist())
            if not name.endswith("/") and not name.startswith("word/media/")
        }
    return {
        "package_hash": canonical_sha256(parts),
        "parts": parts,
    }


def _audit_counts(report: dict[str, object]) -> Counter[str]:
    return Counter(
        str(finding["severity"])
        for finding in report["findings"]  # type: ignore[index]
    )


def test_docx_structural_hashes_ignore_platform_font_rasterization(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"
    for path, image in ((first, b"mac-font"), (second, b"linux-font")):
        with ZipFile(path, "w") as package:
            package.writestr("word/document.xml", b"<document/>")
            package.writestr("word/media/image1.png", image)

    assert _docx_structural_hashes(first) == _docx_structural_hashes(second)


def _destination_page(
    manifest: dict[str, object], destination_name: str
) -> int:
    return next(
        int(destination["page"])
        for destination in manifest["named_destinations"]  # type: ignore[index]
        if destination["name"] == destination_name
    )


def _page_fonts(pdf: Path, page_number: int) -> set[str]:
    import fitz

    with fitz.open(pdf) as document:
        page = document[page_number - 1]
        return {
            str(span["font"])
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", ())
            for span in line.get("spans", ())
            if span.get("text", "").strip()
        }


def _page_header_text(pdf: Path, page_number: int) -> str:
    import fitz

    with fitz.open(pdf) as document:
        return "".join(
            str(block[4]).strip()
            for block in document[page_number - 1].get_text("blocks")
            if float(block[1]) < 120 and str(block[4]).strip()
        )


def _nonwhite_fraction(image_path: Path) -> float:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        difference = ImageChops.difference(
            grayscale, Image.new("L", grayscale.size, 255)
        )
        histogram = difference.histogram()
        nonwhite = sum(histogram[1:])
        return nonwhite / (grayscale.width * grayscale.height)


@pytest.mark.integration
def test_committed_before_after_demo_regenerates_end_to_end(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before.docx"
    after = tmp_path / "after.docx"
    reports = tmp_path / "reports"
    reports.mkdir()
    build_before(before, PROFILE)

    _run(
        "format",
        str(before),
        "--profile",
        str(PROFILE_PATH),
        "--output",
        str(after),
        "--report",
        str(reports / "after-transformation.json"),
    )
    for name, document in (("before", before), ("after", after)):
        _run(
            "audit",
            str(document),
            "--profile",
            str(PROFILE_PATH),
            "--report",
            str(reports / f"{name}-audit.json"),
            "--markdown",
            str(reports / f"{name}-audit.md"),
        )

    before_snapshot = extract_snapshot(before, PROFILE)
    after_snapshot = extract_snapshot(after, PROFILE)
    transformation = _load(reports / "after-transformation.json")
    comparison = transformation["content_comparison"]
    write_content_reports(
        reports, before_snapshot, after_snapshot, comparison
    )

    environment = os.environ.copy()
    environment["THESIS_RENDER_MODE"] = "local"
    for name, document in (("before", before), ("after", after)):
        _run(
            "export",
            str(document),
            "--output",
            str(tmp_path / f"{name}.pdf"),
            "--manifest",
            str(reports / f"{name}-render-manifest.json"),
            "--allow-noncanonical",
            environment=environment,
        )
        preview_pdf(
            tmp_path / f"{name}.pdf",
            tmp_path / "screenshots" / name,
            selectors=SELECTORS,
            manifest_path=reports / f"{name}-render-manifest.json",
        )

    before_audit = _load(reports / "before-audit.json")
    after_audit = _load(reports / "after-audit.json")
    before_counts = _audit_counts(before_audit)
    after_counts = _audit_counts(after_audit)
    before_rules = [
        str(finding["rule_id"])
        for finding in before_audit["findings"]  # type: ignore[index]
        if finding["severity"] in {"error", "violation"}  # type: ignore[index]
    ]
    assert sum(before_counts[level] for level in ("error", "violation")) >= 15
    assert len({rule.split(".", 1)[0] for rule in before_rules}) >= 7
    assert after_counts["error"] == 0
    assert after_counts["violation"] == 0
    assert comparison["equivalent"] is True
    assert not comparison["differences"]

    expected_hashes = _load(
        BASELINES / "expected-docx-structural-hashes.json"
    )
    assert _docx_structural_hashes(before) == expected_hashes["before"]
    assert _docx_structural_hashes(after) == expected_hashes["after"]
    OoxmlPackage.open(before)
    OoxmlPackage.open(after)

    manifests = {
        name: _load(reports / f"{name}-render-manifest.json")
        for name in ("before", "after")
    }
    page_counts = {
        name: len(manifest["pages"])
        for name, manifest in manifests.items()
    }
    assert 12 <= page_counts["after"] <= 15
    assert abs(page_counts["before"] - page_counts["after"]) <= 2
    for name, manifest in manifests.items():
        assert {
            destination["name"]
            for destination in manifest["named_destinations"]
        } >= set(SELECTORS)
        expected = _load(
            BASELINES / f"expected-{name}-render-manifest.json"
        )
        assert _normalized_render_manifest(manifest) == expected
        pdf = tmp_path / f"{name}.pdf"
        for selector in (
            "demo_cover",
            "demo_body",
            "demo_references",
            "demo_appendix",
        ):
            fonts = _page_fonts(pdf, _destination_page(manifest, selector))
            assert any(font.startswith("Noto") and "CJK" in font for font in fonts)
            if name == "after":
                assert any(font.startswith("NotoSansCJK") for font in fonts)
                assert any(font.startswith("NotoSerifCJK") for font in fonts)
    after_manifest = manifests["after"]
    body_header = _page_header_text(
        tmp_path / "after.pdf",
        _destination_page(after_manifest, "demo_body"),
    )
    appendix_header = _page_header_text(
        tmp_path / "after.pdf",
        _destination_page(after_manifest, "demo_appendix"),
    )
    assert "模拟记录字段与复算示例" not in body_header
    assert "绪论" not in appendix_header
    assert "讨论与结论" not in appendix_header
    assert "附录" in appendix_header
    assert "模拟记录字段与复算示例" in appendix_header

    images = sorted((tmp_path / "screenshots").glob("*/*.png"))
    assert len(images) == 14
    assert all(image.stat().st_size > 0 for image in images)
    for selector in SELECTORS:
        assert len(
            list(
                (tmp_path / "screenshots" / "before").glob(
                    f"{selector}-*.png"
                )
            )
        ) == 1
        assert len(
            list(
                (tmp_path / "screenshots" / "after").glob(
                    f"{selector}-*.png"
                )
            )
        ) == 1
    for name in ("before", "after"):
        for selector in (
            "demo_cover",
            "demo_body",
            "demo_references",
            "demo_appendix",
        ):
            image = next(
                (tmp_path / "screenshots" / name).glob(
                    f"{selector}-*.png"
                )
            )
            assert _nonwhite_fraction(image) >= 0.005

    assert _docx_structural_hashes(EXAMPLES / "before.docx") == expected_hashes["before"]
    assert _docx_structural_hashes(EXAMPLES / "after.docx") == expected_hashes["after"]
    assert len(list(SCREENSHOTS.glob("*/*.png"))) == 14
