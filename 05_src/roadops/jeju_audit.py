"""Reusable quality audit for authenticated Jeju C-ITS and ITS payloads.

인증된 제주 C-ITS·ITS 응답의 키 유효성·실시간성·결합 품질을 감사합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from roadops.compatibility import profile_link_compatibility
from roadops.probe import SourceSpec, _provider_error, extract_records


JEJU_LIVE_AUDIT_SOURCE_IDS = (
    "jeju_cits_road_event",
    "jeju_cits_road_close",
    "jeju_cits_road_work",
    "jeju_cits_road_weather",
    "jeju_its_realtime_traffic",
    "jeju_its_hourly_traffic",
    "jeju_its_daily_traffic",
)


def _period_match_status(
    *,
    request_params: Mapping[str, Any],
    timestamp_field: str | None,
    rows: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    requested = str(request_params.get("statDt", "")).strip()
    if not requested or timestamp_field is None:
        return None
    matching = sum(
        str(row.get(timestamp_field, "")).strip().startswith(requested) for row in rows
    )
    return {
        "status": "requested_period_returned" if matching == len(rows) and rows else "mismatch",
        "requested_period": requested,
        "matching_rows": matching,
        "total_rows": len(rows),
    }


def audit_jeju_payload(
    spec: SourceSpec,
    payload: Mapping[str, Any],
    reference_link_rows: Iterable[Mapping[str, Any]],
    *,
    fetch_metadata: Mapping[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    """Audit one successful response without retaining credentials or raw payloads."""

    provider_error = _provider_error(payload)
    records = [dict(record) for record in extract_records(payload)]
    request_params = dict(fetch_metadata.get("request_params", {}))
    compatibility = profile_link_compatibility(
        records,
        reference_link_rows,
        source_id=spec.source_id,
        expected_fields=spec.expected_fields,
        record_key_fields=spec.record_key,
        timestamp_field=spec.timestamp_field,
        source_timezone=spec.source_timezone,
        freshness_max_minutes=spec.freshness_max_minutes,
        now=evaluated_at,
    )
    reported_count = payload.get("info_cnt")
    count_matches = (
        reported_count == len(records) if isinstance(reported_count, int) else None
    )

    period_match = _period_match_status(
        request_params=request_params,
        timestamp_field=spec.timestamp_field,
        rows=records,
    )
    if period_match is not None:
        timeliness = period_match
    elif spec.timestamp_field is None:
        timeliness = {
            "status": "not_verifiable",
            "reason": "source_has_no_timestamp_field",
        }
    else:
        freshness = compatibility["freshness"]
        age = freshness["latest_age_minutes"]
        threshold = freshness["freshness_max_minutes"]
        if age is None:
            freshness_status = "not_verifiable"
        elif threshold is None:
            freshness_status = "observed"
        else:
            freshness_status = "fresh" if age <= threshold else "stale"
        timeliness = {"status": freshness_status, **freshness}

    return {
        "source_id": spec.source_id,
        "name": spec.name,
        "name_ko": spec.name_ko,
        "authentication": {
            "status": "invalid" if provider_error is not None else "valid",
            "environment_variable": (
                spec.authentication.get("environment_variable")
                if spec.authentication
                else None
            ),
            "provider_result": payload.get("result"),
            "provider_error": provider_error,
        },
        "fetch": {
            key: value
            for key, value in fetch_metadata.items()
            if key not in {"source_id", "endpoint_url"}
        },
        "records": {
            "reported_count": reported_count,
            "extracted_count": len(records),
            "reported_count_matches": count_matches,
        },
        "timeliness": timeliness,
        "quality": compatibility,
    }


def build_jeju_audit_report(
    source_results: Iterable[Mapping[str, Any]],
    *,
    evaluated_at: datetime,
    failures: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Aggregate per-source checks into credential and timeliness conclusions."""

    results = [dict(result) for result in source_results]
    failed = [dict(failure) for failure in failures]
    credential_groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        environment_variable = result["authentication"].get("environment_variable")
        if environment_variable:
            credential_groups.setdefault(environment_variable, []).append(result)

    credential_checks: dict[str, dict[str, Any]] = {}
    for environment_variable, group in sorted(credential_groups.items()):
        valid_sources = [
            result["source_id"]
            for result in group
            if result["authentication"]["status"] == "valid"
        ]
        credential_checks[environment_variable] = {
            "status": "valid" if valid_sources else "not_validated",
            "validated_source_count": len(valid_sources),
            "validated_sources": valid_sources,
        }

    realtime = next(
        (
            result
            for result in results
            if result["source_id"] == "jeju_its_realtime_traffic"
        ),
        None,
    )
    realtime_status = realtime["timeliness"]["status"] if realtime else "not_checked"
    required_credentials_valid = all(
        credential_checks.get(name, {}).get("status") == "valid"
        for name in ("JEJU_CITS_API_KEY", "JEJU_ITS_API_KEY")
    )
    overall_status = (
        "pass_with_limitations"
        if required_credentials_valid and realtime_status == "fresh" and not failed
        else "fail"
    )
    return {
        "schema_version": 1,
        "dataset": "jeju_cits_its_live_api_audit",
        "grain": "one audit row per configured API endpoint",
        "evaluated_at": evaluated_at.isoformat(),
        "status": overall_status,
        "credential_checks": credential_checks,
        "realtime_traffic_status": realtime_status,
        "source_count": len(results),
        "failure_count": len(failed),
        "sources": results,
        "failures": failed,
        "limitations": [
            "The provider exposes the audited endpoints over plaintext HTTP.",
            "C-ITS event, closure, work, and road-weather records contain no observation timestamp, so their freshness cannot be measured from a single response.",
        ],
    }
