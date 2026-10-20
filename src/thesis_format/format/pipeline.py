"""Audited, content-preserving thesis formatting pipeline."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from thesis_format.audit import audit_document
from thesis_format.contracts import (
    canonical_json,
    shortest_unique_digest_prefixes,
    validate_transformation_result,
)
from thesis_format.format.fields import repair_fields
from thesis_format.format.geometry import repair_geometry
from thesis_format.format.headers import repair_headers
from thesis_format.format.numbering import repair_numbering
from thesis_format.format.objects import repair_objects
from thesis_format.format.styles import repair_styles
from thesis_format.ooxml import OoxmlPackage
from thesis_format.profile import FormatProfile
from thesis_format.semantic import inspect_document
from thesis_format.snapshot import compare_snapshots, extract_snapshot


OPERATION_BY_RULE = {
    "PAGE.PAPER.SIZE": "set-paper-size",
    "PAGE.MARGIN.BODY": "set-section-margins",
    "PAGE.HEADER_FOOTER_DISTANCE": "set-header-footer-distance",
    "PAGE.SECTION.START": "set-section-start",
    "STYLE.DEFINITION": "set-style-definition",
    "STYLE.ROLE.MAPPING": "apply-semantic-style",
    "STYLE.DIRECT_FORMATTING": "remove-effective-direct-formatting",
    "NUMBERING.MANUAL_HEADING": "apply-heading-numbering",
    "NUMBERING.MANUAL_APPENDIX": "apply-appendix-numbering",
    "NUMBERING.MANUAL_CAPTION": "apply-caption-fields",
    "FIELD.TOC.REQUIRED": "repair-toc-field",
    "FIELD.LIST_OF_FIGURES.REQUIRED": "repair-list-of-figures-field",
    "FIELD.LIST_OF_TABLES.REQUIRED": "repair-list-of-tables-field",
    "FIELD.CROSS_REFERENCE.TARGET": "preserve-missing-cross-reference",
    "FIGURE.DIMENSIONS.MAX_WIDTH": "limit-image-width",
    "FIGURE.ALIGNMENT": "align-image",
    "FIGURE.CAPTION.POSITION": "move_caption",
    "TABLE.CAPTION.POSITION": "move_caption",
    "TABLE.REPEAT_HEADER": "repeat-table-header",
    "TABLE.ROW_SPLIT": "prevent-row-split",
    "TABLE.BORDERS.THREE_LINE": "apply-three-line-table",
    "REFERENCE.PARAGRAPH_FORMAT": "set-reference-paragraph-format",
    "HEADER.FOOTER.LINKING": "repair-section-linking",
    "HEADER.FOOTER.HEADER_REQUIRED": "create-section-header",
    "HEADER.FOOTER.HEADER_SOURCE": "set-header-source",
    "HEADER.FOOTER.FOOTER_REQUIRED": "create-section-footer",
    "HEADER.FOOTER.PAGE_NUMBER": "create-page-number-field",
    "HEADER.FOOTER.PAGE_RESET": "set-page-number-reset",
    "HEADER.FOOTER.PAGE_STYLE": "set-page-number-style",
    "HEADER.FOOTER.PAGE_ALIGNMENT": "set-page-number-alignment",
    "SEMANTIC.AMBIGUOUS_ROLE": "preserve-ambiguous-role",
    "SEMANTIC.ROLE_CONFLICT": "preserve-conflicting-role",
}


def _location_key(location: str) -> tuple[object, ...]:
    order = {
        "document": 0,
        "section": 1,
        "paragraph": 2,
        "table": 3,
        "cell": 4,
        "header": 5,
        "footer": 6,
        "part": 7,
    }
    if location == "document":
        return (0,)
    kind, value = location.split(":", 1)
    if kind == "cell":
        return (order[kind], *(int(item) for item in value.split("/")))
    if kind == "part":
        return (order[kind], value)
    return (order[kind], int(value))


def _change_digest(change: dict[str, object]) -> str:
    payload = "|".join(
        (
            "1.0",
            str(change["rule_id"]),
            str(change["location"]),
            canonical_json(change["before"]).rstrip("\n"),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _caption_binding(
    move: dict[str, object],
    before_snapshot: dict[str, object],
) -> tuple[str, str] | None:
    caption_paragraph = int(move["caption_body_number"])
    captions = [
        node
        for node in before_snapshot["body"]  # type: ignore[index]
        if node["node_type"] == "caption"
        and re.search(
            rf"/w:p\[{caption_paragraph}\](?:/|$)",
            str(node["source_location"]["path"]),
        )
    ]
    if len(captions) != 1:
        return None
    if move["object_kind"] == "figure":
        object_type = "image"
        paragraph = int(move["object_number"])
        objects = [
            node
            for node in before_snapshot["body"]  # type: ignore[index]
            if node["node_type"] == object_type
            and re.search(
                rf"/w:p\[{paragraph}\](?:/|$)",
                str(node["source_location"]["path"]),
            )
        ]
    else:
        object_type = "table"
        table_number = int(move["object_number"])
        table_nodes = [
            node
            for node in before_snapshot["body"]  # type: ignore[index]
            if node["node_type"] == object_type
            and re.match(
                r"^/w:document/w:body/w:tbl\[\d+\]/w:tr\[",
                str(node["source_location"]["path"]),
            )
            is not None
        ]
        distinct_tables: list[dict[str, object]] = []
        seen_hashes: set[str] = set()
        for node in table_nodes:
            occurrence_hash = str(node.get("relationship_hash") or "")
            if occurrence_hash and occurrence_hash not in seen_hashes:
                seen_hashes.add(occurrence_hash)
                distinct_tables.append(node)
        objects = distinct_tables[table_number - 1 : table_number]
    if len(objects) != 1:
        return None
    occurrence_hash = objects[0].get("relationship_hash")
    if not occurrence_hash:
        return None
    return str(captions[0]["node_id"]), str(occurrence_hash)


def _reference_format(
    document,
    semantic,
    profile: FormatProfile,
    findings: list[dict[str, object]],
) -> set[str]:
    from thesis_format.format.styles import W, NS
    from thesis_format.demo.build import _insert_by_schema_order

    repaired: set[str] = set()
    paragraphs = document.xpath(".//w:body//w:p", namespaces=NS)
    nodes = {node.location: node for node in semantic.paragraphs}
    for finding in findings:
        if finding["rule_id"] != "REFERENCE.PARAGRAPH_FORMAT":
            continue
        location = str(finding["location"])
        node = nodes.get(location)
        if node is None or node.role != "reference":
            continue
        paragraph = paragraphs[int(location.split(":")[1]) - 1]
        p_pr = paragraph.find("w:pPr", namespaces=NS)
        if p_pr is None:
            p_pr = document.makeelement(f"{W}pPr")
            paragraph.insert(0, p_pr)
        for name in ("spacing", "ind"):
            old = p_pr.find(f"w:{name}", namespaces=NS)
            if old is not None:
                p_pr.remove(old)
        spacing = document.makeelement(f"{W}spacing")
        spacing.set(f"{W}lineRule", "exact")
        spacing.set(
            f"{W}line", str(round(profile.references.line_spacing_pt * 20))
        )
        spacing.set(
            f"{W}before", str(round(profile.references.space_before_pt * 20))
        )
        spacing.set(
            f"{W}after", str(round(profile.references.space_after_pt * 20))
        )
        indent = document.makeelement(f"{W}ind")
        indent.set(
            f"{W}hanging",
            str(round(profile.references.hanging_indent_mm * 1440 / 25.4)),
        )
        _insert_by_schema_order(p_pr, spacing)
        _insert_by_schema_order(p_pr, indent)
        repaired.add(f"{finding['rule_id']}|{location}")
    return repaired


def _allow_bound_table_caption_move(
    comparison: dict[str, object],
    before_snapshot: dict[str, object],
    after_snapshot: dict[str, object],
    changes: list[dict[str, object]],
) -> None:
    allowed_ids: set[str] = set()
    for change in changes:
        if (
            change["rule_id"] != "TABLE.CAPTION.POSITION"
            or change["operation"] != "move_caption"
            or change["status"] != "applied"
        ):
            continue
        allowed_ids.add(str(change["node_id"]))
        relationship = str(change["object_occurrence_sha256"])
        for snapshot in (before_snapshot, after_snapshot):
            allowed_ids.update(
                str(node["node_id"])
                for node in snapshot["body"]  # type: ignore[index]
                if node["node_type"] == "table"
                and node.get("relationship_hash") == relationship
            )
    if not allowed_ids:
        return
    differences = comparison["differences"]
    assert isinstance(differences, list)
    comparison["differences"] = [
        difference
        for difference in differences
        if not (
            difference["kind"] == "reordered"
            and difference["node_id"] in allowed_ids
        )
    ]
    comparison["equivalent"] = not comparison["differences"]


def _allow_verified_header_footer_repairs(
    comparison: dict[str, object],
    changes: list[dict[str, object]],
) -> None:
    allowed: dict[tuple[int, str], set[str]] = {}
    for change in changes:
        if (
            change["status"] != "applied"
            or not str(change["location"]).startswith("section:")
        ):
            continue
        section = int(str(change["location"]).split(":")[1])
        rule_id = str(change["rule_id"])
        if rule_id in {
            "HEADER.FOOTER.HEADER_REQUIRED",
            "HEADER.FOOTER.HEADER_SOURCE",
        }:
            allowed.setdefault((section, "header"), set()).add(rule_id)
        elif rule_id == "HEADER.FOOTER.LINKING":
            for kind in change["before"]:
                if kind in {"header", "footer"}:
                    allowed.setdefault(
                        (section, str(kind)), set()
                    ).add(rule_id)
    if not allowed:
        return
    differences = comparison["differences"]
    assert isinstance(differences, list)

    def story_part(value: object) -> tuple[int, str] | None:
        if not isinstance(value, dict):
            return None
        location = value.get("source_location")
        if not isinstance(location, dict):
            return None
        part = str(location.get("part") or "")
        kind = (
            "header"
            if part.startswith("word/header")
            else "footer"
            if part.startswith("word/footer")
            else None
        )
        match = re.match(r"^/section\[(\d+)\]/", str(location.get("path") or ""))
        return (
            (int(match.group(1)), kind)
            if match is not None and kind is not None
            else None
        )

    def node(value: object) -> dict[str, object] | None:
        return value if isinstance(value, dict) else None

    def rules_for(difference: dict[str, object]) -> set[str]:
        result: set[str] = set()
        for value in (difference.get("before"), difference.get("after")):
            location = story_part(value)
            if location is not None:
                result.update(allowed.get(location, set()))
        return result

    def operation_allows(difference: dict[str, object]) -> bool:
        rules = rules_for(difference)
        before = node(difference.get("before"))
        after = node(difference.get("after"))
        if "HEADER.FOOTER.HEADER_SOURCE" in rules:
            return (
                difference["kind"] in {"changed", "removed"}
                and before is not None
                and before.get("node_type") == "header"
                and (
                    after is None
                    or after.get("node_type") == "header"
                )
            )
        if "HEADER.FOOTER.HEADER_REQUIRED" in rules:
            return (
                difference["kind"] == "added"
                and after is not None
                and after.get("node_type") == "header"
            )
        if "HEADER.FOOTER.LINKING" in rules:
            return (
                difference["kind"] in {"added", "removed", "changed"}
                and (
                    before is None
                    or before.get("node_type") in {"header", "footer"}
                )
                and (
                    after is None
                    or after.get("node_type") in {"header", "footer"}
                )
            )
        return False

    comparison["differences"] = [
        difference
        for difference in differences
        if not operation_allows(difference)
    ]
    comparison["equivalent"] = not comparison["differences"]


def format_document(
    source_path: str | Path,
    output_path: str | Path,
    profile: FormatProfile,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Format a safe copy and return the exact Task 2 transformation contract."""

    source = Path(source_path)
    output = Path(output_path)
    if source.resolve() == output.resolve():
        raise ValueError("source and output paths must differ")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    pre_audit = audit_document(source, profile, clock=clock)
    before_snapshot = extract_snapshot(source, profile)
    semantic = inspect_document(source, profile)
    package = OoxmlPackage.open(source)
    document = package.xml("word/document.xml")
    findings = list(pre_audit["findings"])
    repaired: set[str] = set()
    repaired |= repair_geometry(document, profile, findings)
    if "word/styles.xml" in package.parts:
        repaired |= repair_styles(
            document,
            package.xml("word/styles.xml"),
            semantic,
            profile,
            findings,
        )
    if "word/numbering.xml" in package.parts:
        repaired |= repair_numbering(
            document,
            package.xml("word/numbering.xml"),
            semantic,
            profile,
            findings,
        )
    repaired |= repair_fields(
        document,
        package.xml("word/settings.xml")
        if "word/settings.xml" in package.parts
        else None,
        semantic,
        profile,
        findings,
    )
    object_repairs, caption_moves, caption_unrepaired = repair_objects(
        document, semantic, profile, findings
    )
    repaired |= object_repairs
    repaired |= _reference_format(document, semantic, profile, findings)
    repaired |= repair_headers(
        package, document, semantic, profile, findings
    )

    replacements = {
        name: root
        for name, root in package._xml.items()
        if name.endswith((".xml", ".rels"))
    }
    package.write(output, replacements)
    post_audit = audit_document(output, profile, clock=clock)
    after_snapshot = extract_snapshot(output, profile)

    changes: list[dict[str, object]] = []
    for finding in findings:
        rule_id = str(finding["rule_id"])
        location = str(finding["location"])
        key = f"{rule_id}|{location}"
        status = "applied" if key in repaired else "skipped"
        change: dict[str, object] = {
            "change_id": "",
            "rule_id": rule_id,
            "location": location,
            "operation": OPERATION_BY_RULE.get(
                rule_id, "preserve-unsupported-finding"
            ),
            "before": finding["before"],
            "after": finding["after"] if status == "applied" else None,
            "status": status,
        }
        if change["operation"] == "move_caption" and status == "applied":
            move = caption_moves.get(key)
            binding = (
                _caption_binding(move, before_snapshot)
                if move is not None
                else None
            )
            if binding is None:
                change["status"] = "failed"
                change["after"] = None
                change["operation"] = "failed-unbound-caption-move"
            else:
                node_id, occurrence_hash = binding
                change["node_id"] = node_id
                change["object_occurrence_sha256"] = occurrence_hash
                change["before"] = {
                    "node_id": node_id,
                    "object_occurrence_sha256": occurrence_hash,
                    "position": move["before_position"],
                }
                change["after"] = {
                    "node_id": node_id,
                    "object_occurrence_sha256": occurrence_hash,
                    "position": move["after_position"],
                }
        elif change["operation"] == "move_caption":
            reason = caption_unrepaired.get(key, "missing")
            change["operation"] = (
                "preserve-ambiguous-caption-association"
                if reason == "ambiguous"
                else "preserve-missing-caption-association"
            )
        changes.append(change)

    outstanding = {
        f"{finding['rule_id']}|{finding['location']}"
        for finding in post_audit["findings"]
    }
    for change in changes:
        key = f"{change['rule_id']}|{change['location']}"
        if change["status"] == "applied" and key in outstanding:
            change["status"] = "failed"
            change["after"] = None
            if change["operation"] == "move_caption":
                change["operation"] = "failed-caption-move-postcondition"

    digests = [_change_digest(change) for change in changes]
    if len(digests) != len(set(digests)):
        raise ValueError("formatter produced duplicate semantic changes")
    for change, change_id in zip(
        changes, shortest_unique_digest_prefixes(digests), strict=True
    ):
        change["change_id"] = change_id
    changes.sort(
        key=lambda change: (
            _location_key(str(change["location"])),
            str(change["rule_id"]),
            str(change["change_id"]),
        )
    )
    comparison = compare_snapshots(
        before_snapshot, after_snapshot, changes=changes
    )
    _allow_bound_table_caption_move(
        comparison,
        before_snapshot,
        after_snapshot,
        changes,
    )
    _allow_verified_header_footer_repairs(comparison, changes)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "source_path": str(source),
        "source_sha256": source_sha256,
        "output_path": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "changes": changes,
        "post_audit": post_audit,
        "content_comparison": comparison,
    }
    validate_transformation_result(report)
    return report
