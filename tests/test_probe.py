from __future__ import annotations

import json
from pathlib import Path

from roadops.probe import extract_records, load_source_specs, missing_expected_fields


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_source_registry_loads_source_definition(tmp_path):
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": "sample",
                "name": "Sample",
                "name_ko": "샘플",
                "documentation_url": "https://example.com/docs",
                "kind": "json_api",
                "expected_fields": ["link_id"],
            }
        ],
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    specs = load_source_specs(path)

    assert len(specs) == 1
    assert specs[0].source_id == "sample"
    assert specs[0].expected_fields == ("link_id",)


def test_project_registry_has_unique_expected_sources():
    specs = load_source_specs(PROJECT_ROOT / "config" / "data_sources.json")
    source_ids = [spec.source_id for spec in specs]

    assert len(source_ids) == 9
    assert len(source_ids) == len(set(source_ids))
    assert "jeju_cits_road_event" in source_ids
    assert "molit_standard_node_link" in source_ids
    assert "kma_ultra_short_forecast" in source_ids
    assert "taas_link_risk" in source_ids


def test_extract_records_supports_cits_envelope():
    payload = {"result": "success", "Info": [{"link_id": "4050000001"}]}
    assert extract_records(payload) == [{"link_id": "4050000001"}]


def test_extract_records_supports_kma_envelope():
    payload = {
        "response": {"body": {"items": {"item": [{"category": "RN1"}]}}}
    }
    assert extract_records(payload) == [{"category": "RN1"}]


def test_extract_records_supports_taas_envelope():
    payload = {"items": {"item": [{"anals_grd": "1"}]}}
    assert extract_records(payload) == [{"anals_grd": "1"}]


def test_missing_expected_fields_reports_schema_gap():
    records = [{"link_id": "4050000001", "latitude": 33.3}]
    assert missing_expected_fields(records, ["link_id", "latitude", "longitude"]) == [
        "longitude"
    ]
