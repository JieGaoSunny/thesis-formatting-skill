"""Text normalization for substantive-content snapshots."""

from __future__ import annotations

import re
import unicodedata

from thesis_format.profile import FormatProfile


_WHITESPACE = re.compile(r"\s+", re.UNICODE)
_NUMBER_PREFIXES = {
    "heading_1": re.compile(r"^第[一二三四五六七八九十百]+章(?:\s+|$)"),
    "heading_2": re.compile(r"^\d+\.\d+(?:\s+|$)"),
    "heading_3": re.compile(r"^\d+\.\d+\.\d+(?:\s+|$)"),
    "figure_caption": re.compile(r"^图\s*\d+[.-]\d+(?:\s+|$)"),
    "table_caption": re.compile(r"^表\s*\d+[.-]\d+(?:\s+|$)"),
    "reference": re.compile(r"^\[\d+\](?:\s+|$)"),
    "appendix_heading": re.compile(r"^附录\s+[A-Z](?:\s+|$)"),
}


def normalize_text(value: str) -> str:
    """Return NFC text with line endings and Unicode whitespace canonicalized."""

    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return _WHITESPACE.sub(" ", normalized).strip()


def _profile_confirms(text: str, role: str, profile: FormatProfile) -> bool:
    for pattern in profile.role_detection.text_patterns.get(role, ()):
        flags = re.IGNORECASE if "ignore_case" in pattern.flags else 0
        if re.fullmatch(pattern.pattern, text, flags):
            return True
    return False


def strip_manual_numbering(
    text: str,
    role: str | None,
    profile: FormatProfile,
    *,
    evidence_text: str | None = None,
) -> str:
    """Remove a leading number only when an anchored profile role confirms it."""

    normalized = normalize_text(text)
    if role not in _NUMBER_PREFIXES:
        return normalized
    evidence = normalize_text(evidence_text if evidence_text is not None else text)
    if not _profile_confirms(evidence, role, profile):
        return normalized
    return normalize_text(_NUMBER_PREFIXES[role].sub("", normalized, count=1))
