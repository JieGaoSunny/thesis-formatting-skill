"""Substantive-content snapshot extraction, comparison, and reporting."""

from thesis_format.snapshot.compare import compare_snapshots
from thesis_format.snapshot.extract import assign_node_ids, extract_snapshot
from thesis_format.snapshot.normalize import normalize_text, strip_manual_numbering
from thesis_format.snapshot.report import write_content_reports

__all__ = [
    "assign_node_ids",
    "compare_snapshots",
    "extract_snapshot",
    "normalize_text",
    "strip_manual_numbering",
    "write_content_reports",
]
