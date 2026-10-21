from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
READMES = (ROOT / "README.md", ROOT / "README.zh-CN.md")
CANONICAL_IMAGE = (
    "ghcr.io/jiegaosunny/thesis-formatting-skill-render@"
    "sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79"
)
COMMANDS = (
    "thesis-format audit thesis.docx --profile rules/university.yaml "
    "--report reports/audit.json --markdown reports/audit.md",
    "thesis-format format thesis.docx --profile rules/university.yaml "
    "--output build/thesis-formatted.docx "
    "--report reports/transformation.json",
    "thesis-format export build/thesis-formatted.docx "
    "--output build/thesis-formatted.pdf "
    "--manifest reports/render-manifest.json",
    "thesis-format preview build/thesis-formatted.pdf "
    "--manifest reports/render-manifest.json --output-dir reports/preview",
    "thesis-format release-check build/thesis-formatted.docx "
    "--profile rules/university.yaml --report reports/privacy.json",
)
SCREENSHOT_NAMES = (
    "cover",
    "toc",
    "body",
    "figure",
    "table",
    "references",
    "appendix",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative_targets(markdown: str) -> set[str]:
    targets = {
        target.split("#", 1)[0]
        for target in re.findall(r"!?\[[^\]]*]\(([^)]+)\)", markdown)
        if target
        and not target.startswith(("#", "http://", "https://", "mailto:"))
    }
    return {target for target in targets if target}


def test_readmes_are_complete_bilingual_equivalents() -> None:
    english, chinese = (_text(path) for path in READMES)

    for text in (english, chinese):
        for heading in (
            "Installation",
            "Workflow",
            "Examples",
            "Repaired defects",
            "Architecture",
            "Tests and reproducibility",
            "Limitations and manual review",
            "Privacy",
        ):
            assert heading.lower() in text.lower()
        for command in COMMANDS:
            assert command in text
        for artifact in (
            "examples/before.docx",
            "examples/after.docx",
            "examples/before.pdf",
            "examples/after.pdf",
            "docs/format-rules.md",
            "docs/limitations.md",
        ):
            assert artifact in text
        for screenshot in SCREENSHOT_NAMES:
            assert (
                f"examples/screenshots/before/demo_{screenshot}-" in text
            )
            assert f"examples/screenshots/after/demo_{screenshot}-" in text
        assert CANONICAL_IMAGE in text
        assert ".claude/skills/thesis-formatting/SKILL.md" in text
        assert ".github/skills/thesis-formatting/SKILL.md" in text

    assert "entirely fictional" in english.lower()
    assert "Apple University" in english
    assert all(word in chinese for word in ("Apple University", "虚构", "人物", "数据"))


def test_all_relative_readme_links_exist() -> None:
    for readme in READMES:
        for target in _relative_targets(_text(readme)):
            assert (ROOT / target).exists(), f"{readme.name}: {target}"


def test_public_documentation_is_anonymous_and_generic() -> None:
    documentation = [
        *READMES,
        ROOT / "docs" / "format-rules.md",
        ROOT / "docs" / "limitations.md",
    ]
    prohibited = (
        "real student",
        "real supervisor",
        "source institution",
        "private university",
        "student id:",
        "学号：",
        "真实姓名",
        "原学校",
        "/users/jie/",
    )

    for path in documentation:
        text = _text(path).casefold()
        assert "apple university" in text or path.parent.name == "docs"
        assert not any(term.casefold() in text for term in prohibited)


def test_ci_is_pinned_reproducible_and_public_safe() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    text = _text(workflow_path)
    workflow = yaml.safe_load(text)

    assert workflow["permissions"] == {"contents": "read"}
    assert {"push", "pull_request", "workflow_dispatch"} <= set(
        workflow.get("on", workflow.get(True))
    )
    assert re.search(r"uv run --frozen pytest .*?-m [\"']not integration[\"']", text)
    assert f"docker pull {CANONICAL_IMAGE}" in text
    assert CANONICAL_IMAGE in text
    assert "tests/test_render.py tests/test_demo_e2e.py" in text
    assert "tests/fixtures/privacy/synthetic-denylist.txt" in text
    assert "tests/test_docs.py" in text
    assert "actions/upload-artifact@" in text
    assert "ci-reports" in text
    assert "PRIVATE" not in text

    action_uses = re.findall(r"uses:\s*([^@\s]+)@([^\s#]+)", text)
    assert action_uses
    for action, revision in action_uses:
        assert re.fullmatch(r"[0-9a-f]{40}", revision), (action, revision)


def test_render_image_workflow_actions_are_commit_pinned() -> None:
    text = _text(ROOT / ".github" / "workflows" / "render-image.yml")
    action_uses = re.findall(r"uses:\s*([^@\s]+)@([^\s#]+)", text)
    assert action_uses
    for action, revision in action_uses:
        assert re.fullmatch(r"[0-9a-f]{40}", revision), (action, revision)
