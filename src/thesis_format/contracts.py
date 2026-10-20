"""Versioned JSON contracts and deterministic semantic validation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


SCHEMA_VERSION = "1.0"
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
_TEXT_PATTERN_FLAGS = {
    "ignore_case": re.IGNORECASE,
    "unicode": re.UNICODE,
}
_PRIVACY_PATTERN_FLAGS = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "u": re.UNICODE,
}


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
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ContractError("canonical JSON strings cannot contain lone surrogates")
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


def _validate_canonical_compatibility(
    value: Any, path: tuple[str | int, ...] = ()
) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        try:
            binary64 = float(value)
        except OverflowError:
            binary64 = math.inf
        if not math.isfinite(binary64) or int(binary64) != value:
            raise ContractError(
                f"integer {value} is not exactly representable as an IEEE-754 "
                "binary64, as required by this I-JSON/JCS input policy",
                path,
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("contract inputs must contain only finite numbers", path)
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ContractError(
                "canonical JSON strings cannot contain lone surrogates", path
            )
        return
    if isinstance(value, Mapping):
        normalized_keys: set[str] = set()
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(
                    "canonical JSON object keys must be strings", path
                )
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized_keys:
                raise ContractError(
                    f"duplicate object key after NFC normalization: {normalized_key!r}",
                    (*path, key),
                )
            normalized_keys.add(normalized_key)
            _validate_canonical_compatibility(item, (*path, key))
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_canonical_compatibility(item, (*path, index))
        return
    raise ContractError(
        f"unsupported canonical JSON value type {type(value).__name__!r}", path
    )


def _expand_decimal(mantissa: str, exponent: int) -> str:
    negative = mantissa.startswith("-")
    unsigned = mantissa.removeprefix("-")
    digits = unsigned.replace(".", "")
    decimal_position = unsigned.find(".")
    if decimal_position < 0:
        decimal_position = len(digits)
    decimal_position += exponent

    if decimal_position <= 0:
        rendered = "0." + "0" * -decimal_position + digits
    elif decimal_position >= len(digits):
        rendered = digits + "0" * (decimal_position - len(digits))
    else:
        rendered = digits[:decimal_position] + "." + digits[decimal_position:]
    return f"-{rendered}" if negative else rendered


def _serialize_float(value: float) -> str:
    if not math.isfinite(value):
        raise ContractError("canonical JSON numbers must be finite")
    if value == 0:
        return "0"

    rendered = repr(value).lower()
    if "e" not in rendered:
        return rendered.removesuffix(".0")

    mantissa, exponent_text = rendered.split("e")
    exponent = int(exponent_text)
    if 1e-6 <= abs(value) < 1e21:
        return _expand_decimal(mantissa, exponent)

    mantissa = mantissa.removesuffix(".0")
    sign = "+" if exponent >= 0 else "-"
    return f"{mantissa}e{sign}{abs(exponent)}"


def _serialize_canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        try:
            binary64 = float(value)
        except OverflowError:
            binary64 = math.inf
        if not math.isfinite(binary64) or int(binary64) != value:
            raise ContractError(
                f"integer {value} is not exactly representable as an IEEE-754 "
                "binary64, as required by this I-JSON/JCS input policy"
            )
        return _serialize_float(binary64)
    if isinstance(value, float):
        return _serialize_float(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_serialize_canonical(item) for item in value) + "]"
    if isinstance(value, Mapping):
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(
            f"{_serialize_canonical(key)}:{_serialize_canonical(value[key])}"
            for key in keys
        ) + "}"
    raise ContractError(
        f"unsupported canonical JSON value type {type(value).__name__!r}"
    )


def canonical_json(value: Any) -> str:
    """Serialize NFC-normalized JSON with RFC 8785/JCS number semantics."""

    return _serialize_canonical(_normalize(value)) + "\n"


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

    seen: dict[str, int] = {}
    for index, digest in enumerate(values):
        if digest in seen:
            raise ValueError(
                f"duplicate full digest at indexes {seen[digest]} and {index}: {digest}"
            )
        seen[digest] = index

    lengths: dict[str, int] = {digest: minimum for digest in values}
    while True:
        groups: dict[str, list[str]] = {}
        for digest in values:
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


def _normalized_report_value(value: Any) -> str:
    return canonical_json(value).rstrip("\n")


def _report_item_digest(schema_version: str, item: Mapping[str, Any]) -> str:
    payload = "|".join(
        (
            schema_version,
            unicodedata.normalize("NFC", item["rule_id"]),
            unicodedata.normalize("NFC", item["location"]),
            _normalized_report_value(item["before"]),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _privacy_finding_digest(
    schema_version: str, item: Mapping[str, Any]
) -> str:
    return canonical_sha256(
        [
            schema_version,
            item["rule_id"],
            item["path"],
            item["location"],
            item["redacted_match_sha256"],
        ]
    )


def _validate_payload_ids(
    items: list[dict[str, Any]],
    *,
    path: tuple[str | int, ...],
    id_field: str,
    digest_function: Any,
) -> None:
    full_digests = [digest_function(item) for item in items]
    seen_digests: dict[str, int] = {}
    for index, digest in enumerate(full_digests):
        if digest in seen_digests:
            raise ContractError(
                (
                    "duplicate semantic key/full digest; "
                    f"duplicates item {seen_digests[digest]}"
                ),
                path + (index, id_field),
            )
        seen_digests[digest] = index
    expected_ids = shortest_unique_digest_prefixes(full_digests)
    for index, (item, expected_id) in enumerate(zip(items, expected_ids, strict=True)):
        if item[id_field] != expected_id:
            raise ContractError(
                (
                    f"{id_field} must be deterministic prefix {expected_id!r}; "
                    "collision lengths extend by four hex characters"
                ),
                path + (index, id_field),
            )


_LOCATION_RANK = {
    "document": 0,
    "section": 1,
    "paragraph": 2,
    "table": 3,
    "cell": 4,
    "header": 5,
    "footer": 6,
    "part": 7,
}


def _document_location_key(location: str) -> tuple[Any, ...]:
    if location == "document":
        return (_LOCATION_RANK["document"],)
    kind, value = location.split(":", 1)
    if kind == "cell":
        return (_LOCATION_RANK[kind], *(int(part) for part in value.split("/")))
    if kind == "part":
        return (_LOCATION_RANK[kind], unicodedata.normalize("NFC", value))
    return (_LOCATION_RANK[kind], int(value))


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
    try:
        created_at = datetime.fromisoformat(report["created_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(
            "created_at must be an RFC 3339 date-time",
            path + ("created_at",),
            cause=error,
        ) from error
    if created_at.tzinfo is None:
        raise ContractError(
            "created_at must include an RFC 3339 timezone",
            path + ("created_at",),
        )

    findings = report["findings"]
    _validate_payload_ids(
        findings,
        path=path + ("findings",),
        id_field="finding_id",
        digest_function=lambda item: _report_item_digest(
            report["schema_version"], item
        ),
    )
    counts = Counter(finding["severity"] for finding in findings)
    expected_summary = {
        "errors": counts["error"],
        "violations": counts["violation"],
        "warnings": counts["warning"],
    }
    if report["summary"] != expected_summary:
        raise ContractError(
            f"summary must equal {expected_summary!r}", path + ("summary",)
        )
    severity_order = {"error": 0, "violation": 1, "warning": 2}
    expected_order = sorted(
        findings,
        key=lambda item: (
            _document_location_key(item["location"]),
            severity_order[item["severity"]],
            item["rule_id"],
            item["finding_id"],
        ),
    )
    if findings != expected_order:
        raise ContractError(
            "findings must be ordered by document location, severity, rule_id, and finding_id",
            path + ("findings",),
        )


def _validate_transformation(report: dict[str, Any]) -> None:
    changes = report["changes"]
    _validate_payload_ids(
        changes,
        path=("changes",),
        id_field="change_id",
        digest_function=lambda item: _report_item_digest(
            report["schema_version"], item
        ),
    )
    expected_order = sorted(
        changes,
        key=lambda item: (
            _document_location_key(item["location"]),
            item["rule_id"],
            item["change_id"],
        ),
    )
    if changes != expected_order:
        raise ContractError(
            "changes must be ordered by location, rule_id, and change_id",
            ("changes",),
        )
    _validate_audit(report["post_audit"], ("post_audit",))
    if report["post_audit"]["document_sha256"] != report["output_sha256"]:
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
    findings = report["findings"]
    _validate_payload_ids(
        findings,
        path=("findings",),
        id_field="finding_id",
        digest_function=lambda item: _privacy_finding_digest(
            report["schema_version"], item
        ),
    )
    expected_order = sorted(
        findings,
        key=lambda item: (
            unicodedata.normalize("NFC", item["path"]),
            unicodedata.normalize("NFC", item["location"]),
            item["rule_id"],
            item["redacted_match_sha256"],
            item["finding_id"],
        ),
    )
    if findings != expected_order:
        raise ContractError(
            "findings must be ordered by path, location, rule_id, redacted hash, and finding_id",
            ("findings",),
        )
    counts = Counter(finding["severity"] for finding in findings)
    expected_summary = {
        "errors": counts["error"],
        "violations": counts["violation"],
        "warnings": counts["warning"],
    }
    if report["summary"] != expected_summary:
        raise ContractError(
            f"summary must equal {expected_summary!r}",
            ("summary",),
        )


def _validate_render(report: dict[str, Any]) -> None:
    expected_font_manifest_hash = canonical_sha256(report["font_manifest"])
    if report["font_manifest_hash"] != expected_font_manifest_hash:
        raise ContractError(
            (
                "font_manifest_hash must equal the canonical font_manifest digest "
                f"{expected_font_manifest_hash!r}"
            ),
            ("font_manifest_hash",),
        )
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
    pages_by_number = {page["page"]: page for page in pages}
    names: set[str] = set()
    for index, destination in enumerate(report["named_destinations"]):
        destination_page = pages_by_number.get(destination["page"])
        if destination_page is None:
            raise ContractError(
                "named destination references a missing page",
                ("named_destinations", index, "page"),
            )
        for coordinate, dimension in (
            ("x_pt", "width_pt"),
            ("y_pt", "height_pt"),
        ):
            if destination[coordinate] > destination_page[dimension]:
                raise ContractError(
                    (
                        f"{coordinate} must be within referenced page {dimension} "
                        f"{destination_page[dimension]!r}"
                    ),
                    ("named_destinations", index, coordinate),
                )
        if destination["name"] in names:
            raise ContractError(
                "named destination names must be unique",
                ("named_destinations", index, "name"),
            )
        names.add(destination["name"])
    _validate_top_id(report, "render_id")


def _compile_regex(
    pattern: str,
    flag_names: Sequence[str],
    flag_map: Mapping[str, re.RegexFlag],
    path: tuple[str | int, ...],
) -> None:
    if len(flag_names) != len(set(flag_names)):
        raise ContractError("regex flags must not contain duplicates", path)
    unsupported = sorted(set(flag_names) - flag_map.keys())
    if unsupported:
        raise ContractError(
            f"unsupported regex flags: {', '.join(unsupported)}",
            path,
        )

    flags = re.NOFLAG
    for flag_name in flag_names:
        flags |= flag_map[flag_name]
    try:
        re.compile(pattern, flags)
    except (re.error, ValueError) as error:
        raise ContractError(
            f"invalid regular expression or incompatible flags: {error}",
            path,
            cause=error,
        ) from error


def _validate_format_profile(profile: dict[str, Any]) -> None:
    paper = profile["page"]["paper"]
    margins = profile["page"]["body"]
    measurements = {
        ("page", "paper", "width_mm"): paper["width_mm"],
        ("page", "paper", "height_mm"): paper["height_mm"],
        ("page", "body", "top_mm"): margins["top_mm"],
        ("page", "body", "bottom_mm"): margins["bottom_mm"],
        ("page", "body", "left_mm"): margins["left_mm"],
        ("page", "body", "right_mm"): margins["right_mm"],
    }
    for path, measurement in measurements.items():
        if not math.isfinite(measurement) or measurement <= 0:
            raise ContractError(
                "paper dimensions and margins must be positive finite numbers",
                path,
            )

    content_width = (
        paper["width_mm"] - margins["left_mm"] - margins["right_mm"]
    )
    content_height = (
        paper["height_mm"] - margins["top_mm"] - margins["bottom_mm"]
    )
    if content_width <= 0:
        raise ContractError(
            "margins must leave positive content width",
            ("page", "body"),
        )
    if content_height <= 0:
        raise ContractError(
            "margins must leave positive content height",
            ("page", "body"),
        )

    heading_roles = (
        "front_heading",
        "heading_1",
        "heading_2",
        "heading_3",
        "appendix_heading",
    )
    for role in heading_roles:
        paragraph = profile["styles"][role]["paragraph"]
        for field in ("first_line_chars", "left_indent_mm", "hanging_indent_mm"):
            if paragraph[field] != 0:
                raise ContractError(
                    "heading indentation values must all be zero",
                    ("styles", role, "paragraph", field),
                )

    if profile["figures"]["max_width_mm"] - content_width > 1e-9:
        raise ContractError(
            "figure maximum width may not exceed body content width",
            ("figures", "max_width_mm"),
        )

    aliases: dict[str, str] = {}
    for role, style in profile["styles"].items():
        for index, alias in enumerate(style["word_styles"]):
            previous_role = aliases.get(alias)
            if previous_role is not None:
                raise ContractError(
                    (
                        "each word_styles alias must map to exactly one semantic "
                        f"role; {alias!r} also maps to {previous_role!r}"
                    ),
                    ("styles", role, "word_styles", index),
                )
            aliases[alias] = role

    reference_style = profile["styles"]["reference"]["paragraph"]
    references = profile["references"]
    expected_line_spacing = {
        "type": "exact",
        "value_pt": references["line_spacing_pt"],
    }
    if reference_style["line_spacing"] != expected_line_spacing:
        raise ContractError(
            f"reference line_spacing must equal {expected_line_spacing!r}",
            ("styles", "reference", "paragraph", "line_spacing"),
        )
    for field in ("space_before_pt", "space_after_pt", "hanging_indent_mm"):
        if reference_style[field] != references[field]:
            raise ContractError(
                f"reference style {field} must equal references.{field}",
                ("styles", "reference", "paragraph", field),
            )

    if profile["figures"]["caption_position"] != "below":
        raise ContractError(
            "figures.caption_position must be 'below'",
            ("figures", "caption_position"),
        )
    if profile["tables"]["caption_position"] != "above":
        raise ContractError(
            "tables.caption_position must be 'above'",
            ("tables", "caption_position"),
        )

    headers_footers = profile["headers_footers"]
    page_alignment = profile["fields"]["page_number"]["alignment"]
    for region_name in ("front_matter", "body", "appendix"):
        region = headers_footers[region_name]
        if not region["header_enabled"] and region["header_source"] != "none":
            raise ContractError(
                "header_source must be none when header_enabled is false",
                ("headers_footers", region_name, "header_source"),
            )
        if region["header_style_role"] not in profile["styles"]:
            raise ContractError(
                "header_style_role must name an existing semantic style",
                ("headers_footers", region_name, "header_style_role"),
            )
        if (
            region["page_number_enabled"]
            and region["page_number_alignment"] != page_alignment
        ):
            raise ContractError(
                "enabled page_number_alignment must equal fields.page_number.alignment",
                ("headers_footers", region_name, "page_number_alignment"),
            )

    parts = profile["front_matter"]["parts"]
    part_by_id = {part["id"]: part for part in parts}
    for field_name in ("toc", "list_of_figures", "list_of_tables"):
        if profile["fields"][field_name]["required"]:
            part = part_by_id.get(field_name)
            if part is None or part["heading_role"] not in profile["styles"]:
                raise ContractError(
                    f"required field {field_name} must map to an existing front-matter style",
                    ("fields", field_name, "required"),
                )

    front_region = headers_footers["front_matter"]
    numbered_parts = [
        part for part in parts if part["page_number_style"] != "none"
    ]
    if front_region["page_number_enabled"]:
        if not numbered_parts:
            raise ContractError(
                "front page numbering is enabled but no front-matter part is numbered",
                ("front_matter", "parts"),
            )
        for index, part in enumerate(parts):
            if (
                part["page_number_style"] != "none"
                and part["page_number_style"] != front_region["page_number_style"]
            ):
                raise ContractError(
                    "front part page-number style must match headers_footers.front_matter",
                    ("front_matter", "parts", index, "page_number_style"),
                )
    elif numbered_parts:
        raise ContractError(
            "front page numbering is disabled but a front-matter part is numbered",
            ("front_matter", "parts"),
        )

    first_numbered = numbered_parts[0] if numbered_parts else None
    if first_numbered is not None and not first_numbered["starts_section"]:
        raise ContractError(
            "the first numbered front-matter part must start a section for page reset",
            ("front_matter", "parts"),
        )

    for index, part in enumerate(parts):
        expected_show_header = (
            front_region["header_enabled"]
            and part["page_number_style"] != "none"
        )
        if part["show_header"] != expected_show_header:
            raise ContractError(
                "front_matter show_header must match rendered front header behavior",
                ("front_matter", "parts", index, "show_header"),
            )

    body_region = headers_footers["body"]
    if (
        not body_region["page_number_enabled"]
        or body_region["page_number_style"] != "decimal"
    ):
        raise ContractError(
            "body page numbering must be enabled with decimal style",
            ("headers_footers", "body", "page_number_style"),
        )
    if (
        front_region["page_number_style"] == "decimal"
        and body_region["page_number_style"] == "decimal"
    ):
        raise ContractError(
            "front and body decimal pagination ranges must not overlap; body reset is required",
            ("headers_footers", "front_matter", "page_number_style"),
        )
    appendix_region = headers_footers["appendix"]
    if (
        appendix_region["page_number_enabled"]
        and appendix_region["page_number_style"]
        != body_region["page_number_style"]
    ):
        raise ContractError(
            "appendix page-number style must continue the body pagination style",
            ("headers_footers", "appendix", "page_number_style"),
        )

    toc_levels = profile["fields"]["toc"]["levels"]
    if toc_levels["min"] > toc_levels["max"]:
        raise ContractError(
            "TOC levels require min <= max",
            ("fields", "toc", "levels"),
        )

    position_constraints = profile["role_detection"]["position_constraints"]
    for role, constraints in position_constraints.items():
        for index, constraint in enumerate(constraints):
            maximum = constraint["max_index"]
            if maximum is not None and constraint["min_index"] > maximum:
                raise ContractError(
                    "position range requires min_index <= max_index",
                    (
                        "role_detection",
                        "position_constraints",
                        role,
                        index,
                    ),
                )

    text_patterns = profile["role_detection"]["text_patterns"]
    for role, patterns in text_patterns.items():
        for index, pattern in enumerate(patterns):
            expression = pattern["pattern"]
            terminal_dollar_escaped = (
                expression.endswith("$")
                and len(expression) >= 2
                and (
                    len(expression[:-1])
                    - len(expression[:-1].rstrip("\\"))
                )
                % 2
                == 1
            )
            if (
                not expression.startswith("^")
                or not expression.endswith("$")
                or terminal_dollar_escaped
            ):
                raise ContractError(
                    "role detection patterns must start with ^ and end with an unescaped $",
                    (
                        "role_detection",
                        "text_patterns",
                        role,
                        index,
                        "pattern",
                    ),
                )
            _compile_regex(
                expression,
                pattern["flags"],
                _TEXT_PATTERN_FLAGS,
                (
                    "role_detection",
                    "text_patterns",
                    role,
                    index,
                ),
            )

    privacy = profile["privacy"]
    for index, pattern in enumerate(privacy["generic_patterns"]):
        _compile_regex(
            pattern["regex"],
            list(pattern["flags"]),
            _PRIVACY_PATTERN_FLAGS,
            ("privacy", "generic_patterns", index),
        )
    for index, pattern in enumerate(privacy["unresolved_placeholder_patterns"]):
        _compile_regex(
            pattern,
            (),
            _PRIVACY_PATTERN_FLAGS,
            ("privacy", "unresolved_placeholder_patterns", index),
        )


SEMANTIC_VALIDATORS = {
    "format-profile": _validate_format_profile,
    "audit": _validate_audit,
    "transformation-result": _validate_transformation,
    "content-snapshot": _validate_snapshot,
    "privacy-report": _validate_privacy,
    "render-manifest": _validate_render,
}


def validate_contract(contract_name: str, instance: Any) -> None:
    """Validate a contract against JSON Schema and semantic invariants."""

    _validate_canonical_compatibility(instance)
    schema = load_schema(contract_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
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
