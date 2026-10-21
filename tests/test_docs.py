from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
READMES = (ROOT / "README.md", ROOT / "README.zh-CN.md")
CANONICAL_IMAGE = (
    "ghcr.io/jiegaosunny/thesis-formatting-skill-render@"
    "sha256:5866364e94961d3e8f33402985f4b2e900febb07a7503e83b8c957216c1c9d79"
)
COMMANDS = (
    "uv run thesis-format audit examples/before.docx "
    "--profile rules/apple-university.yaml "
    "--report build/release/before-audit.json "
    "--markdown build/release/before-audit.md",
    "uv run thesis-format format examples/before.docx "
    "--profile rules/apple-university.yaml "
    "--output build/release/after.docx "
    "--report build/release/transformation.json",
    "uv run thesis-format export build/release/after.docx "
    "--output build/release/after.pdf "
    "--manifest build/release/render-manifest.json --allow-noncanonical",
    "uv run thesis-format preview build/release/after.pdf "
    "--manifest build/release/render-manifest.json "
    "--output-dir build/release/previews",
    "uv run thesis-format release-check build/release "
    "--profile rules/apple-university.yaml "
    "--denylist tests/fixtures/privacy/synthetic-denylist.txt "
    "--report build/privacy.json "
    "--markdown build/privacy.md",
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


def test_documented_demo_command_inputs_exist_or_are_prior_outputs() -> None:
    value_options = {
        "--profile",
        "--denylist",
        "--report",
        "--markdown",
        "--output",
        "--manifest",
        "--output-dir",
    }
    output_options = {
        "--report",
        "--markdown",
        "--output",
        "--manifest",
        "--output-dir",
    }

    for readme in READMES:
        lines = _text(readme).splitlines()
        commands = [line for line in lines if line in COMMANDS]
        assert commands[: len(COMMANDS)] == list(COMMANDS)
        assert set(commands) == set(COMMANDS)
        created_directories = {
            Path(token)
            for line in lines
            if line.startswith("mkdir -p ")
            for token in shlex.split(line)[2:]
        }
        created_directories |= {
            parent
            for directory in tuple(created_directories)
            for parent in directory.parents
            if parent != Path(".")
        }
        produced: set[Path] = set()

        for command in commands:
            arguments = shlex.split(command)
            source = Path(arguments[4])
            assert (
                (ROOT / source).exists()
                or source in produced
                or source in created_directories
            ), command

            for index, argument in enumerate(arguments):
                if argument not in value_options:
                    continue
                path = Path(arguments[index + 1])
                if argument in output_options:
                    assert (
                        (ROOT / path.parent).exists()
                        or path.parent in created_directories
                    ), f"{command}: missing output parent {path.parent}"
                    produced.add(path)
                else:
                    assert (ROOT / path).exists(), f"{command}: {path}"

            if arguments[3] == "release-check":
                generated_release_outputs = {
                    path for path in produced if path != source
                }
                assert generated_release_outputs
                assert all(
                    output.is_relative_to(source)
                    for output in generated_release_outputs
                    if output not in {Path("build/privacy.json"), Path("build/privacy.md")}
                )
                for required in (
                    source / "before-audit.json",
                    source / "after.docx",
                    source / "after.pdf",
                    source / "render-manifest.json",
                    source / "previews",
                ):
                    assert required in produced


def test_no_documentation_or_skill_uses_missing_legacy_profile_path() -> None:
    paths = [
        *READMES,
        ROOT / "SKILL.md",
        ROOT / ".claude" / "skills" / "thesis-formatting" / "SKILL.md",
        ROOT / ".github" / "skills" / "thesis-formatting" / "SKILL.md",
        ROOT / ".github" / "workflows" / "ci.yml",
    ]
    legacy_profile = "rules/" + "university.yaml"
    for path in paths:
        assert legacy_profile not in _text(path)


def test_release_documentation_has_demo_and_private_modes() -> None:
    for readme in READMES:
        text = _text(readme)
        release_commands = [
            line
            for line in text.splitlines()
            if line.startswith("uv run thesis-format release-check ")
        ]
        assert len(release_commands) >= 2
        assert all("--denylist" in command for command in release_commands)
        assert any(
            "release-check examples " in command
            and "tests/fixtures/privacy/synthetic-denylist.txt" in command
            for command in release_commands
        )
        assert "PRIVATE_DENYLIST" in text
        assert "never commit" in text.lower() or "不得提交" in text


def test_documented_cli_commands_use_uv_run() -> None:
    documentation = [
        *READMES,
        ROOT / "SKILL.md",
        ROOT / ".claude" / "skills" / "thesis-formatting" / "SKILL.md",
        ROOT / ".github" / "skills" / "thesis-formatting" / "SKILL.md",
    ]
    for path in documentation:
        for line in _text(path).splitlines():
            if re.match(r"^(?:uv run )?thesis-format ", line):
                assert line.startswith("uv run thesis-format "), f"{path}: {line}"


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
    assert re.search(r"release-check examples\s+\\", text)
    assert "release-check examples/after.docx" not in text
    assert "ci-reports/acceptance-release" in text
    assert re.search(
        r"release-check ci-reports/acceptance-release\s+\\", text
    )
    assert (
        "tests/test_privacy.py::"
        "test_committed_examples_pass_release_check_with_profile_and_denylist"
        in text
    )
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
