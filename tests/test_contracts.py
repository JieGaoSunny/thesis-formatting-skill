from __future__ import annotations

import copy
import json
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


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / CONTRACTS[name]).read_text(encoding="utf-8"))


def refresh_id(report: dict, id_field: str) -> None:
    report[id_field] = stable_id(
        {key: value for key, value in report.items() if key != id_field}
    )


@pytest.mark.parametrize("contract_name", CONTRACTS)
def test_valid_contract_fixtures(contract_name: str) -> None:
    validate_contract(contract_name, fixture(contract_name))


def test_contract_error_includes_json_path() -> None:
    profile = fixture("format-profile")
    del profile["role_detection"]["text_patterns"][0]["pattern"]

    with pytest.raises(ContractError, match=r"\$\.role_detection\.text_patterns\[0\]"):
        validate_contract("format-profile", profile)


def test_unknown_keys_are_rejected_recursively() -> None:
    profile = fixture("format-profile")
    profile["role_detection"]["text_patterns"][0]["unknown"] = True

    with pytest.raises(ContractError, match=r"unknown"):
        validate_contract("format-profile", profile)


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
