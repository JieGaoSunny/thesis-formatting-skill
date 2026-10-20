from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import struct
from importlib import resources
from pathlib import Path

import pytest

from thesis_format.contracts import (
    ContractError,
    canonical_json,
    load_schema,
    shortest_unique_digest_prefixes,
    stable_id,
    validate_contract,
)


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
CONTRACTS = {
    "format-profile": "format-profile.json",
    "audit": "audit.json",
    "transformation-result": "transformation-result.json",
    "content-snapshot": "content-snapshot.json",
    "privacy-report": "privacy-report.json",
    "render-manifest": "render-manifest.json",
}
PROFILE_ROLES = {
    "title_zh",
    "title_en",
    "front_heading",
    "heading_1",
    "heading_2",
    "heading_3",
    "body",
    "abstract_zh",
    "abstract_en",
    "keywords",
    "figure_caption",
    "table_caption",
    "source_note",
    "table_body",
    "reference",
    "appendix_heading",
}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / CONTRACTS[name]).read_text(encoding="utf-8"))


def refresh_id(report: dict, id_field: str) -> None:
    report[id_field] = stable_id(
        {key: value for key, value in report.items() if key != id_field}
    )


@pytest.mark.parametrize("contract_name", CONTRACTS)
def test_valid_contract_fixtures(contract_name: str) -> None:
    validate_contract(contract_name, fixture(contract_name))


def test_format_profile_fixture_covers_approved_contract() -> None:
    profile = fixture("format-profile")

    assert set(profile) == {
        "profile",
        "metadata",
        "page",
        "styles",
        "role_detection",
        "numbering",
        "front_matter",
        "fields",
        "headers_footers",
        "figures",
        "tables",
        "references",
        "privacy",
    }
    assert set(profile["styles"]) == PROFILE_ROLES
    assert set(profile["role_detection"]["text_patterns"]) == PROFILE_ROLES
    assert set(profile["role_detection"]["position_constraints"]) == PROFILE_ROLES


def test_contract_error_includes_json_path() -> None:
    profile = fixture("format-profile")
    del profile["role_detection"]["text_patterns"]["heading_1"][0]["pattern"]

    with pytest.raises(
        ContractError,
        match=r"\$\.role_detection\.text_patterns\.heading_1\[0\]",
    ):
        validate_contract("format-profile", profile)


def object_paths(value: object, path: tuple[str | int, ...] = ()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, (*path, index))


def value_at_path(value: object, path: tuple[str | int, ...]) -> object:
    current = value
    for part in path:
        current = current[part]  # type: ignore[index]
    return current


def numeric_paths(value: object, path: tuple[str | int, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from numeric_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from numeric_paths(child, (*path, index))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path


PROFILE_NUMERIC_PATHS = tuple(numeric_paths(fixture("format-profile")))


@pytest.mark.parametrize("contract_name", CONTRACTS)
def test_unknown_keys_are_rejected_at_every_object_path(contract_name: str) -> None:
    allowed_maps = {
        ("privacy-report", ("summary",)),
    }
    document = fixture(contract_name)

    for path in object_paths(document):
        if (contract_name, path) in allowed_maps:
            continue
        mutated = copy.deepcopy(document)
        target = value_at_path(mutated, path)
        assert isinstance(target, dict)
        target["unknown_contract_key"] = True

        with pytest.raises(
            ContractError,
            match=r"unknown_contract_key",
        ):
            validate_contract(contract_name, mutated)


@pytest.mark.parametrize("contract_name,collection", [("audit", "findings"), ("transformation-result", "changes")])
@pytest.mark.parametrize("field", ["before", "after"])
def test_before_and_after_are_required_even_when_null(
    contract_name: str, collection: str, field: str
) -> None:
    report = fixture(contract_name)
    del report[collection][0][field]

    with pytest.raises(ContractError, match=field):
        validate_contract(contract_name, report)


def test_canonical_json_is_nfc_utf8_sorted_compact_and_newline_terminated() -> None:
    value = {"z": "e\u0301", "汉字": ["cafe\u0301"], "a": 1}

    assert canonical_json(value) == '{"a":1,"z":"é","汉字":["café"]}\n'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1e20, "100000000000000000000"),
        (1e-7, "1e-7"),
        (-0.0, "0"),
        (2.0, "2"),
        (1e30, "1e+30"),
        (1e-6, "0.000001"),
    ],
)
def test_canonical_json_uses_jcs_number_serialization(
    value: float, expected: str
) -> None:
    assert canonical_json(value) == f"{expected}\n"


@pytest.mark.parametrize(
    ("ieee_754", "expected"),
    [
        ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"),
        ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"),
        ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"),
        ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"),
        ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"),
        ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"),
        ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
        ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"),
        ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"),
        ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"),
        ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ],
)
def test_canonical_json_matches_rfc_8785_appendix_b_boundaries(
    ieee_754: str, expected: str
) -> None:
    value = struct.unpack(">d", bytes.fromhex(ieee_754))[0]

    assert canonical_json(value) == f"{expected}\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2**53, "9007199254740992"),
        (-(2**53), "-9007199254740992"),
        (2**68, "295147905179352830000"),
    ],
)
def test_canonical_json_accepts_exactly_representable_binary64_integers(
    value: int, expected: str
) -> None:
    assert canonical_json(value) == f"{expected}\n"


@pytest.mark.parametrize("value", [2**53 + 1, -(2**53 + 1), 2**68 + 1])
def test_canonical_json_rejects_integers_not_exactly_representable_as_binary64(
    value: int,
) -> None:
    with pytest.raises(
        ContractError,
        match="not exactly representable as an IEEE-754 binary64",
    ):
        canonical_json(value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises((ContractError, ValueError), match="finite|compliant"):
        canonical_json({"value": value})


def test_stable_ids_use_jcs_number_serialization() -> None:
    expected = hashlib.sha256(b'{"value":100000000000000000000}\n').hexdigest()[:16]

    assert stable_id({"value": 1e20}) == expected


@pytest.mark.parametrize(
    "path",
    PROFILE_NUMERIC_PATHS,
    ids=lambda path: ".".join(map(str, path)),
)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_format_profile_rejects_non_finite_float_at_every_numeric_path(
    path: tuple[str | int, ...], value: float
) -> None:
    profile = fixture("format-profile")
    parent = value_at_path(profile, path[:-1])
    parent[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ContractError, match=rf"{re.escape(str(path[-1]))}.*finite"):
        validate_contract("format-profile", profile)


@pytest.mark.parametrize("contract_name", CONTRACTS)
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_every_contract_rejects_nested_non_finite_float(
    contract_name: str, value: float
) -> None:
    document = fixture(contract_name)
    document["non_finite_probe"] = {"nested": [value]}

    with pytest.raises(ContractError, match=r"non_finite_probe.*nested.*finite"):
        validate_contract(contract_name, document)


def test_format_profile_rejects_non_positive_or_infeasible_geometry() -> None:
    profile = fixture("format-profile")
    profile["page"]["body"]["left_mm"] = 0
    with pytest.raises(ContractError, match=r"margin|positive"):
        validate_contract("format-profile", profile)

    profile = fixture("format-profile")
    profile["page"]["body"]["left_mm"] = 105
    profile["page"]["body"]["right_mm"] = 105
    with pytest.raises(ContractError, match=r"content width|margins"):
        validate_contract("format-profile", profile)


def test_format_profile_rejects_reversed_toc_levels() -> None:
    profile = fixture("format-profile")
    profile["fields"]["toc"]["levels"] = {"min": 4, "max": 3}

    with pytest.raises(ContractError, match=r"TOC|min.*max"):
        validate_contract("format-profile", profile)


def test_format_profile_rejects_reversed_position_range() -> None:
    profile = fixture("format-profile")
    constraint = profile["role_detection"]["position_constraints"]["heading_1"][0]
    constraint["min_index"] = 5
    constraint["max_index"] = 4

    with pytest.raises(ContractError, match=r"min_index.*max_index"):
        validate_contract("format-profile", profile)


@pytest.mark.parametrize(
    ("collection_path", "pattern_key"),
    [
        (("role_detection", "text_patterns", "heading_1"), "pattern"),
        (("privacy", "generic_patterns"), "regex"),
    ],
)
def test_format_profile_compiles_all_configured_regexes(
    collection_path: tuple[str, ...], pattern_key: str
) -> None:
    profile = fixture("format-profile")
    collection = value_at_path(profile, collection_path)
    assert isinstance(collection, list)
    collection[0][pattern_key] = "^($" if pattern_key == "pattern" else "("

    with pytest.raises(ContractError, match=r"regular expression|regex"):
        validate_contract("format-profile", profile)


def test_format_profile_compiles_unresolved_placeholder_regexes() -> None:
    profile = fixture("format-profile")
    profile["privacy"]["unresolved_placeholder_patterns"][0] = "("

    with pytest.raises(ContractError, match=r"regular expression|regex"):
        validate_contract("format-profile", profile)


def test_format_profile_rejects_incompatible_regex_flags() -> None:
    profile = fixture("format-profile")
    pattern = profile["role_detection"]["text_patterns"]["heading_1"][0]
    pattern["flags"] = ["ascii", "unicode"]

    with pytest.raises(ContractError, match=r"incompatible|flags"):
        validate_contract("format-profile", profile)


@pytest.mark.parametrize(
    "pattern",
    [
        "第.+章$",
        "^第.+章",
        "第.+章",
        r"^第.+章\$",
    ],
)
def test_format_profile_rejects_role_detection_patterns_without_whole_string_anchors(
    pattern: str,
) -> None:
    profile = fixture("format-profile")
    profile["role_detection"]["text_patterns"]["heading_1"][0]["pattern"] = pattern

    with pytest.raises(ContractError, match=r"start with \^ and end with an unescaped \$"):
        validate_contract("format-profile", profile)


def test_format_profile_rejects_multiline_role_detection_patterns() -> None:
    profile = fixture("format-profile")
    pattern = profile["role_detection"]["text_patterns"]["heading_1"][0]
    pattern["pattern"] = "^第.+章$"
    pattern["flags"] = ["multiline"]

    with pytest.raises(ContractError, match=r"multiline|flags"):
        validate_contract("format-profile", profile)


def test_format_profile_rejects_duplicate_privacy_regex_flags() -> None:
    profile = fixture("format-profile")
    profile["privacy"]["generic_patterns"][0]["flags"] = "ii"

    with pytest.raises(ContractError, match=r"duplicate|flags"):
        validate_contract("format-profile", profile)


def test_digest_prefixes_extend_collisions_four_characters_at_a_time() -> None:
    digests = [
        "0123456789abcdefaaaa" + "0" * 44,
        "0123456789abcdefbbbb" + "1" * 44,
        "fedcba9876543210cccc" + "2" * 44,
    ]

    assert shortest_unique_digest_prefixes(digests) == [
        "0123456789abcdefaaaa",
        "0123456789abcdefbbbb",
        "fedcba9876543210",
    ]


def test_invalid_stable_id_is_rejected() -> None:
    audit = fixture("audit")
    audit["findings"][0]["finding_id"] = "0" * 16

    with pytest.raises(ContractError, match=r"finding_id"):
        validate_contract("audit", audit)


@pytest.mark.parametrize(
    "contract_name,collection",
    [("audit", "findings"), ("transformation-result", "changes"), ("privacy-report", "matches")],
)
def test_semantically_wrong_order_is_rejected(contract_name: str, collection: str) -> None:
    report = fixture(contract_name)
    report[collection].reverse()

    with pytest.raises(ContractError, match=r"order"):
        validate_contract(contract_name, report)


def test_collision_id_length_is_verified() -> None:
    audit = fixture("audit")
    audit["findings"][0]["finding_id"] += "0000"

    with pytest.raises(ContractError, match=r"collision|length|finding_id"):
        validate_contract("audit", audit)


@pytest.mark.parametrize(
    "contract_name,collection",
    [("audit", "findings"), ("transformation-result", "changes")],
)
def test_duplicate_collection_semantic_keys_are_rejected(
    contract_name: str, collection: str
) -> None:
    report = fixture(contract_name)
    report[collection].append(copy.deepcopy(report[collection][0]))

    with pytest.raises(ContractError, match=r"duplicate semantic key|full digest"):
        validate_contract(contract_name, report)


def test_privacy_contract_cannot_contain_private_matched_text() -> None:
    report = fixture("privacy-report")
    report["matches"][0]["matched_text"] = "private"

    with pytest.raises(ContractError, match=r"matched_text"):
        validate_contract("privacy-report", report)


def test_render_destinations_must_reference_existing_pages() -> None:
    manifest = fixture("render-manifest")
    manifest["named_destinations"][0]["page"] = 99

    with pytest.raises(ContractError, match=r"named_destinations"):
        validate_contract("render-manifest", manifest)


def test_render_font_manifest_hash_must_match_canonical_manifest() -> None:
    manifest = fixture("render-manifest")
    manifest["font_manifest_hash"] = "0" * 64

    with pytest.raises(ContractError, match=r"font_manifest_hash"):
        validate_contract("render-manifest", manifest)


def test_render_destination_coordinates_allow_page_boundaries() -> None:
    manifest = fixture("render-manifest")
    page = manifest["pages"][0]
    destination = manifest["named_destinations"][0]
    destination["x_pt"] = page["width_pt"]
    destination["y_pt"] = page["height_pt"]
    refresh_id(manifest, "render_id")

    validate_contract("render-manifest", manifest)


@pytest.mark.parametrize(
    "coordinate,dimension",
    [("x_pt", "width_pt"), ("y_pt", "height_pt")],
)
def test_render_destination_coordinates_must_lie_within_referenced_page(
    coordinate: str, dimension: str
) -> None:
    manifest = fixture("render-manifest")
    manifest["named_destinations"][0][coordinate] = (
        manifest["pages"][0][dimension] + 0.001
    )

    with pytest.raises(ContractError, match=rf"named_destinations.*{coordinate}"):
        validate_contract("render-manifest", manifest)


def test_schemas_load_from_installed_package_resources() -> None:
    schema_file = resources.files("thesis_format").joinpath(
        "schemas", "format-profile.schema.json"
    )

    assert schema_file.is_file()
    assert load_schema("format-profile")["$id"].endswith(
        "/format-profile.schema.json"
    )


def test_loaded_schemas_are_independent_values() -> None:
    schema = load_schema("audit")
    changed = copy.deepcopy(schema)
    changed["title"] = "changed"

    assert load_schema("audit")["title"] != changed["title"]
