from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.jeju_audit import audit_jeju_payload, build_jeju_audit_report
from roadops.probe import SourceSpec


NOW = datetime(2026, 10, 27, 9, 19, tzinfo=ZoneInfo("Asia/Seoul"))


def _spec(
    source_id: str,
    *,
    timestamp_field: str | None = None,
    freshness_max_minutes: float | None = None,
    runtime_params: str | None = None,
) -> SourceSpec:
    return SourceSpec(
        source_id=source_id,
        name=source_id,
        name_ko=source_id,
        documentation_url="https://example.com",
        kind="json_api",
        endpoint_url="http://api.example.com",
        download_url=None,
        authentication={
            "environment_variable": (
                "JEJU_CITS_API_KEY" if "cits" in source_id else "JEJU_ITS_API_KEY"
            ),
            "query_parameter": "code",
        },
        default_params={"type": "L"},
        runtime_params=runtime_params,
        join_key="link_id",
        coordinate_system=None,
        expected_fields=("link_id", timestamp_field) if timestamp_field else ("link_id",),
        record_key=("link_id", timestamp_field) if timestamp_field else ("link_id",),
        timestamp_field=timestamp_field,
        source_timezone="Asia/Seoul",
        freshness_max_minutes=freshness_max_minutes,
    )


def test_realtime_payload_validates_key_and_freshness():
    spec = _spec(
        "jeju_its_realtime_traffic",
        timestamp_field="prcn_dt",
        freshness_max_minutes=30,
    )
    payload = {
        "result": "success",
        "info_cnt": 1,
        "info": [{"link_id": "4050000001", "prcn_dt": "20261027091500"}],
    }

    result = audit_jeju_payload(
        spec,
        payload,
        [{"link_id": "4050000001"}],
        fetch_metadata={
            "http_status": 200,
            "transport": "http",
            "request_params": {"type": "L"},
        },
        evaluated_at=NOW,
    )

    assert result["authentication"]["status"] == "valid"
    assert result["records"]["reported_count_matches"] is True
    assert result["timeliness"]["status"] == "fresh"
    assert result["timeliness"]["latest_age_minutes"] == 4.0


def test_cits_without_timestamp_is_explicitly_not_verifiable():
    spec = _spec("jeju_cits_road_event")
    payload = {
        "result": "success",
        "info_cnt": 1,
        "info": [{"link_id": "4050000001"}],
    }

    result = audit_jeju_payload(
        spec,
        payload,
        [{"link_id": "4050000001"}],
        fetch_metadata={"http_status": 200, "transport": "http", "request_params": {}},
        evaluated_at=NOW,
    )

    assert result["authentication"]["status"] == "valid"
    assert result["timeliness"] == {
        "status": "not_verifiable",
        "reason": "source_has_no_timestamp_field",
    }


def test_statistics_must_return_the_requested_period():
    spec = _spec(
        "jeju_its_hourly_traffic",
        timestamp_field="stat_dt",
        runtime_params="jeju_previous_complete_hour",
    )
    payload = {
        "result": "success",
        "info_cnt": 1,
        "info": [{"link_id": "4050000001", "stat_dt": "20261027080000"}],
    }

    result = audit_jeju_payload(
        spec,
        payload,
        [{"link_id": "4050000001"}],
        fetch_metadata={
            "http_status": 200,
            "transport": "http",
            "request_params": {"type": "L", "statDt": "2026102708"},
        },
        evaluated_at=NOW,
    )

    assert result["timeliness"]["status"] == "requested_period_returned"
    assert result["timeliness"]["matching_rows"] == 1


def test_report_passes_with_documented_cits_freshness_limitation():
    cits = {
        "source_id": "jeju_cits_road_event",
        "authentication": {
            "status": "valid",
            "environment_variable": "JEJU_CITS_API_KEY",
        },
        "timeliness": {"status": "not_verifiable"},
    }
    its = {
        "source_id": "jeju_its_realtime_traffic",
        "authentication": {
            "status": "valid",
            "environment_variable": "JEJU_ITS_API_KEY",
        },
        "timeliness": {"status": "fresh"},
    }

    report = build_jeju_audit_report([cits, its], evaluated_at=NOW)

    assert report["status"] == "pass_with_limitations"
    assert report["credential_checks"]["JEJU_CITS_API_KEY"]["status"] == "valid"
    assert report["credential_checks"]["JEJU_ITS_API_KEY"]["status"] == "valid"
