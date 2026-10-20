"""Command-line entry point for thesis-formatting-skill."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from thesis_format import __version__
from thesis_format.audit import audit_document, render_audit_markdown
from thesis_format.contracts import canonical_json
from thesis_format.format import format_document
from thesis_format.profile import load_profile


ExportFunction = Callable[[Path, Path], Path | Sequence[Path] | None]
PreviewFunction = Callable[[Path, Path], Path | Sequence[Path] | None]
PrivacyFunction = Callable[[Path, Path], Mapping[str, object]]


@dataclass(frozen=True)
class CliDependencies:
    """Optional Task 11/12 integrations supplied by callers or tests."""

    export_document: ExportFunction | None = None
    preview_document: PreviewFunction | None = None
    privacy_check: PrivacyFunction | None = None


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


def _protect_source(source: Path, *destinations: Path | None) -> None:
    source_path = source.resolve()
    for destination in destinations:
        if destination is not None and destination.resolve() == source_path:
            raise ValueError("source and requested output/report paths must differ")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(path)


def _is_unresolved(report: Mapping[str, object]) -> bool:
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return False
    return bool(summary.get("errors", 0) or summary.get("violations", 0))


def _run_audit(args: argparse.Namespace) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _protect_source(args.source, args.report, args.markdown)
    profile = load_profile(args.profile)
    report = audit_document(args.source, profile)
    _write_text(args.report, canonical_json(report))
    if args.markdown is not None:
        _write_text(args.markdown, render_audit_markdown(report))
    return 1 if _is_unresolved(report) else 0


def _run_format(args: argparse.Namespace) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _protect_source(args.source, args.output, args.report)
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
    _protect_source(args.source, args.output)
    if function is None:
        raise RuntimeError(
            "PDF export tooling is unavailable until Task 11; "
            "inject export_document to enable this command"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    function(args.source, args.output)
    print(args.output)
    return 0


def _run_preview(args: argparse.Namespace, function: PreviewFunction | None) -> int:
    _require_file(args.source, "input")
    if function is None:
        raise RuntimeError(
            "preview rendering tooling is unavailable until Task 11; "
            "inject preview_document to enable this command"
        )
    function(args.source, args.output_directory)
    print(args.output_directory)
    return 0


def _run_release_check(
    args: argparse.Namespace, function: PrivacyFunction | None
) -> int:
    _require_file(args.source, "input")
    _require_file(args.profile, "profile")
    _protect_source(args.source, args.report)
    if function is None:
        raise RuntimeError(
            "privacy release-check tooling is unavailable until Task 12; "
            "inject privacy_check to enable this command"
        )
    report = function(args.source, args.profile)
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
