"""Audit air and sea gateway APIs without overstating passenger semantics."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


GATEWAY_SOURCE_ROLES = {
    "kac_realtime_flights": {
        "mode": "realtime",
        "evidence_role": "flight_operations",
        "passenger_semantics": "no_passenger_count",
        "safe_use": "arrival_schedule_delay_cancellation_proxy",
    },
    "kac_hourly_arrival_passengers": {
        "mode": "aggregate_current_or_recent",
        "evidence_role": "hourly_arrival_passenger_count",
        "passenger_semantics": "aggregate_count_candidate",
        "safe_use": "validate_returned_period_and_field_before_use",
    },
    "komsa_ferry_schedule": {
        "mode": "realtime_schedule",
        "evidence_role": "ferry_schedule_control_capacity",
        "passenger_semantics": "capacity_not_actual_passengers",
        "safe_use": "schedule_control_and_capacity_proxy_only",
    },
    "komsa_monthly_departure_statistics": {
        "mode": "historical_monthly",
        "evidence_role": "historical_transport_statistics",
        "passenger_semantics": "historical_aggregate_count",
        "safe_use": "historical_baseline_not_realtime_inflow",
    },
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _jeju_signal(record: Mapping[str, Any]) -> bool:
    return any(
        signal in _text(value).upper()
        for value in record.values()
        for signal in ("CJU", "제주", "JEJU")
    )


def _field_groups(fields: Iterable[str]) -> dict[str, list[str]]:
    passenger_tokens = (
        "passenger",
        "psngr",
        "psg",
        "trnsport",
        "transport",
        "people",
        "person",
        "승객",
        "여객",
        "운송인원",
    )
    capacity_tokens = (
        "capacity",
        "quota",
        "max_psn",
        "maxpsn",
        "정원",
    )
    time_tokens = (
        "time",
        "date",
        "ymd",
        "hour",
        "dt",
        "시각",
        "일자",
    )
    status_tokens = (
        "status",
        "remark",
        "cancel",
        "control",
        "reason",
        "sttus",
        "현황",
        "통제",
        "취소",
    )

    normalized = sorted(set(str(field) for field in fields))

    def matching(tokens: tuple[str, ...]) -> list[str]:
        return [
            field
            for field in normalized
            if any(token in field.lower() for token in tokens)
        ]

    return {
        "passenger_fields": matching(passenger_tokens),
        "capacity_fields": matching(capacity_tokens),
        "time_fields": matching(time_tokens),
        "status_fields": matching(status_tokens),
    }


def audit_gateway_source(
    source_id: str,
    *,
    records: Iterable[Mapping[str, Any]],
    fetch_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize access, schema, Jeju scope, and safe interpretation."""

    role = GATEWAY_SOURCE_ROLES[source_id]
    materialized = [dict(record) for record in records]
    fields = sorted(
        {
            str(field)
            for record in materialized[:20]
            for field in record.keys()
        }
    )
    groups = _field_groups(fields)
    jeju_rows = sum(_jeju_signal(record) for record in materialized)
    fetch_status = str(fetch_result.get("status") or "unknown")
    blockers: list[str] = []

    if fetch_status != "response_received":
        blockers.append(f"fetch:{fetch_status}")
    provider_code = _text(fetch_result.get("provider_result_code"))
    if provider_code == "30":
        blockers.append("access:service_key_not_registered_for_api")
    elif provider_code == "20":
        blockers.append("access:permission_denied")
    elif provider_code == "12":
        blockers.append("contract:endpoint_unavailable_or_route_mismatch")
    elif provider_code == "10":
        blockers.append("contract:invalid_request_parameters")
    if fetch_status == "response_received" and not materialized:
        blockers.append("response:no_records")
    if materialized and jeju_rows == 0:
        blockers.append("scope:jeju_not_observed_in_sample")
    if source_id == "komsa_ferry_schedule":
        blockers.append("contract:vessel_name_seed_required")
    if (
        role["passenger_semantics"] == "aggregate_count_candidate"
        and not groups["passenger_fields"]
    ):
        blockers.append("schema:passenger_field_not_identified")

    readiness = "ready_for_feature_spike" if not blockers else "blocked_or_limited"
    return {
        "source_id": source_id,
        "fetch_status": fetch_status,
        "http_status": fetch_result.get("http_status"),
        "provider_result_code": fetch_result.get("provider_result_code"),
        "provider_result_message": fetch_result.get("provider_result_message"),
        "mode": role["mode"],
        "evidence_role": role["evidence_role"],
        "passenger_semantics": role["passenger_semantics"],
        "safe_use": role["safe_use"],
        "record_count": len(materialized),
        "jeju_signal_rows": jeju_rows,
        "observed_fields": fields,
        **groups,
        "readiness": readiness,
        "blockers": sorted(set(blockers)),
    }


def build_gateway_audit_report(
    source_results: Iterable[Mapping[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    """Build structural quality checks and readiness counts for G1."""

    results = [dict(result) for result in source_results]
    failed_checks: list[str] = []
    source_ids = [str(result.get("source_id")) for result in results]
    if set(source_ids) != set(GATEWAY_SOURCE_ROLES):
        failed_checks.append("source_set_mismatch")
    if len(source_ids) != len(set(source_ids)):
        failed_checks.append("duplicate_source_id")
    if any("serviceKey" in str(result) for result in results):
        failed_checks.append("credential_parameter_leak")

    readiness_counts = Counter(str(result["readiness"]) for result in results)
    access_counts = Counter(str(result["fetch_status"]) for result in results)
    status = "fail" if failed_checks else (
        "pass"
        if readiness_counts.get("blocked_or_limited", 0) == 0
        else "pass_with_limitations"
    )
    return {
        "schema_version": 1,
        "status": status,
        "generated_at": generated_at,
        "source_count": len(results),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "access_status_counts": dict(sorted(access_counts.items())),
        "sources": results,
        "failed_checks": failed_checks,
    }
