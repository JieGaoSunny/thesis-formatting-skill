"""Deterministic LibreOffice PDF export, inspection, and previews."""

from __future__ import annotations

import hashlib
import json
import locale as locale_module
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pikepdf
import pymupdf
from PIL import Image

from thesis_format.contracts import (
    canonical_json,
    canonical_sha256,
    stable_id,
    validate_render_manifest,
)


DEFAULT_DPI = 144
DEFAULT_TIMEOUT_SECONDS = 120
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_NUMERIC_SELECTOR = re.compile(r"^-?\d+$")


class RenderError(RuntimeError):
    """A document could not be rendered or inspected."""


class RenderTimeoutError(RenderError):
    """LibreOffice exceeded the configured rendering timeout."""


class CanonicalEnvironmentError(RenderError):
    """The environment cannot make a canonical-container claim."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_environment(
    environment: Mapping[str, Any] | str | Path | None,
) -> dict[str, Any]:
    if environment is None:
        environment = _project_root() / "render-environment.json"
    if isinstance(environment, (str, Path)):
        path = Path(environment)
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CanonicalEnvironmentError(
                f"invalid render environment: {path}"
            ) from error
    else:
        loaded = dict(environment)
    renderer = loaded.get("renderer")
    if not isinstance(renderer, Mapping):
        raise CanonicalEnvironmentError("render environment is missing renderer")
    digest = renderer.get("image_digest")
    if not isinstance(digest, str) or not _IMAGE_DIGEST.fullmatch(digest):
        raise CanonicalEnvironmentError(
            "canonical rendering requires a pinned container image digest"
        )
    if not isinstance(renderer.get("name"), str) or not renderer["name"]:
        raise CanonicalEnvironmentError("render environment is missing renderer name")
    if not isinstance(renderer.get("version"), str) or not renderer["version"]:
        raise CanonicalEnvironmentError(
            "render environment is missing renderer version"
        )
    selected_locale = loaded.get("locale")
    if not isinstance(selected_locale, str) or len(selected_locale) < 2:
        raise CanonicalEnvironmentError("render environment is missing locale")
    return loaded


def _destination_array(value: Any) -> Any:
    if isinstance(value, pikepdf.Dictionary):
        if "/D" in value:
            return value["/D"]
        if "/Dest" in value:
            return value["/Dest"]
    return value


def _decode_destination_name(name: str) -> str:
    # LibreOffice writes OOXML bookmark underscores as the hexadecimal token 5F.
    return name.replace("5F", "_")


def _raw_name_tree_entries(node: Any) -> list[tuple[str, Any]]:
    entries: list[tuple[str, Any]] = []
    if not isinstance(node, pikepdf.Dictionary):
        return entries
    names = node.get("/Names")
    if isinstance(names, pikepdf.Array):
        if len(names) % 2:
            raise RenderError("invalid PDF named destinations: odd name tree")
        for index in range(0, len(names), 2):
            entries.append(
                (_decode_destination_name(str(names[index])), names[index + 1])
            )
    kids = node.get("/Kids")
    if isinstance(kids, pikepdf.Array):
        for kid in kids:
            entries.extend(_raw_name_tree_entries(kid))
    return entries


def _named_destinations(
    pdf: pikepdf.Pdf, page_dimensions: Sequence[tuple[float, float]]
) -> list[dict[str, object]]:
    entries: list[tuple[str, Any]] = []
    names = pdf.Root.get("/Names")
    if isinstance(names, pikepdf.Dictionary):
        entries.extend(_raw_name_tree_entries(names.get("/Dests")))
    legacy = pdf.Root.get("/Dests")
    if isinstance(legacy, pikepdf.Dictionary):
        entries.extend(
            (
                _decode_destination_name(str(key).removeprefix("/")),
                value,
            )
            for key, value in legacy.items()
        )

    page_numbers = {page.obj.objgen: index + 1 for index, page in enumerate(pdf.pages)}
    seen: set[str] = set()
    destinations: list[dict[str, object]] = []
    for name, raw_value in entries:
        if name in seen:
            raise RenderError(f"duplicate PDF named destination: {name}")
        seen.add(name)
        value = _destination_array(raw_value)
        if not isinstance(value, pikepdf.Array) or not value:
            raise RenderError(f"invalid PDF named destination: {name}")
        page_number: int | None = None
        page_reference = value[0]
        if isinstance(page_reference, int):
            candidate = page_reference + 1
            if 1 <= candidate <= len(page_dimensions):
                page_number = candidate
        else:
            page_number = page_numbers.get(page_reference.objgen)
        if page_number is None:
            raise RenderError(f"named destination {name!r} references a missing page")
        width, height = page_dimensions[page_number - 1]
        x_pt = 0.0
        y_pt = 0.0
        if len(value) >= 4 and str(value[1]) == "/XYZ":
            if value[2] is not None:
                x_pt = float(value[2])
            if value[3] is not None:
                y_pt = float(value[3])
        destinations.append(
            {
                "name": name,
                "page": page_number,
                "x_pt": round(min(max(x_pt, 0.0), width), 3),
                "y_pt": round(min(max(y_pt, 0.0), height), 3),
            }
        )
    return sorted(destinations, key=lambda item: (item["name"], item["page"]))


def _font_style(base_name: str) -> tuple[str, str]:
    clean = re.sub(r"^[A-Z]{6}\+", "", base_name)
    if "-" not in clean:
        return clean, "Regular"
    family, style = clean.rsplit("-", 1)
    return family or clean, style or "Regular"


def _font_manifest(document: pymupdf.Document) -> list[dict[str, object]]:
    fonts: dict[tuple[int, str], dict[str, object]] = {}
    for page in document:
        for font in page.get_fonts(full=True):
            xref = int(font[0])
            base_name = str(font[3] or font[4] or "Unknown")
            key = (xref, base_name)
            if key in fonts:
                continue
            try:
                extracted = document.extract_font(xref) if xref > 0 else None
            except RuntimeError:
                extracted = None
            stream = (
                extracted[3]
                if extracted is not None
                and len(extracted) >= 4
                and isinstance(extracted[3], bytes)
                and extracted[3]
                else None
            )
            family, style = _font_style(base_name)
            embedded = bool(stream)
            identity = stream or canonical_json(
                {"xref": xref, "base_name": base_name, "font": list(font[1:])}
            ).encode("utf-8")
            fonts[key] = {
                "postscript_name": base_name,
                "family": family,
                "style": style,
                "embedded": embedded,
                "subset": bool(re.match(r"^[A-Z]{6}\+", base_name)),
                "file_sha256": _sha256_bytes(identity),
            }
    return sorted(
        fonts.values(),
        key=lambda item: (
            str(item["postscript_name"]),
            str(item["style"]),
            str(item["file_sha256"]),
        ),
    )


def _perceptual_hash(page: pymupdf.Page) -> str:
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY, alpha=False
    )
    image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    resized = image.resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(resized.getdata())
    bits = [
        pixels[row * 9 + column] > pixels[row * 9 + column + 1]
        for row in range(8)
        for column in range(8)
    ]
    value = sum(int(bit) << (63 - index) for index, bit in enumerate(bits))
    return f"{value:016x}"


def inspect_pdf(
    pdf_path: str | Path,
    environment: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, object]:
    """Inspect a PDF and return a validated deterministic render manifest."""

    path = Path(pdf_path)
    selected_environment = _load_environment(environment)
    try:
        raw_pdf_sha256 = _sha256_file(path)
        document = pymupdf.open(path)
        if not document.is_pdf or document.page_count < 1:
            document.close()
            raise RenderError(f"invalid PDF: {path}")
        with pikepdf.open(path) as pdf:
            dimensions = [
                (round(float(page.rect.width), 3), round(float(page.rect.height), 3))
                for page in document
            ]
            destinations = _named_destinations(pdf, dimensions)
    except (OSError, ValueError, pikepdf.PdfError, pymupdf.FileDataError) as error:
        raise RenderError(f"invalid PDF: {path}") from error

    try:
        font_manifest = _font_manifest(document)
        extracted_pages = [
            re.sub(r"\s+", " ", page.get_text("text")).strip() for page in document
        ]
        pages = [
            {
                "page": index + 1,
                "width_pt": dimensions[index][0],
                "height_pt": dimensions[index][1],
                "perceptual_hash": _perceptual_hash(page),
            }
            for index, page in enumerate(document)
        ]
    finally:
        document.close()

    page_dimensions = {
        "width_pt": dimensions[0][0],
        "height_pt": dimensions[0][1],
    }
    structural = {
        "page_dimensions": page_dimensions,
        "named_destinations": destinations,
        "font_manifest": font_manifest,
        "pages": pages,
        "extracted_pages": extracted_pages,
    }
    renderer = selected_environment["renderer"]
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "raw_pdf_sha256": raw_pdf_sha256,
        "structural_hash": canonical_sha256(structural),
        "renderer": {
            "name": renderer["name"],
            "version": renderer["version"],
            "image_digest": renderer["image_digest"],
        },
        "font_manifest_hash": canonical_sha256(font_manifest),
        "locale": selected_environment["locale"],
        "page_dimensions": page_dimensions,
        "named_destinations": destinations,
        "extracted_text_hash": _sha256_bytes(
            "\n\f\n".join(extracted_pages).encode("utf-8")
        ),
        "font_manifest": font_manifest,
        "pages": pages,
    }
    manifest["render_id"] = stable_id(manifest)
    validate_render_manifest(manifest)
    return manifest


def _run_soffice(
    command: list[str], *, timeout_seconds: float, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=dict(environment),
        )
    except subprocess.TimeoutExpired as error:
        raise RenderTimeoutError(
            f"LibreOffice rendering timed out after {timeout_seconds:g} seconds"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "unknown LibreOffice error").strip()
        raise RenderError(f"LibreOffice rendering failed: {detail}") from error


def export_document(
    input_docx: str | Path,
    output_pdf: str | Path,
    manifest_path: str | Path,
    environment: Mapping[str, Any] | str | Path | None = None,
) -> list[Path]:
    """Refresh a DOCX through LibreOffice, export PDF, and write its manifest."""

    source = Path(input_docx)
    output = Path(output_pdf)
    manifest_output = Path(manifest_path)
    selected_environment = _load_environment(environment)
    if not source.is_file():
        raise RenderError(f"input DOCX does not exist: {source}")
    soffice = Path(
        str(
            selected_environment.get("soffice_path")
            or shutil.which("soffice")
            or "soffice"
        )
    )
    timeout_seconds = float(
        selected_environment.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    work = output.parent / f".render-work-{uuid.uuid4().hex}"
    source_dir = work / "source"
    refreshed_dir = work / "refreshed"
    pdf_dir = work / "pdf"
    profile_dir = work / "profile"
    for directory in (source_dir, refreshed_dir, pdf_dir, profile_dir):
        directory.mkdir(parents=True, exist_ok=False)
    staged_source = source_dir / source.name
    shutil.copy2(source, staged_source)
    process_environment = os.environ.copy()
    process_environment.update(
        {
            "HOME": str(work / "home"),
            "LANG": str(selected_environment["locale"]),
            "LC_ALL": str(selected_environment["locale"]),
            "TZ": str(selected_environment.get("timezone", "UTC")),
        }
    )
    profile_argument = f"-env:UserInstallation={profile_dir.resolve().as_uri()}"
    common = [
        str(soffice),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--nofirststartwizard",
        profile_argument,
    ]
    try:
        _run_soffice(
            [
                *common,
                "--convert-to",
                "docx:Office Open XML Text",
                "--outdir",
                str(refreshed_dir),
                str(staged_source),
            ],
            timeout_seconds=timeout_seconds,
            environment=process_environment,
        )
        refreshed = refreshed_dir / staged_source.name
        if not refreshed.is_file() or refreshed.stat().st_size == 0:
            raise RenderError("LibreOffice produced no updated DOCX")
        _run_soffice(
            [
                *common,
                "--convert-to",
                (
                    "pdf:writer_pdf_Export:"
                    '{"ExportBookmarks":{"type":"boolean","value":"true"},'
                    '"ExportBookmarksToPDFDestination":'
                    '{"type":"boolean","value":"true"}}'
                ),
                "--outdir",
                str(pdf_dir),
                str(refreshed),
            ],
            timeout_seconds=timeout_seconds,
            environment=process_environment,
        )
        generated = pdf_dir / f"{refreshed.stem}.pdf"
        if not generated.is_file() or generated.stat().st_size == 0:
            raise RenderError("LibreOffice produced no PDF")
        if output.exists():
            raise RenderError(f"PDF output already exists: {output}")
        if manifest_output.exists():
            raise RenderError(f"render manifest already exists: {manifest_output}")
        shutil.move(str(generated), output)
        manifest = inspect_pdf(output, selected_environment)
        manifest_output.write_text(canonical_json(manifest), encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return [output, manifest_output]


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid render manifest: {path}") from error
    validate_render_manifest(manifest)
    return manifest


def _selector_pages(
    selectors: Sequence[str | int],
    manifest: Mapping[str, Any],
    page_count: int,
) -> list[tuple[str | None, int]]:
    destinations = manifest["named_destinations"]
    by_name: dict[str, int] = {}
    for destination in destinations:
        name = destination["name"]
        page = destination["page"]
        if name in by_name:
            raise ValueError(f"duplicate named destination: {name}")
        if not 1 <= page <= page_count:
            raise ValueError(f"named destination {name!r} references a missing page")
        by_name[name] = page

    selected: list[tuple[str | None, int]] = []
    seen: set[tuple[str | None, int]] = set()
    for raw_selector in selectors:
        selector = str(raw_selector)
        if _NUMERIC_SELECTOR.fullmatch(selector):
            page = int(selector)
            if page < 1 or page > page_count:
                raise ValueError(f"invalid page selector: {selector}")
            item = (None, page)
        else:
            if selector not in by_name:
                raise ValueError(f"missing destination selector: {selector}")
            item = (selector, by_name[selector])
        if item in seen:
            raise ValueError(f"duplicate preview selector: {selector}")
        seen.add(item)
        selected.append(item)
    return selected


def preview_pdf(
    input_pdf: str | Path,
    output_directory: str | Path,
    selectors: Sequence[str | int] | None = None,
    manifest_path: str | Path | None = None,
    *,
    dpi: int = DEFAULT_DPI,
) -> list[Path]:
    """Render selected PDF pages to fixed-DPI, nonempty PNG images."""

    source = Path(input_pdf)
    output = Path(output_directory)
    if dpi <= 0:
        raise ValueError("preview DPI must be positive")
    if manifest_path is None:
        candidate = source.with_suffix(".render-manifest.json")
        if not candidate.is_file():
            candidate = source.with_suffix(".json")
        manifest_file = candidate
    else:
        manifest_file = Path(manifest_path)
    manifest = _read_manifest(manifest_file)
    actual_hash = _sha256_file(source)
    if manifest["raw_pdf_sha256"] != actual_hash:
        raise ValueError("PDF raw SHA-256 does not match render manifest")
    try:
        document = pymupdf.open(source)
    except (OSError, pymupdf.FileDataError) as error:
        raise RenderError(f"invalid PDF: {source}") from error
    try:
        requested = selectors or [str(number) for number in range(1, document.page_count + 1)]
        selected = _selector_pages(requested, manifest, document.page_count)
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError(f"preview output directory is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        scale = dpi / 72
        rendered: list[Path] = []
        for name, page_number in selected:
            stem = f"page-{page_number:03d}"
            if name is not None:
                safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
                stem = f"{safe_name}-page-{page_number:03d}"
            destination = output / f"{stem}.png"
            pixmap = document[page_number - 1].get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), alpha=False
            )
            pixmap.save(destination)
            if not destination.is_file() or destination.stat().st_size == 0:
                raise RenderError(f"preview renderer produced an empty PNG: {destination}")
            rendered.append(destination)
        return rendered
    finally:
        document.close()


__all__ = [
    "CanonicalEnvironmentError",
    "RenderError",
    "RenderTimeoutError",
    "export_document",
    "inspect_pdf",
    "preview_pdf",
]
