"""Versioned JSON contracts and deterministic semantic validation."""

from __future__ import annotations

import copy
import hashlib
import json
import unicodedata
from collections import Counter
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


SCHEMA_VERSION = "1.0.0"
CONTRACT_NAMES = frozenset(
    {
        "format-profile",
        "audit",
        "transformation-result",
        "content-snapshot",
        "privacy-report",
        "render-manifest",
    }
)


class ContractError(ValueError):
    """A schema or semantic contract violation with a JSON path."""

    def __init__(
        self,
        message: str,
        path: Sequence[str | int] = (),
        *,
        cause: Exception | None = None,
    ) -> None:
        self.path = tuple(path)
        self.cause = cause
        super().__init__(f"{_json_path(self.path)}: {message}")

    @classmethod
    def from_jsonschema(cls, error: ValidationError) -> "ContractError":
        return cls(error.message, tuple(error.absolute_path), cause=error)


def _json_path(path: Sequence[str | int]) -> str:
    result = "$"
    for component in path:
        if isinstance(component, int):
            result += f"[{component}]"
        elif component.isidentifier():
            result += f".{component}"
        else:
            result += f"[{json.dumps(component, ensure_ascii=False)}]"
    return result


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError(
                    f"duplicate object key after NFC normalization: {normalized_key!r}"
                )
            normalized[normalized_key] = _normalize(item)
        return normalized
    return value


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically with NFC strings and a final newline."""

    return (
        json.dumps(
            _normalize(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 digest of a value's canonical UTF-8 JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@lru_cache(maxsize=None)
def _cached_schema(contract_name: str) -> dict[str, Any]:
    if contract_name not in CONTRACT_NAMES:
        raise ContractError(f"unknown contract {contract_name!r}")
    schema_resource = resources.files("thesis_format").joinpath(
        "schemas", f"{contract_name}.schema.json"
    )
    with schema_resource.open("r", encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return schema


def load_schema(contract_name: str) -> dict[str, Any]:
    """Load a packaged schema using ``importlib.resources``."""

    return copy.deepcopy(_cached_schema(contract_name))


def shortest_unique_digest_prefixes(
    digests: Iterable[str], *, minimum: int = 16, step: int = 4
) -> list[str]:
    """Shorten full SHA-256 digests, extending true prefix collisions."""

    values = list(digests)
    if minimum < 1 or step < 1:
        raise ValueError("minimum and step must be positive")
    for digest in values:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"not a lowercase SHA-256 digest: {digest!r}")

    distinct = set(values)
    lengths: dict[str, int] = {digest: minimum for digest in distinct}
    while True:
        groups: dict[str, list[str]] = {}
        for digest in distinct:
            groups.setdefault(digest[: lengths[digest]], []).append(digest)
        collisions = [group for group in groups.values() if len(group) > 1]
        if not collisions:
            break
        for group in collisions:
            for digest in group:
                lengths[digest] = min(64, lengths[digest] + step)
        if any(lengths[digest] == 64 for group in collisions for digest in group):
            break
    return [digest[: lengths[digest]] for digest in values]


def deterministic_ids(payloads: Iterable[Any]) -> list[str]:
    """Create deterministic digest-prefix IDs for canonical JSON payloads."""

    return shortest_unique_digest_prefixes(canonical_sha256(payload) for payload in payloads)


def stable_id(payload: Any) -> str:
    """Create a 16-hex deterministic ID for one payload."""

    return canonical_sha256(payload)[:16]


def _without(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


def _location_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    location = item["location"]
    source = location["source"]
    return (
        source["part"],
        source["index"],
        source["path"],
        -1 if source["page"] is None else source["page"],
        location["node_id"],
        canonical_sha256(_without(item, _id_field(item))),
    )


def _id_field(item: Mapping[str, Any]) -> str:
    for candidate in ("finding_id", "change_id", "match_id"):
        if candidate in item:
            return candidate
    raise ValueError("collection item has no stable ID field")


def _validate_collection(
    items: list[dict[str, Any]],
    *,
    path: tuple[str | int, ...],
    id_field: str,
) -> None:
    payloads = [_without(item, id_field) for item in items]
    expected_ids = deterministic_ids(payloads)
    for index, (item, expected_id) in enumerate(zip(items, expected_ids, strict=True)):
        if item[id_field] != expected_id:
            raise ContractError(
                (
                    f"{id_field} must be deterministic prefix {expected_id!r}; "
                    "collision lengths extend by four hex characters"
                ),
                path + (index, id_field),
            )
    expected_order = sorted(items, key=_location_key)
    if items != expected_order:
        raise ContractError(
            "items must be in stable source-location order",
            path,
        )


def _validate_top_id(
    report: Mapping[str, Any], id_field: str, path: tuple[str | int, ...] = ()
) -> None:
    expected = stable_id(_without(report, id_field))
    if report[id_field] != expected:
        raise ContractError(
            f"{id_field} must be deterministic prefix {expected!r}",
            path + (id_field,),
        )


def _validate_audit(report: dict[str, Any], path: tuple[str | int, ...] = ()) -> None:
    findings = report["findings"]
    _validate_collection(
        findings, path=path + ("findings",), id_field="finding_id"
    )
    counts = Counter(finding["severity"] for finding in findings)
    expected_summary = {
        "error": counts["error"],
        "warning": counts["warning"],
        "info": counts["info"],
    }
    if report["summary"] != expected_summary:
        raise ContractError(
            f"summary must equal {expected_summary!r}", path + ("summary",)
        )
    _validate_top_id(report, "audit_id", path)


def _validate_transformation(report: dict[str, Any]) -> None:
    _validate_collection(
        report["changes"], path=("changes",), id_field="change_id"
    )
    _validate_audit(report["post_audit"], ("post_audit",))
    if report["post_audit"]["document_sha256"] != report["output_document_sha256"]:
        raise ContractError(
            "post audit document must be the transformation output",
            ("post_audit", "document_sha256"),
        )
    comparison = report["content_comparison"]
    if comparison["equivalent"] != (len(comparison["differences"]) == 0):
        raise ContractError(
            "equivalent must be true exactly when differences is empty",
            ("content_comparison", "equivalent"),
        )
    _validate_top_id(report, "transformation_id")


def _validate_snapshot(report: dict[str, Any]) -> None:
    seen: set[str] = set()
    for collection_name, expected_type in (
        ("body", None),
        ("headers", "header"),
        ("footers", "footer"),
    ):
        for index, node in enumerate(report[collection_name]):
            node_id = node["node_id"]
            if node_id in seen:
                raise ContractError(
                    "node_id must be unique",
                    (collection_name, index, "node_id"),
                )
            seen.add(node_id)
            if expected_type is not None and node["node_type"] != expected_type:
                raise ContractError(
                    f"{collection_name} nodes must have node_type {expected_type!r}",
                    (collection_name, index, "node_type"),
                )
    _validate_top_id(report, "snapshot_id")


def _validate_privacy(report: dict[str, Any]) -> None:
    _validate_collection(report["matches"], path=("matches",), id_field="match_id")
    counts = dict(sorted(Counter(match["category"] for match in report["matches"]).items()))
    if report["summary"] != counts:
        raise ContractError(
            f"summary must equal {counts!r}",
            ("summary",),
        )
    _validate_top_id(report, "privacy_report_id")


def _validate_render(report: dict[str, Any]) -> None:
    pages = report["pages"]
    page_numbers = [page["page"] for page in pages]
    expected_numbers = list(range(1, len(pages) + 1))
    if page_numbers != expected_numbers:
        raise ContractError(
            f"pages must be consecutively numbered {expected_numbers!r}",
            ("pages",),
        )
    dimensions = report["page_dimensions"]
    for index, page in enumerate(pages):
        if (
            page["width_pt"] != dimensions["width_pt"]
            or page["height_pt"] != dimensions["height_pt"]
        ):
            raise ContractError(
                "page dimensions must match page_dimensions",
                ("pages", index),
            )
    page_set = set(page_numbers)
    names: set[str] = set()
    for index, destination in enumerate(report["named_destinations"]):
        if destination["page"] not in page_set:
            raise ContractError(
                "named destination references a missing page",
                ("named_destinations", index, "page"),
            )
        if destination["name"] in names:
            raise ContractError(
                "named destination names must be unique",
                ("named_destinations", index, "name"),
            )
        names.add(destination["name"])
    _validate_top_id(report, "render_id")


SEMANTIC_VALIDATORS = {
    "audit": _validate_audit,
    "transformation-result": _validate_transformation,
    "content-snapshot": _validate_snapshot,
    "privacy-report": _validate_privacy,
    "render-manifest": _validate_render,
}


def validate_contract(contract_name: str, instance: Any) -> None:
    """Validate a contract against JSON Schema and semantic invariants."""

    schema = load_schema(contract_name)
    validator = Draft202012Validator(schema)
    error = next(iter(validator.iter_errors(instance)), None)
    if error is not None:
        raise ContractError.from_jsonschema(error) from error
    semantic_validator = SEMANTIC_VALIDATORS.get(contract_name)
    if semantic_validator is not None:
        semantic_validator(instance)


def validate_format_profile(instance: Any) -> None:
    validate_contract("format-profile", instance)


def validate_audit(instance: Any) -> None:
    validate_contract("audit", instance)


def validate_transformation_result(instance: Any) -> None:
    validate_contract("transformation-result", instance)


def validate_content_snapshot(instance: Any) -> None:
    validate_contract("content-snapshot", instance)


def validate_privacy_report(instance: Any) -> None:
    validate_contract("privacy-report", instance)


def validate_render_manifest(instance: Any) -> None:
    validate_contract("render-manifest", instance)
