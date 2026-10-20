"""Write canonical snapshot artifacts and a human-readable content diff."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from thesis_format.contracts import canonical_json


def _summary(comparison: Mapping[str, object]) -> str:
    differences = comparison["differences"]
    assert isinstance(differences, list)
    lines = [
        "# Content preservation diff",
        "",
        f"Equivalent: **{'yes' if comparison['equivalent'] else 'no'}**",
        "",
    ]
    if not differences:
        lines.append("No substantive content differences.")
        return "\n".join(lines) + "\n"
    lines.extend(["| Kind | Node | Before | After |", "|---|---|---|---|"])
    for difference in differences:
        before = difference.get("before") or {}
        after = difference.get("after") or {}
        before_text = str(before.get("normalized_text", "")).replace("|", "\\|")
        after_text = str(after.get("normalized_text", "")).replace("|", "\\|")
        lines.append(
            f"| {difference['kind']} | `{difference['node_id']}` | "
            f"{before_text} | {after_text} |"
        )
    return "\n".join(lines) + "\n"


def write_content_reports(
    output_directory: str | Path,
    before: Mapping[str, object],
    after: Mapping[str, object],
    comparison: Mapping[str, object],
) -> dict[str, Path]:
    """Write content-before.json, content-after.json, and content-diff.md."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "before": directory / "content-before.json",
        "after": directory / "content-after.json",
        "diff": directory / "content-diff.md",
    }
    paths["before"].write_text(canonical_json(before), encoding="utf-8")
    paths["after"].write_text(canonical_json(after), encoding="utf-8")
    paths["diff"].write_text(_summary(comparison), encoding="utf-8")
    return paths
