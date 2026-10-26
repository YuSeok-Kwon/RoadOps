from __future__ import annotations

import json
from pathlib import Path

import httpx

from roadops.probe import (
    _live_probe,
    extract_records,
    load_source_specs,
    missing_expected_fields,
)


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
    assert specs[0].record_key == ()
    assert specs[0].source_timezone == "Asia/Seoul"


def test_source_registry_loads_quality_contract(tmp_path):
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": "traffic",
                "name": "Traffic",
                "name_ko": "교통",
                "documentation_url": "https://example.com/docs",
                "kind": "json_api",
                "expected_fields": ["link_id", "observed_at"],
                "quality_contract": {
                    "record_key": ["link_id", "observed_at"],
                    "timestamp_field": "observed_at",
                    "source_timezone": "Asia/Seoul",
                    "freshness_max_minutes": 30,
                },
            }
        ],
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    spec = load_source_specs(path)[0]

    assert spec.record_key == ("link_id", "observed_at")
    assert spec.timestamp_field == "observed_at"
    assert spec.freshness_max_minutes == 30


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


def test_live_probe_blocks_plaintext_endpoint_before_reading_credentials(tmp_path):
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": "traffic",
                "name": "Traffic",
                "name_ko": "교통",
                "documentation_url": "https://example.com/docs",
                "endpoint_url": "http://api.example.com/traffic",
                "kind": "json_api",
                "authentication": {
                    "environment_variable": "UNSET_TEST_TRAFFIC_KEY",
                    "query_parameter": "code",
                },
            }
        ],
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    spec = load_source_specs(path)[0]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"Info": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _live_probe(client, spec)

    assert result["status"] == "insecure_transport_blocked"
    assert calls == 0


def test_live_probe_decodes_url_encoded_api_key(monkeypatch, tmp_path):
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": "taas",
                "name": "TAAS",
                "name_ko": "TAAS",
                "documentation_url": "https://example.com/docs",
                "endpoint_url": "https://example.com/taas",
                "kind": "json_api",
                "authentication": {
                    "environment_variable": "TEST_TAAS_KEY",
                    "query_parameter": "authKey",
                },
                "expected_fields": ["anals_grd"],
            }
        ],
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    spec = load_source_specs(path)[0]
    monkeypatch.setenv("TEST_TAAS_KEY", "raw%2Bkey%2Fvalue%3D")
    observed_key = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_key
        observed_key = request.url.params.get("authKey")
        return httpx.Response(
            200,
            json={
                "resultCode": "00",
                "resultMsg": "NORMAL_CODE",
                "items": {"item": [{"anals_grd": "01"}]},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _live_probe(client, spec)

    assert observed_key == "raw+key/value="
    assert result["status"] == "schema_valid"


def test_live_probe_reports_taas_error_inside_http_200(monkeypatch, tmp_path):
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": "taas",
                "name": "TAAS",
                "name_ko": "TAAS",
                "documentation_url": "https://example.com/docs",
                "endpoint_url": "https://example.com/taas",
                "kind": "json_api",
                "authentication": {
                    "environment_variable": "TEST_TAAS_KEY",
                    "query_parameter": "authKey",
                },
                "expected_fields": ["anals_grd"],
            }
        ],
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    spec = load_source_specs(path)[0]
    monkeypatch.setenv("TEST_TAAS_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resultCode": "30",
                "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _live_probe(client, spec)

    assert result["status"] == "api_error"
    assert result["http_status"] == 200
    assert result["provider_result_code"] == "30"
    assert result["provider_result_message"] == "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
    assert "missing_expected_fields" not in result
