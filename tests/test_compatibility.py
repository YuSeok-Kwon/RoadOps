from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from roadops.compatibility import profile_link_compatibility
from roadops.live import LiveFetchError, fetch_json_payload
from roadops.probe import SourceSpec


NOW = datetime(2026, 10, 26, 12, 15, tzinfo=ZoneInfo("Asia/Seoul"))


def _references():
    return [
        {"link_id": "4050000001"},
        {"link_id": "4050000002"},
        {"link_id": "4060000001"},
    ]


def _traffic_row(link_id: str, timestamp: str = "20261026120000"):
    return {
        "link_id": link_id,
        "prcn_dt": timestamp,
        "tfvl": "12",
        "sped": 45,
        "ocpy_rate": 15,
        "trvl_hh": 60,
    }


def test_compatible_fresh_snapshot_passes_all_gates():
    report = profile_link_compatibility(
        [_traffic_row("4050000001"), _traffic_row("4050000002")],
        _references(),
        source_id="traffic",
        expected_fields=("link_id", "prcn_dt", "tfvl", "sped", "ocpy_rate", "trvl_hh"),
        record_key_fields=("link_id", "prcn_dt"),
        timestamp_field="prcn_dt",
        freshness_max_minutes=30,
        now=NOW,
    )

    assert report["status"] == "pass"
    assert report["summary"]["matched_source_rows"] == 2
    assert report["summary"]["valid_id_exact_join_rate"] == 1.0
    assert report["freshness"]["latest_age_minutes"] == 15.0
    assert all(check["passed"] for check in report["checks"])


def test_profile_separates_invalid_unmatched_duplicate_missing_and_stale_rows():
    duplicate = _traffic_row("9999999999", "20211026120000")
    missing_speed = _traffic_row("4050000001", "20211026120000")
    missing_speed["sped"] = ""
    rows = [
        duplicate,
        dict(duplicate),
        _traffic_row("405000001", "bad-timestamp"),
        missing_speed,
    ]

    report = profile_link_compatibility(
        rows,
        _references(),
        source_id="traffic",
        expected_fields=("link_id", "prcn_dt", "sped"),
        record_key_fields=("link_id", "prcn_dt"),
        timestamp_field="prcn_dt",
        freshness_max_minutes=30,
        now=NOW,
    )

    assert report["status"] == "fail"
    assert report["summary"]["invalid_source_link_id_rows"] == 1
    assert report["summary"]["unmatched_valid_source_rows"] == 2
    assert report["summary"]["matched_source_rows"] == 1
    assert report["summary"]["duplicate_record_key_excess"] == 1
    assert report["issue_counts"]["missing_required_field:sped"] == 1
    assert report["issue_counts"]["invalid_source_timestamp"] == 1
    assert report["freshness"]["latest_age_minutes"] > 2_000_000
    assert "exact_link_join_rate" in report["failed_checks"]
    assert "source_freshness" in report["failed_checks"]


def test_empty_source_fails_without_dividing_by_zero():
    report = profile_link_compatibility(
        [],
        _references(),
        source_id="traffic",
        expected_fields=("link_id",),
    )

    assert report["status"] == "fail"
    assert report["summary"]["source_rows"] == 0
    assert report["summary"]["all_record_exact_join_rate"] is None


def test_future_timestamp_is_reported_separately():
    report = profile_link_compatibility(
        [_traffic_row("4050000001", "20261026123000")],
        _references(),
        source_id="traffic",
        timestamp_field="prcn_dt",
        now=NOW,
    )

    assert report["status"] == "fail"
    assert report["freshness"]["future_timestamp_rows"] == 1
    assert "source_timestamp_not_future" in report["failed_checks"]


def _http_spec() -> SourceSpec:
    return SourceSpec(
        source_id="traffic",
        name="Traffic",
        name_ko="교통",
        documentation_url="https://example.com/docs",
        kind="json_api",
        endpoint_url="http://api.example.com/traffic",
        download_url=None,
        authentication={"environment_variable": "TRAFFIC_KEY", "query_parameter": "code"},
        default_params={"type": "L"},
        runtime_params=None,
        join_key="link_id",
        coordinate_system=None,
        expected_fields=("link_id",),
        record_key=("link_id",),
        timestamp_field=None,
        source_timezone="Asia/Seoul",
        freshness_max_minutes=None,
    )


def test_live_fetch_blocks_plaintext_http_before_network_call():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"Info": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            fetch_json_payload(_http_spec(), api_key="secret", client=client)
        except LiveFetchError as exc:
            assert exc.reason == "insecure_transport_blocked"
        else:
            raise AssertionError("Plaintext HTTP should be blocked")

    assert calls == 0


def test_live_fetch_metadata_never_contains_api_key_when_explicitly_allowed():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["code"] == "secret"
        return httpx.Response(200, json={"Info": [{"link_id": "4050000001"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload, metadata = fetch_json_payload(
            _http_spec(),
            api_key="secret",
            allow_insecure_http=True,
            client=client,
        )

    assert payload["Info"][0]["link_id"] == "4050000001"
    assert "secret" not in str(metadata)
    assert metadata["transport"] == "http"
