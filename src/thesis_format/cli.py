"""Command-line entry point for thesis-formatting-skill."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from thesis_format import __version__
from thesis_format.audit import audit_document, render_audit_markdown
from thesis_format.contracts import (
    canonical_json,
    validate_privacy_report,
    validate_render_manifest,
)
from thesis_format.format import format_document
from thesis_format.profile import load_profile


ExportFunction = Callable[[Path, Path], Path | Sequence[Path] | None]
PreviewFunction = Callable[[Path, Path], Path | Sequence[Path] | None]
PrivacyFunction = Callable[[Path, Path], Mapping[str, object]]


def _default_export_document(
    source: Path, output: Path
) -> Path | Sequence[Path] | None:
    try:
        from thesis_format.render import export_document
    except ImportError as error:
        raise RuntimeError(
            "optional PDF export tooling is unavailable; install tooling that "
            "provides thesis_format.render.export_document"
        ) from error
    return export_document(source, output)


def _default_preview_pdf(
    source: Path, output_directory: Path
) -> Path | Sequence[Path] | None:
    try:
        from thesis_format.render import preview_pdf
    except ImportError as error:
        raise RuntimeError(
            "optional preview tooling is unavailable; install tooling that "
            "provides thesis_format.render.preview_pdf"
        ) from error
    return preview_pdf(source, output_directory)


def _default_release_check(
    source: Path, profile: Path
) -> Mapping[str, object]:
    try:
        from thesis_format.privacy import release_check
    except ImportError as error:
        raise RuntimeError(
            "optional privacy tooling is unavailable; install tooling that "
            "provides thesis_format.privacy.release_check"
        ) from error
    return release_check(source, profile)


@dataclass(frozen=True)
class CliDependencies:
    """Optional Task 11/12 integrations supplied by callers or tests."""

    export_document: ExportFunction | None = _default_export_document
    preview_document: PreviewFunction | None = _default_preview_pdf
    privacy_check: PrivacyFunction | None = _default_release_check


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thesis-format")
    parser.add_argument(
        "--version",
        action="version",
        version=f"thesis-formatting-skill {__version__}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit", help="audit a DOCX against a profile")
    audit.add_argument("source", type=Path)
    audit.add_argument("--profile", type=Path, required=True)
    audit.add_argument("--report", "--json", dest="report", type=Path, required=True)
    audit.add_argument("--markdown", type=Path)

    formatter = commands.add_parser(
        "format", help="write a formatted DOCX copy and transformation report"
    )
    formatter.add_argument("source", type=Path)
    formatter.add_argument("--profile", type=Path, required=True)
    formatter.add_argument("--output", type=Path, required=True)
    formatter.add_argument("--report", type=Path, required=True)

    exporter = commands.add_parser("export", help="export a DOCX to PDF")
    exporter.add_argument("source", type=Path)
    exporter.add_argument("--output", "--pdf", dest="output", type=Path, required=True)

    preview = commands.add_parser("preview", help="render DOCX preview images")
    preview.add_argument("source", type=Path)
    preview.add_argument(
        "--output-dir", "--output", dest="output_directory", type=Path, required=True
    )

    release = commands.add_parser(
        "release-check", help="run the privacy release check"
    )
    release.add_argument("source", type=Path)
    release.add_argument("--profile", type=Path, required=True)
    release.add_argument("--report", type=Path, required=True)
    return parser


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")


def _path_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


def _reject_path_collisions(
    *artifacts: tuple[str, Path | None],
) -> None:
    requested = [
        (label, path, path.resolve(), _path_identity(path))
        for label, path in artifacts
        if path is not None
    ]
    for index, (left_label, left, left_resolved, left_identity) in enumerate(
        requested
    ):
        for (
            right_label,
            right,
            right_resolved,
            right_identity,
        ) in requested[index + 1 :]:
            same_resolved_path = left_resolved == right_resolved
            same_inode = (
                left_identity is not None
                and right_identity is not None
                and left_identity == right_identity
            )
            try:
                same_file = left.samefile(right)
            except OSError:
                same_file = False
            if same_resolved_path or same_inode or same_file:
                raise ValueError(
                    f"{left_label} and {right_label} paths must differ"
                )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path)


def _provider_paths(result: object) -> tuple[Path, ...]:
    if result is None:
        return ()
    if isinstance(result, Path):
        return (result,)
    if isinstance(result, (str, bytes, Mapping)) or not isinstance(
        result, Sequence
    ):
        raise ValueError("provider returned invalid artifact paths")
    paths: list[Path] = []
    for item in result:
        if not isinstance(item, (str, Path)):
            raise ValueError("provider returned invalid artifact paths")
        paths.append(Path(item))
    return tuple(paths)


def _require_nonempty_regular_file(path: Path, label: str) -> None:
    try:
        valid = path.is_file() and path.stat().st_size > 0
    except OSError:
        valid = False
    if not valid:
        raise ValueError(
            f"{label} does not exist or is not a nonempty regular file: {path}"
        )


def _validate_returned_artifacts(paths: Sequence[Path]) -> None:
    for path in paths:
        _require_nonempty_regular_file(path, "provider artifact")
        if path.suffix.lower() == ".json":
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid render manifest: {path}") from error
            validate_render_manifest(manifest)


def _is_unresolved(report: Mapping[str, object]) -> bool:
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return False
    return bool(summary.get("errors", 0) or summary.get("violations", 0))


def _run_audit(args: argparse.Namespace) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _reject_path_collisions(
        ("source", args.source),
        ("profile", args.profile),
        ("report", args.report),
        ("markdown report", args.markdown),
    )
    profile = load_profile(args.profile)
    report = audit_document(args.source, profile)
    _write_text(args.report, canonical_json(report))
    if args.markdown is not None:
        _write_text(args.markdown, render_audit_markdown(report))
    return 1 if _is_unresolved(report) else 0


def _run_format(args: argparse.Namespace) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _reject_path_collisions(
        ("source", args.source),
        ("profile", args.profile),
        ("output", args.output),
        ("report", args.report),
    )
    profile = load_profile(args.profile)
    report = format_document(args.source, args.output, profile)
    print(args.output)
    _write_text(args.report, canonical_json(report))
    post_audit = report.get("post_audit")
    comparison = report.get("content_comparison")
    unresolved = (
        isinstance(post_audit, Mapping)
        and _is_unresolved(post_audit)
        or not isinstance(comparison, Mapping)
        or comparison.get("equivalent") is not True
    )
    return 1 if unresolved else 0


def _run_export(args: argparse.Namespace, function: ExportFunction | None) -> int:
    _require_file(args.source, "input")
    _reject_path_collisions(("source", args.source), ("output", args.output))
    if function is None:
        raise RuntimeError(
            "optional PDF export tooling is unavailable; install tooling that "
            "provides thesis_format.render.export_document"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    returned_paths = _provider_paths(function(args.source, args.output))
    _require_nonempty_regular_file(args.output, "PDF output")
    _validate_returned_artifacts(
        tuple(path for path in returned_paths if path != args.output)
    )
    print(args.output)
    return 0


def _run_preview(args: argparse.Namespace, function: PreviewFunction | None) -> int:
    _require_file(args.source, "input")
    _reject_path_collisions(
        ("source", args.source),
        ("preview output", args.output_directory),
    )
    if function is None:
        raise RuntimeError(
            "optional preview tooling is unavailable; install tooling that "
            "provides thesis_format.render.preview_pdf"
        )
    returned_paths = _provider_paths(function(args.source, args.output_directory))
    _validate_returned_artifacts(returned_paths)
    image_suffixes = {
        ".bmp",
        ".gif",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }
    returned_images = [
        path for path in returned_paths if path.suffix.lower() in image_suffixes
    ]
    if returned_images:
        images = returned_images
    elif args.output_directory.is_dir():
        images = [
            path
            for path in args.output_directory.rglob("*")
            if path.suffix.lower() in image_suffixes
        ]
    else:
        images = []
    if not images:
        raise ValueError("preview provider produced no image artifacts")
    for image in images:
        _require_nonempty_regular_file(image, "preview image")
    print(args.output_directory)
    return 0


def _run_release_check(
    args: argparse.Namespace, function: PrivacyFunction | None
) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _reject_path_collisions(
        ("source", args.source),
        ("profile", args.profile),
        ("report", args.report),
    )
    if function is None:
        raise RuntimeError(
            "optional privacy tooling is unavailable; install tooling that "
            "provides thesis_format.privacy.release_check"
        )
    report = function(args.source, args.profile)
    validate_privacy_report(report)
    _write_text(args.report, canonical_json(report))
    return 1 if _is_unresolved(report) else 0


def main(
    argv: Sequence[str] | None = None,
    *,
    dependencies: CliDependencies | None = None,
) -> int:
    """Run the CLI and return its documented process exit code."""

    args = _parser().parse_args(argv)
    dependencies = dependencies or CliDependencies()
    try:
        if args.command == "audit":
            return _run_audit(args)
        if args.command == "format":
            return _run_format(args)
        if args.command == "export":
            return _run_export(args, dependencies.export_document)
        if args.command == "preview":
            return _run_preview(args, dependencies.preview_document)
        if args.command == "release-check":
            return _run_release_check(args, dependencies.privacy_check)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"thesis-format: {error}", file=sys.stderr)
        return 2
    return 2


__all__ = ["CliDependencies", "main"]
