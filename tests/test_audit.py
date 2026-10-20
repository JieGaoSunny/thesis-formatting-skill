from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from thesis_format.audit import (
    AuditContext,
    AuditFinding,
    RuleRegistry,
    audit_document,
    render_audit_markdown,
)
from thesis_format.contracts import validate_audit
from thesis_format.profile import load_profile

from helpers.docx_factory import build_docx


ROOT = Path(__file__).parents[1]
PROFILE = load_profile(ROOT / "rules" / "apple-university.yaml")
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


class _Rule:
    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id

    def audit(self, context: AuditContext):
        yield AuditFinding(
            rule_id=self.rule_id,
            severity="warning",
            location="document",
            message=f"{self.rule_id} ran.",
            repairable=False,
            before=None,
            after=None,
        )


def test_rule_registry_preserves_registration_order_and_rejects_duplicates() -> None:
    first = _Rule("TEST.FIRST")
    second = _Rule("TEST.SECOND")
    registry = RuleRegistry((first, second))

    assert registry.rules == (first, second)
    with pytest.raises(ValueError, match="duplicate rule_id"):
        RuleRegistry((first, _Rule("TEST.FIRST")))


def test_audit_uses_injected_clock_and_emits_exact_valid_contract(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "thesis.docx",
        [
            {"text": "第一章 绪论", "style": "AppleHeading1"},
            {"text": "1.1 研究背景"},
            {"text": "正文"},
        ],
    )

    report = audit_document(path, PROFILE, clock=lambda: NOW)

    validate_audit(report)
    assert report["created_at"] == "2026-10-20T10:00:00Z"
    assert report["input"] == "thesis.docx"
    assert report["profile"] == "apple-university-thesis"
    assert report["findings"]
    assert report["findings"] == audit_document(
        path, PROFILE, clock=lambda: NOW
    )["findings"]


def test_ambiguous_roles_and_manual_headings_are_reported(
    tmp_path: Path,
) -> None:
    path = build_docx(
        tmp_path / "ambiguous.docx",
        [
            {"text": "第一章 绪论", "style": "AppleHeading1"},
            {"text": "1.1 研究背景"},
            {"text": "可能是标题也可能是正文"},
            {"text": "附录 A 调查表"},
        ],
    )

    report = audit_document(path, PROFILE, clock=lambda: NOW)
    rule_ids = {finding["rule_id"] for finding in report["findings"]}

    assert "SEMANTIC.AMBIGUOUS_ROLE" in rule_ids
    assert "NUMBERING.MANUAL_HEADING" in rule_ids
    assert "NUMBERING.MANUAL_APPENDIX" in rule_ids


def test_privacy_values_are_redacted_in_contract_and_markdown(
    tmp_path: Path,
) -> None:
    secret = "student@example.com"
    path = build_docx(
        tmp_path / "private.docx",
        [{"text": f"Contact {secret} and replace {{{{AUTHOR}}}}"}],
    )

    report = audit_document(path, PROFILE, clock=lambda: NOW)
    markdown = render_audit_markdown(report)

    validate_audit(report)
    assert secret not in repr(report)
    assert secret not in markdown
    assert "{{AUTHOR}}" not in markdown
    assert "[REDACTED]" in markdown
