"""Deterministic LibreOffice PDF export, inspection, and previews."""

from __future__ import annotations

import hashlib
import errno
import json
import os
import re
import shutil
import stat
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
_RENDER_MODES = frozenset({"canonical", "local"})
_IMAGE_DIGEST_ENV = "THESIS_RENDER_IMAGE_DIGEST"
_RENDER_MODE_ENV = "THESIS_RENDER_MODE"


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
    configured_mode = loaded.get("render_mode")
    environment_mode = os.environ.get(_RENDER_MODE_ENV)
    mode = environment_mode or configured_mode or "canonical"
    if mode not in _RENDER_MODES:
        raise CanonicalEnvironmentError(
            f"render mode must be one of {sorted(_RENDER_MODES)!r}"
        )
    digest = os.environ.get(_IMAGE_DIGEST_ENV)
    if mode == "canonical" and (
        not isinstance(digest, str) or not _IMAGE_DIGEST.fullmatch(digest)
    ):
        raise CanonicalEnvironmentError(
            "canonical rendering requires a valid "
            f"{_IMAGE_DIGEST_ENV}=sha256:<64 lowercase hex characters>"
        )
    if not isinstance(renderer.get("name"), str) or not renderer["name"]:
        raise CanonicalEnvironmentError("render environment is missing renderer name")
    expected_snapshot = renderer.get("expected_source_snapshot")
    if not isinstance(expected_snapshot, str) or not expected_snapshot:
        raise CanonicalEnvironmentError(
            "render environment is missing expected source snapshot"
        )
    selected_locale = loaded.get("locale")
    if not isinstance(selected_locale, str) or len(selected_locale) < 2:
        raise CanonicalEnvironmentError("render environment is missing locale")
    loaded["render_mode"] = mode
    loaded["_runtime_image_digest"] = digest
    return loaded


def _renderer_image_digest(
    environment: Mapping[str, Any], detected_version: str
) -> str:
    if environment["render_mode"] == "canonical":
        return str(environment["_runtime_image_digest"])
    renderer = environment["renderer"]
    configured_soffice = str(environment.get("soffice_path") or "soffice")
    soffice = Path(shutil.which(configured_soffice) or configured_soffice)
    executable_sha256 = (
        _sha256_file(soffice) if soffice.is_file() else "unavailable"
    )
    fingerprint = canonical_sha256(
        {
            "renderer": {
                "name": renderer["name"],
                "version": detected_version,
                "executable_sha256": executable_sha256,
                "repository": renderer.get("repository"),
                "expected_source_snapshot": renderer["expected_source_snapshot"],
                "font_inputs": renderer.get("font_inputs", []),
            },
            "locale": environment["locale"],
            "timezone": environment.get("timezone", "UTC"),
        }
    )
    return f"sha256:{fingerprint}"


def require_canonical_render_manifest(manifest: Mapping[str, Any]) -> None:
    """Reject a structurally valid manifest produced in local development mode."""

    validate_render_manifest(manifest)
    environment = manifest.get("environment")
    if (
        not isinstance(environment, Mapping)
        or environment.get("mode") != "canonical"
        or environment.get("canonical") is not True
    ):
        raise CanonicalEnvironmentError(
            "canonical acceptance rejects noncanonical local render manifests"
        )


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

    detected_version = _detect_soffice_version(selected_environment)
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
    render_mode = str(selected_environment["render_mode"])
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "raw_pdf_sha256": raw_pdf_sha256,
        "structural_hash": canonical_sha256(structural),
        "renderer": {
            "name": renderer["name"],
            "version": detected_version,
            "image_digest": _renderer_image_digest(
                selected_environment, detected_version
            ),
        },
        "environment": {
            "mode": render_mode,
            "canonical": render_mode == "canonical",
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


def _detect_soffice_version(environment: Mapping[str, Any]) -> str:
    soffice = str(
        environment.get("soffice_path") or shutil.which("soffice") or "soffice"
    )
    timeout_seconds = float(
        environment.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )
    process_environment = os.environ.copy()
    process_environment.update(
        {
            "LANG": str(environment["locale"]),
            "LC_ALL": str(environment["locale"]),
            "TZ": str(environment.get("timezone", "UTC")),
        }
    )
    try:
        completed = subprocess.run(
            [soffice, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=process_environment,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        raise RenderError("could not detect LibreOffice version") from error
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        raise RenderError("LibreOffice reported an empty version")
    return version


def _file_identity(path: Path) -> tuple[int, int]:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RenderError(f"published artifact cannot be inspected: {path}") from error
    if not stat.S_ISREG(details.st_mode):
        raise RenderError(f"published artifact is not a regular file: {path}")
    return details.st_dev, details.st_ino


def _unlink_exact_artifact(
    path: Path,
    identity: tuple[int, int],
    expected_sha256: str | None = None,
) -> None:
    try:
        if _file_identity(path) != identity:
            return
        if (
            expected_sha256 is not None
            and _sha256_file(path) != expected_sha256
        ):
            return
        path.unlink()
    except (OSError, RenderError):
        return


def _publish_exclusive(
    staged: Path, destination: Path
) -> tuple[tuple[int, int], str]:
    expected_sha256 = _sha256_file(staged)
    staged_identity = _file_identity(staged)
    created_identity: tuple[int, int] | None = None
    try:
        try:
            os.link(staged, destination, follow_symlinks=False)
            linked_identity = _file_identity(destination)
            if linked_identity != staged_identity:
                raise RenderError(
                    f"published artifact inode mismatch: {destination}"
                )
            created_identity = linked_identity
        except FileExistsError as error:
            raise RenderError(f"artifact destination already exists: {destination}") from error
        except OSError as error:
            if error.errno not in {
                errno.EXDEV,
                errno.EPERM,
                errno.EACCES,
                errno.ENOTSUP,
                errno.EOPNOTSUPP,
            }:
                raise RenderError(
                    f"could not publish artifact: {destination}"
                ) from error
            try:
                descriptor = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    staged.stat().st_mode & 0o777,
                )
            except FileExistsError as exclusive_error:
                raise RenderError(
                    f"artifact destination already exists: {destination}"
                ) from exclusive_error
            descriptor_details = os.fstat(descriptor)
            created_identity = (
                descriptor_details.st_dev,
                descriptor_details.st_ino,
            )
            try:
                with staged.open("rb") as source, os.fdopen(descriptor, "wb") as target:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
            except BaseException:
                if created_identity is not None:
                    _unlink_exact_artifact(destination, created_identity)
                raise

        if _file_identity(destination) != created_identity:
            raise RenderError(
                f"published artifact inode mismatch: {destination}"
            )
        if _sha256_file(destination) != expected_sha256:
            raise RenderError(
                f"published artifact hash mismatch: {destination}"
            )
        return created_identity, expected_sha256
    except BaseException:
        if created_identity is not None:
            _unlink_exact_artifact(destination, created_identity, expected_sha256)
        raise


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
    if output.exists():
        raise RenderError(f"PDF output already exists: {output}")
    if manifest_output.exists():
        raise RenderError(f"render manifest already exists: {manifest_output}")
    token = uuid.uuid4().hex
    work = output.parent / f".render-work-{token}"
    temporary_pdf = output.parent / f".render-pdf-{token}.pdf"
    temporary_manifest = (
        manifest_output.parent / f".render-manifest-{token}.json"
    )
    try:
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
        profile_argument = (
            f"-env:UserInstallation={profile_dir.resolve().as_uri()}"
        )
        common = [
            str(soffice),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            profile_argument,
        ]
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
        os.replace(generated, temporary_pdf)
        manifest = inspect_pdf(temporary_pdf, selected_environment)
        validate_render_manifest(manifest)
        if manifest["raw_pdf_sha256"] != _sha256_file(temporary_pdf):
            raise RenderError(
                "render manifest raw_pdf_sha256 does not match temporary PDF"
            )
        temporary_manifest.write_text(
            canonical_json(manifest), encoding="utf-8"
        )
        persisted_manifest = _read_manifest(temporary_manifest)
        if persisted_manifest["raw_pdf_sha256"] != _sha256_file(temporary_pdf):
            raise RenderError(
                "temporary render manifest raw_pdf_sha256 does not match PDF"
            )
        published_pdf: tuple[tuple[int, int], str] | None = None
        try:
            published_pdf = _publish_exclusive(temporary_pdf, output)
            _publish_exclusive(temporary_manifest, manifest_output)
        except BaseException:
            if published_pdf is not None:
                _unlink_exact_artifact(output, *published_pdf)
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
        temporary_pdf.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
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
    "require_canonical_render_manifest",
]
