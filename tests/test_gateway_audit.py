from __future__ import annotations

from roadops.gateway_audit import (
    GATEWAY_SOURCE_ROLES,
    audit_gateway_source,
    build_gateway_audit_report,
)


def test_flight_operations_are_not_mislabeled_as_passenger_counts():
    result = audit_gateway_source(
        "kac_realtime_flights",
        records=[
            {
                "arrvCityCode": "CJU",
                "scheduledDateTime": "202611121800",
                "remark": "도착",
            }
        ],
        fetch_result={"status": "response_received", "http_status": 200},
    )

    assert result["passenger_semantics"] == "no_passenger_count"
    assert result["jeju_signal_rows"] == 1
    assert result["readiness"] == "ready_for_feature_spike"


def test_hourly_passenger_source_requires_an_observed_count_field():
    result = audit_gateway_source(
        "kac_hourly_arrival_passengers",
        records=[{"airport": "CJU", "date": "20261112", "hour": "18"}],
        fetch_result={"status": "response_received", "http_status": 200},
    )

    assert result["passenger_semantics"] == "aggregate_count_candidate"
    assert "schema:passenger_field_not_identified" in result["blockers"]
    assert result["readiness"] == "blocked_or_limited"


def test_ferry_capacity_is_kept_as_proxy_and_ship_seed_is_reported():
    result = audit_gateway_source(
        "komsa_ferry_schedule",
        records=[
            {
                "departurePort": "제주항",
                "passengerCapacity": 500,
                "departureTime": "1800",
            }
        ],
        fetch_result={"status": "response_received", "http_status": 200},
    )

    assert result["passenger_semantics"] == "capacity_not_actual_passengers"
    assert result["capacity_fields"] == ["passengerCapacity"]
    assert "contract:vessel_name_seed_required" in result["blockers"]


def test_gateway_report_preserves_access_limitations_without_structural_failure():
    results = []
    for source_id in GATEWAY_SOURCE_ROLES:
        results.append(
            audit_gateway_source(
                source_id,
                records=[],
                fetch_result={
                    "status": "fetch_failed",
                    "provider_result_code": "20",
                    "provider_result_message": "SERVICE_ACCESS_DENIED_ERROR",
                },
            )
        )

    report = build_gateway_audit_report(
        results,
        generated_at="2026-11-12T18:00:00+09:00",
    )

    assert report["status"] == "pass_with_limitations"
    assert report["source_count"] == 4
    assert report["readiness_counts"] == {"blocked_or_limited": 4}
    assert report["failed_checks"] == []
    assert all(
        "access:permission_denied" in source["blockers"]
        for source in report["sources"]
    )
