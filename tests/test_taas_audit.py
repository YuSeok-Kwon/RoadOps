from __future__ import annotations

import json
from pathlib import Path

import httpx

from roadops.probe import SourceSpec
from roadops.taas_audit import (
    audit_taas_links,
    fetch_taas_link_risk,
    stratified_link_sample,
    taas_linestring_from_wkt,
)


def _spec() -> SourceSpec:
    return SourceSpec(
        source_id="taas_link_risk",
        name="TAAS",
        name_ko="TAAS",
        documentation_url="https://example.com/docs",
        kind="json_api",
        endpoint_url="https://example.com/taas",
        download_url=None,
        authentication={"environment_variable": "TAAS_API_KEY", "query_parameter": "authKey"},
        default_params={"vhctyCd": "01", "type": "json", "numOfRows": 10, "pageNo": 1},
        runtime_params=None,
        join_key="link geometry",
        coordinate_system="EPSG:4326",
        expected_fields=("index", "line_string", "anals_value", "anals_grd"),
        record_key=(),
        timestamp_field=None,
        source_timezone="Asia/Seoul",
        freshness_max_minutes=None,
    )


def _links() -> list[dict[str, str]]:
    rows = []
    index = 0
    for prefix in ("405", "406"):
        for road_rank in ("105", "106", "107"):
            for _ in range(3):
                index += 1
                longitude = 126.0 + index / 1000
                rows.append(
                    {
                        "link_id": f"{prefix}{index:07d}",
                        "road_rank": road_rank,
                        "road_name": f"road-{index}",
                        "geometry_wkt": (
                            f"LINESTRING ({longitude:.6f} 33.300000,"
                            f"{longitude + 0.0005:.6f} 33.300500)"
                        ),
                    }
                )
    return rows


def test_taas_linestring_uses_geometry_endpoints():
    result = taas_linestring_from_wkt(
        "LINESTRING (126.1 33.1,126.2 33.2,126.3 33.3)"
    )
    assert result == "LineString(126.10000000 33.10000000,126.30000000 33.30000000)"


def test_stratified_sample_is_deterministic_and_covers_every_stratum():
    first, profile = stratified_link_sample(_links(), sample_size=12, seed=42)
    second, _ = stratified_link_sample(_links(), sample_size=12, seed=42)

    assert [row["link_id"] for row in first] == [row["link_id"] for row in second]
    assert len(first) == 12
    assert len(profile["sample_strata"]) == 6
    assert all(count == 2 for count in profile["sample_strata"].values())


def test_fetch_uses_encoded_key_once_and_reuses_sanitized_cache(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["authKey"] == "raw+key/value="
        return httpx.Response(
            200,
            json={
                "resultCode": "00",
                "resultMsg": "NORMAL_CODE",
                "items": {
                    "item": [
                        {
                            "index": "1",
                            "line_string": "LINESTRING (...) ",
                            "anals_value": "0.4",
                            "anals_grd": "02",
                        }
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = fetch_taas_link_risk(
            _spec(),
            api_key="raw%2Bkey%2Fvalue%3D",
            link_id="4050000001",
            search_line_string="LineString(126.1 33.1,126.2 33.2)",
            cache_dir=tmp_path,
            client=client,
        )
        second = fetch_taas_link_risk(
            _spec(),
            api_key="raw%2Bkey%2Fvalue%3D",
            link_id="4050000001",
            search_line_string="LineString(126.1 33.1,126.2 33.2)",
            cache_dir=tmp_path,
            client=client,
        )

    assert first["status"] == "ok"
    assert first["fetch_source"] == "live"
    assert second["status"] == "ok"
    assert second["fetch_source"] == "cache"
    assert calls == 1
    assert "raw" not in "".join(path.read_text() for path in tmp_path.iterdir())


def test_fetch_classifies_provider_error_without_caching(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resultCode": "30",
                "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_taas_link_risk(
            _spec(),
            api_key="key",
            link_id="4050000001",
            search_line_string="LineString(126.1 33.1,126.2 33.2)",
            cache_dir=tmp_path,
            client=client,
        )

    assert result["status"] == "api_error"
    assert result["provider_result_code"] == "30"
    assert not list(tmp_path.iterdir())


def test_fetch_caches_query_specific_parameter_rejection(tmp_path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "resultCode": "10",
                "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = fetch_taas_link_risk(
            _spec(),
            api_key="key",
            link_id="4050000001",
            search_line_string="LineString(126.1 33.1,126.2 33.2)",
            cache_dir=tmp_path,
            client=client,
        )
        second = fetch_taas_link_risk(
            _spec(),
            api_key="key",
            link_id="4050000001",
            search_line_string="LineString(126.1 33.1,126.2 33.2)",
            cache_dir=tmp_path,
            client=client,
        )

    assert first["status"] == "api_error"
    assert second["status"] == "api_error"
    assert second["fetch_source"] == "cache"
    assert calls == 1


def test_audit_reports_coverage_segments_and_features(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        line = request.url.params["searchLineString"]
        if "126.00100000" in line:
            return httpx.Response(
                200,
                json={"resultCode": "00", "resultMsg": "NORMAL_CODE", "items": {}},
            )
        return httpx.Response(
            200,
            json={
                "resultCode": "00",
                "resultMsg": "NORMAL_CODE",
                "items": {
                    "item": [
                        {
                            "index": "1",
                            "line_string": line,
                            "anals_value": "0.5",
                            "anals_grd": "02",
                        }
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report, results, features = audit_taas_links(
            _links(),
            _spec(),
            api_key="key",
            sample_size=18,
            seed=42,
            cache_dir=tmp_path,
            request_delay_seconds=0,
            client=client,
        )

    assert len(results) == 18
    assert len(report["segment_breakdown"]) == 6
    assert report["summary"]["request_success_count"] == 18
    assert report["summary"]["record_covered_links"] == 17
    assert report["status_counts"] == {"no_data": 1, "ok": 17}
    assert len(features) == 17
    assert report["risk_distribution"]["grade_counts"] == {"02": 17}
    assert max(
        row["absolute_share_difference"] for row in report["sampling_balance"]
    ) == 0.0
    serialized = json.dumps(report)
    assert "authKey" not in serialized
    assert "key" not in serialized
