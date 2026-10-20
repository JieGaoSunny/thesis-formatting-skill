"""Compare ordered substantive nodes from two content snapshots."""

from __future__ import annotations

from typing import Iterable, Mapping

from thesis_format.contracts import canonical_sha256


def _flatten(snapshot: Mapping[str, object]) -> list[tuple[str, dict[str, object]]]:
    return [
        (collection, node)
        for collection in ("body", "headers", "footers")
        for node in snapshot[collection]  # type: ignore[index]
    ]


def _structural_key(
    collection: str, node: Mapping[str, object]
) -> tuple[object, ...]:
    location = node["source_location"]
    assert isinstance(location, Mapping)
    return (
        collection,
        node["node_type"],
        location["part"],
        location["path"],
        location["index"],
    )


def _object_identity(node: Mapping[str, object]) -> tuple[object, object] | None:
    if node["node_type"] not in {"image", "table"}:
        return None
    return node["node_type"], node.get("relationship_hash") or node["node_id"]


def _adjacent_identities(
    nodes: list[dict[str, object]], index: int, object_type: str
) -> set[tuple[object, object]]:
    identities: set[tuple[object, object]] = set()
    for neighbor in (index - 1, index + 1):
        if 0 <= neighbor < len(nodes) and nodes[neighbor]["node_type"] == object_type:
            identity = _object_identity(nodes[neighbor])
            if identity is not None:
                identities.add(identity)
    return identities


def _caption_move_allowed(
    node_id: str,
    before: Mapping[str, object],
    after: Mapping[str, object],
    changes: Iterable[Mapping[str, object]],
) -> bool:
    before_body = before["body"]
    after_body = after["body"]
    assert isinstance(before_body, list) and isinstance(after_body, list)
    before_index = next(
        (index for index, node in enumerate(before_body) if node["node_id"] == node_id),
        None,
    )
    after_index = next(
        (index for index, node in enumerate(after_body) if node["node_id"] == node_id),
        None,
    )
    if before_index is None or after_index is None:
        return False
    before_node = before_body[before_index]
    after_node = after_body[after_index]
    if (
        before_node["node_type"] != "caption"
        or after_node["node_type"] != "caption"
        or before_node["normalized_text"] != after_node["normalized_text"]
    ):
        return False
    for change in changes:
        if (
            change.get("operation") != "move_caption"
            or change.get("status") != "applied"
            or change.get("node_id") != node_id
        ):
            continue
        rule_id = str(change.get("rule_id", ""))
        object_type = {
            "FIGURE.CAPTION.POSITION": "image",
            "TABLE.CAPTION.POSITION": "table",
        }.get(rule_id)
        before_binding = change.get("before")
        binding_hash = (
            before_binding.get("object_occurrence_sha256")
            if isinstance(before_binding, Mapping)
            else None
        )
        object_occurrence_sha256 = (
            change.get("object_occurrence_sha256")
            or binding_hash
            or change.get("relationship_sha256")
        )
        if object_type is None or not isinstance(object_occurrence_sha256, str):
            continue
        expected_identity = (object_type, object_occurrence_sha256)
        if (
            expected_identity
            in _adjacent_identities(before_body, before_index, object_type)
            and expected_identity
            in _adjacent_identities(after_body, after_index, object_type)
        ):
            return True
    return False


def compare_snapshots(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    changes: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Return explicit added, removed, changed, and reordered differences."""

    changes = tuple(changes)
    before_flat = _flatten(before)
    after_flat = _flatten(after)
    before_by_id = {
        (collection, str(node["node_id"])): node
        for collection, node in before_flat
    }
    after_by_id = {
        (collection, str(node["node_id"])): node
        for collection, node in after_flat
    }
    shared = set(before_by_id) & set(after_by_id)
    differences: list[dict[str, object]] = []
    for key in sorted(shared):
        before_node = before_by_id[key]
        after_node = after_by_id[key]
        if (
            before_node["node_type"]
            in {"footnote_reference", "endnote_reference"}
            and before_node["source_location"] != after_node["source_location"]
        ):
            differences.append(
                {
                    "kind": "changed",
                    "node_id": str(before_node["node_id"]),
                    "before": before_node,
                    "after": after_node,
                }
            )
    shared_order_unchanged: dict[str, bool] = {}
    for collection in ("body", "headers", "footers"):
        before_shared = [
            str(node["node_id"])
            for name, node in before_flat
            if name == collection and (name, str(node["node_id"])) in shared
        ]
        after_shared = [
            str(node["node_id"])
            for name, node in after_flat
            if name == collection and (name, str(node["node_id"])) in shared
        ]
        shared_order_unchanged[collection] = before_shared == after_shared

    before_unmatched = [
        (collection, node)
        for collection, node in before_flat
        if (collection, str(node["node_id"])) not in shared
    ]
    after_unmatched = [
        (collection, node)
        for collection, node in after_flat
        if (collection, str(node["node_id"])) not in shared
    ]
    after_by_structure = {
        _structural_key(collection, node): (collection, node)
        for collection, node in after_unmatched
    }
    changed_after_ids: set[tuple[str, str]] = set()
    changed_before_ids: set[tuple[str, str]] = set()
    for collection, node in before_unmatched:
        if not shared_order_unchanged[collection]:
            continue
        match = after_by_structure.get(_structural_key(collection, node))
        if match is None:
            continue
        _, after_node = match
        changed_before_ids.add((collection, str(node["node_id"])))
        changed_after_ids.add((collection, str(after_node["node_id"])))
        differences.append(
            {
                "kind": "changed",
                "node_id": str(node["node_id"]),
                "before": node,
                "after": after_node,
            }
        )

    for collection, node in before_unmatched:
        if (collection, str(node["node_id"])) not in changed_before_ids:
            differences.append(
                {
                    "kind": "removed",
                    "node_id": str(node["node_id"]),
                    "before": node,
                    "after": None,
                }
            )
    for collection, node in after_unmatched:
        if (collection, str(node["node_id"])) not in changed_after_ids:
            differences.append(
                {
                    "kind": "added",
                    "node_id": str(node["node_id"]),
                    "before": None,
                    "after": node,
                }
            )

    for collection in ("body", "headers", "footers"):
        before_ids = [
            str(node["node_id"])
            for node in before[collection]  # type: ignore[index]
            if (collection, str(node["node_id"])) in shared
        ]
        after_ids = [
            str(node["node_id"])
            for node in after[collection]  # type: ignore[index]
            if (collection, str(node["node_id"])) in shared
        ]
        if before_ids == after_ids:
            continue
        allowed_caption_ids = {
            node_id
            for node_id in before_ids
            if _caption_move_allowed(node_id, before, after, changes)
        }
        if (
            [node_id for node_id in before_ids if node_id not in allowed_caption_ids]
            == [node_id for node_id in after_ids if node_id not in allowed_caption_ids]
        ):
            continue
        for node_id in before_ids:
            if before_ids.index(node_id) == after_ids.index(node_id):
                continue
            if collection == "body" and _caption_move_allowed(
                node_id, before, after, changes
            ):
                continue
            differences.append(
                {
                    "kind": "reordered",
                    "node_id": node_id,
                    "before": before_by_id[(collection, node_id)],
                    "after": after_by_id[(collection, node_id)],
                }
            )

    return {
        "before_snapshot_sha256": canonical_sha256(before),
        "after_snapshot_sha256": canonical_sha256(after),
        "equivalent": not differences,
        "differences": differences,
    }
