from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_PATHS = (
    ROOT / "SKILL.md",
    ROOT / ".claude" / "skills" / "thesis-formatting" / "SKILL.md",
    ROOT / ".github" / "skills" / "thesis-formatting" / "SKILL.md",
)


def _skill() -> str:
    return SKILL_PATHS[0].read_text(encoding="utf-8")


def test_cross_agent_skill_copies_are_byte_identical() -> None:
    payloads = [path.read_bytes() for path in SKILL_PATHS]

    assert len({hashlib.sha256(payload).hexdigest() for payload in payloads}) == 1


def test_frontmatter_is_small_exact_and_discoverable() -> None:
    text = _skill()
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    assert len(match.group(1).encode("utf-8")) <= 1024
    frontmatter = yaml.safe_load(match.group(1))

    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "thesis-formatting"
    assert re.fullmatch(r"[A-Za-z0-9-]+", frontmatter["name"])
    assert frontmatter["description"].startswith("Use when...")
    assert "DOCX" in frontmatter["description"]
    assert "Chinese" in frontmatter["description"]
    assert "before/after" in frontmatter["description"]
    assert not any(
        word in frontmatter["description"].lower()
        for word in ("audit first", "workflow", "format then", "steps")
    )


def test_skill_closes_every_observed_baseline_loophole() -> None:
    text = _skill().lower()

    required_rules = (
        "audit before",
        "supplied profile",
        "never overwrite",
        "new output",
        "deterministic formatter",
        "prebuilt",
        "do not infer",
        "ambiguous",
        "identity",
        "post-audit",
        "content snapshot",
        "render",
        "report",
        "warning",
        "never claim compliance",
        "validation incomplete",
        "privacy",
        "release-check",
        "substantive comparison",
        "tests",
    )
    for rule in required_rules:
        assert rule in text


def test_skill_has_exact_commands_quick_reference_and_pressure_red_flags() -> None:
    text = _skill()

    assert "## Quick Reference" in text
    assert "## Common Mistakes and Red Flags" in text
    assert (
        "thesis-format audit thesis.docx --profile rules/university.yaml "
        "--report reports/audit.json --markdown reports/audit.md"
    ) in text
    assert (
        "thesis-format format thesis.docx --profile rules/university.yaml "
        "--output build/thesis-formatted.docx "
        "--report reports/transformation.json"
    ) in text
    assert (
        "thesis-format export build/thesis-formatted.docx "
        "--output build/thesis-formatted.pdf"
    ) in text
    for rationalization in (
        "The deadline is close",
        "copy the prepared template",
        "visual check is enough",
        "skip the report",
        "replace the source",
    ):
        assert rationalization in text


def test_skill_documents_test_commands_and_all_installation_paths() -> None:
    text = _skill()

    assert "uv run pytest" in text
    assert "require installed renderer and privacy tooling" in text
    assert "unavailable renderer blocks compliance" in text
    assert "unavailable privacy tooling blocks release" in text
    for path in (
        "SKILL.md",
        ".claude/skills/thesis-formatting/SKILL.md",
        ".github/skills/thesis-formatting/SKILL.md",
    ):
        assert f"`{path}`" in text
