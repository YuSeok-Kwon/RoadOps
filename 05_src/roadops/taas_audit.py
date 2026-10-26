"""Stratified coverage audit for TAAS detailed-link road risk data.

TAAS 세부링크 도로위험지수와 제주 기준 도로망의 결합 품질을 표본 감사합니다.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import httpx

from roadops.probe import (
    SourceSpec,
    _normalize_api_key,
    _provider_error,
    extract_records,
)
from roadops.spatial import normalize_link_id, parse_point


TAAS_EXPECTED_FIELDS = ("index", "line_string", "anals_value", "anals_grd")
_COORDINATE_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class TaasAuditThresholds:
    """Predeclared quality gates for using TAAS as a scoring feature."""

    sample_completion_min: float = 1.0
    sample_link_uniqueness_min: float = 1.0
    request_success_min: float = 0.95
    record_coverage_min: float = 0.90
    schema_validity_min: float = 0.99
    required_field_completeness_min: float = 0.99


def taas_linestring_from_wkt(geometry_wkt: Any) -> str | None:
    """Reduce a WKT road geometry to the endpoint pair required by TAAS."""

    coordinates = _COORDINATE_PATTERN.findall(str(geometry_wkt or ""))
    if len(coordinates) < 2:
        return None
    start_lon, start_lat = map(float, coordinates[0])
    end_lon, end_lat = map(float, coordinates[-1])
    if parse_point(start_lat, start_lon) is None or parse_point(end_lat, end_lon) is None:
        return None
    if start_lon == end_lon and start_lat == end_lat:
        return None
    return (
        "LineString("
        f"{start_lon:.8f} {start_lat:.8f},"
        f"{end_lon:.8f} {end_lat:.8f}"
        ")"
    )


def _stratum(row: Mapping[str, Any]) -> tuple[str, str]:
    link_id = str(row["link_id"])
    road_rank = str(row.get("road_rank") or "missing").strip()
    return link_id[:3], road_rank


def _proportional_allocation(
    group_sizes: Mapping[tuple[str, str], int], sample_size: int
) -> dict[tuple[str, str], int]:
    groups = sorted(group_sizes)
    if sample_size >= sum(group_sizes.values()):
        return dict(group_sizes)
    if sample_size < len(groups):
        ranked = sorted(groups, key=lambda key: (-group_sizes[key], key))
        return {key: int(key in ranked[:sample_size]) for key in groups}

    allocation = {key: 1 for key in groups}
    remaining = sample_size - len(groups)
    capacities = {key: group_sizes[key] - 1 for key in groups}
    capacity_total = sum(capacities.values())
    quotas = {
        key: (remaining * capacities[key] / capacity_total if capacity_total else 0.0)
        for key in groups
    }
    for key in groups:
        allocation[key] += min(capacities[key], int(quotas[key]))

    undistributed = sample_size - sum(allocation.values())
    remainder_order = sorted(
        groups,
        key=lambda key: (-(quotas[key] - int(quotas[key])), key),
    )
    for key in remainder_order:
        if undistributed == 0:
            break
        if allocation[key] < group_sizes[key]:
            allocation[key] += 1
            undistributed -= 1
    return allocation


def stratified_link_sample(
    link_rows: Iterable[Mapping[str, Any]],
    *,
    sample_size: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a deterministic proportional sample by link prefix and road rank."""

    if sample_size <= 0:
        raise ValueError("sample_size must be positive")

    source_rows = list(link_rows)
    unique_eligible: dict[str, dict[str, Any]] = {}
    invalid_link_ids = 0
    invalid_geometries = 0
    duplicate_link_rows = 0
    for raw_row in source_rows:
        row = {str(key).strip().lower(): value for key, value in raw_row.items()}
        link_id = normalize_link_id(row.get("link_id"))
        if link_id is None:
            invalid_link_ids += 1
            continue
        search_line_string = taas_linestring_from_wkt(row.get("geometry_wkt"))
        if search_line_string is None:
            invalid_geometries += 1
            continue
        if link_id in unique_eligible:
            duplicate_link_rows += 1
            continue
        row["link_id"] = link_id
        row["administrative_prefix"] = link_id[:3]
        row["search_line_string"] = search_line_string
        unique_eligible[link_id] = row

    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in unique_eligible.values():
        groups[_stratum(row)].append(row)
    target_size = min(sample_size, len(unique_eligible))
    allocation = _proportional_allocation(
        {key: len(rows) for key, rows in groups.items()}, target_size
    )

    selected: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda row: row["link_id"])
        group_random = random.Random(f"{seed}:{key[0]}:{key[1]}")
        selected.extend(group_random.sample(ordered, allocation[key]))
    random.Random(seed).shuffle(selected)

    population_strata = {
        f"{key[0]}|{key[1]}": len(rows) for key, rows in sorted(groups.items())
    }
    sample_strata = Counter(
        f"{row['administrative_prefix']}|{row.get('road_rank') or 'missing'}"
        for row in selected
    )
    profile = {
        "source_rows": len(source_rows),
        "eligible_unique_links": len(unique_eligible),
        "invalid_link_id_rows": invalid_link_ids,
        "invalid_geometry_rows": invalid_geometries,
        "duplicate_link_rows": duplicate_link_rows,
        "requested_sample_size": sample_size,
        "selected_sample_size": len(selected),
        "sampling_seed": seed,
        "strata_fields": ["administrative_prefix", "road_rank"],
        "population_strata": population_strata,
        "sample_strata": dict(sorted(sample_strata.items())),
    }
    return selected, profile


def _cache_path(
    cache_dir: Path, endpoint_url: str, search_line_string: str, vehicle_type: str
) -> Path:
    fingerprint = hashlib.sha256(
        f"{endpoint_url}|{vehicle_type}|{search_line_string}".encode("utf-8")
    ).hexdigest()
    return cache_dir / f"{fingerprint}.json"


def _numeric(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _load_cached_payload(path: Path) -> tuple[Mapping[str, Any], dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    payload = cached.get("payload") if isinstance(cached, Mapping) else None
    if not isinstance(payload, Mapping):
        return None
    return payload, {
        "fetch_source": "cache",
        "http_status": cached.get("http_status"),
        "fetched_at": cached.get("fetched_at"),
        "elapsed_ms": None,
    }


def _store_cached_payload(
    path: Path,
    *,
    endpoint_url: str,
    search_line_string: str,
    vehicle_type: str,
    http_status: int,
    fetched_at: str,
    payload: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cache_record = {
        "schema_version": 1,
        "endpoint_url": endpoint_url,
        "search_line_string": search_line_string,
        "vehicle_type": vehicle_type,
        "http_status": http_status,
        "fetched_at": fetched_at,
        "payload": payload,
    }
    path.write_text(
        json.dumps(cache_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_taas_link_risk(
    spec: SourceSpec,
    *,
    api_key: str,
    link_id: str,
    search_line_string: str,
    cache_dir: str | Path,
    refresh_cache: bool = False,
    timeout_seconds: float = 30.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch one TAAS result with sanitized errors and credential-free caching."""

    if spec.endpoint_url is None or spec.authentication is None:
        raise ValueError("TAAS endpoint and authentication must be configured")
    cache_root = Path(cache_dir)
    vehicle_type = str(spec.default_params.get("vhctyCd", "01"))
    cache_file = _cache_path(
        cache_root, spec.endpoint_url, search_line_string, vehicle_type
    )
    cached = None if refresh_cache else _load_cached_payload(cache_file)
    if cached is not None:
        payload, request_metadata = cached
    else:
        params = dict(spec.default_params)
        params["searchLineString"] = search_line_string
        params[spec.authentication["query_parameter"]] = _normalize_api_key(api_key)
        owns_client = client is None
        http_client = client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "Jeju-RoadOps-TAAS-Audit/0.1"},
        )
        started = time.monotonic()
        try:
            try:
                response = http_client.get(spec.endpoint_url, params=params)
            except httpx.HTTPError as exc:
                return {
                    "link_id": link_id,
                    "status": "network_error",
                    "error_type": type(exc).__name__,
                    "fetch_source": "live",
                    "http_status": None,
                    "record_count": 0,
                    "complete_record_count": 0,
                    "records": [],
                }
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            if not response.is_success:
                return {
                    "link_id": link_id,
                    "status": "http_error",
                    "fetch_source": "live",
                    "http_status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "record_count": 0,
                    "complete_record_count": 0,
                    "records": [],
                }
            try:
                payload = response.json()
            except json.JSONDecodeError:
                return {
                    "link_id": link_id,
                    "status": "non_json_response",
                    "fetch_source": "live",
                    "http_status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "record_count": 0,
                    "complete_record_count": 0,
                    "records": [],
                }
            if not isinstance(payload, Mapping):
                return {
                    "link_id": link_id,
                    "status": "invalid_response_shape",
                    "fetch_source": "live",
                    "http_status": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "record_count": 0,
                    "complete_record_count": 0,
                    "records": [],
                }
            fetched_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            request_metadata = {
                "fetch_source": "live",
                "http_status": response.status_code,
                "fetched_at": fetched_at,
                "elapsed_ms": elapsed_ms,
            }
        finally:
            if owns_client:
                http_client.close()

        provider_error = _provider_error(payload)
        if provider_error is None or provider_error.get("provider_result_code") == "10":
            _store_cached_payload(
                cache_file,
                endpoint_url=spec.endpoint_url,
                search_line_string=search_line_string,
                vehicle_type=vehicle_type,
                http_status=request_metadata["http_status"],
                fetched_at=request_metadata["fetched_at"],
                payload=payload,
            )

    error = _provider_error(payload)
    if error is not None:
        return {
            "link_id": link_id,
            "status": "api_error",
            **request_metadata,
            **error,
            "record_count": 0,
            "complete_record_count": 0,
            "records": [],
        }

    records = [dict(record) for record in extract_records(payload)]
    if not records:
        return {
            "link_id": link_id,
            "status": "no_data",
            **request_metadata,
            "record_count": 0,
            "complete_record_count": 0,
            "missing_expected_fields": list(TAAS_EXPECTED_FIELDS),
            "records": [],
        }

    complete_records = 0
    missing_fields: set[str] = set()
    invalid_risk_values = 0
    for record in records:
        record_missing = {
            field
            for field in TAAS_EXPECTED_FIELDS
            if record.get(field) is None or str(record.get(field)).strip() == ""
        }
        missing_fields.update(record_missing)
        if not record_missing:
            complete_records += 1
        if _numeric(record.get("anals_value")) is None:
            invalid_risk_values += 1

    status = (
        "ok"
        if complete_records == len(records) and invalid_risk_values == 0
        else "schema_invalid"
    )
    first_record = records[0]
    return {
        "link_id": link_id,
        "status": status,
        **request_metadata,
        "record_count": len(records),
        "complete_record_count": complete_records,
        "missing_expected_fields": sorted(missing_fields),
        "invalid_risk_value_records": invalid_risk_values,
        "risk_value": _numeric(first_record.get("anals_value")),
        "risk_grade": first_record.get("anals_grd"),
        "records": records,
    }


def _rate_check(
    *,
    check_id: str,
    dimension: str,
    severity: str,
    numerator: int,
    denominator: int,
    minimum_rate: float,
    meaning: str,
) -> dict[str, Any]:
    rate = numerator / denominator if denominator else None
    return {
        "check_id": check_id,
        "dimension": dimension,
        "severity": severity,
        "numerator": numerator,
        "denominator": denominator,
        "observed_rate": round(rate, 6) if rate is not None else None,
        "minimum_rate": minimum_rate,
        "passed": rate is not None and rate >= minimum_rate,
        "meaning": meaning,
    }


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def build_taas_audit_report(
    results: Iterable[Mapping[str, Any]],
    *,
    sampling_profile: Mapping[str, Any],
    thresholds: TaasAuditThresholds | None = None,
) -> dict[str, Any]:
    """Summarize completeness, schema, coverage, and segment-level risks."""

    rules = thresholds or TaasAuditThresholds()
    rows = [dict(result) for result in results]
    sample_count = len(rows)
    requested_count = int(sampling_profile["requested_sample_size"])
    unique_link_count = len({str(row.get("link_id")) for row in rows})
    status_counts = Counter(str(row.get("status")) for row in rows)
    request_success_statuses = {"ok", "no_data", "schema_invalid"}
    request_success_count = sum(
        count for status, count in status_counts.items() if status in request_success_statuses
    )
    record_covered_count = status_counts["ok"] + status_counts["schema_invalid"]
    schema_valid_count = status_counts["ok"]
    returned_record_count = sum(int(row.get("record_count") or 0) for row in rows)
    complete_record_count = sum(
        int(row.get("complete_record_count") or 0) for row in rows
    )

    checks = [
        _rate_check(
            check_id="sample_completion",
            dimension="volume",
            severity="high",
            numerator=sample_count,
            denominator=requested_count,
            minimum_rate=rules.sample_completion_min,
            meaning="The requested stratified sample was fully evaluated.",
        ),
        _rate_check(
            check_id="sample_link_uniqueness",
            dimension="uniqueness",
            severity="high",
            numerator=unique_link_count,
            denominator=sample_count,
            minimum_rate=rules.sample_link_uniqueness_min,
            meaning="Each sampled reference link appears once.",
        ),
        _rate_check(
            check_id="request_success",
            dimension="availability",
            severity="critical",
            numerator=request_success_count,
            denominator=sample_count,
            minimum_rate=rules.request_success_min,
            meaning="TAAS returned a normal provider response for the sampled request.",
        ),
        _rate_check(
            check_id="record_coverage",
            dimension="completeness",
            severity="high",
            numerator=record_covered_count,
            denominator=sample_count,
            minimum_rate=rules.record_coverage_min,
            meaning="A TAAS risk record was returned for the sampled reference link.",
        ),
        _rate_check(
            check_id="schema_validity",
            dimension="validity",
            severity="critical",
            numerator=schema_valid_count,
            denominator=record_covered_count,
            minimum_rate=rules.schema_validity_min,
            meaning="Returned link responses satisfied the required TAAS schema.",
        ),
        _rate_check(
            check_id="required_field_completeness",
            dimension="completeness",
            severity="critical",
            numerator=complete_record_count,
            denominator=returned_record_count,
            minimum_rate=rules.required_field_completeness_min,
            meaning="Returned TAAS records populated every required scoring field.",
        ),
    ]

    segment_rows: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        segment_rows[
            (
                str(row.get("administrative_prefix") or "unknown"),
                str(row.get("road_rank") or "missing"),
            )
        ].append(row)
    segment_breakdown: list[dict[str, Any]] = []
    for (prefix, road_rank), segment in sorted(segment_rows.items()):
        covered = sum(row.get("status") in {"ok", "schema_invalid"} for row in segment)
        successful = sum(row.get("status") in request_success_statuses for row in segment)
        segment_breakdown.append(
            {
                "administrative_prefix": prefix,
                "road_rank": road_rank,
                "sample_count": len(segment),
                "request_success_count": successful,
                "request_success_rate": round(successful / len(segment), 6),
                "record_covered_count": covered,
                "record_coverage_rate": round(covered / len(segment), 6),
                "no_data_count": sum(row.get("status") == "no_data" for row in segment),
                "error_count": sum(
                    row.get("status") not in request_success_statuses for row in segment
                ),
            }
        )

    risk_values = [
        float(row["risk_value"])
        for row in rows
        if row.get("risk_value") is not None
    ]
    risk_grades = Counter(
        str(row["risk_grade"])
        for row in rows
        if row.get("risk_grade") is not None
    )
    provider_errors = Counter(
        (
            str(row.get("provider_result_code") or "unknown"),
            str(row.get("provider_result_message") or "unknown"),
        )
        for row in rows
        if row.get("status") == "api_error"
    )
    grade_values: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("risk_grade") is not None and row.get("risk_value") is not None:
            grade_values[str(row["risk_grade"])].append(float(row["risk_value"]))

    population_strata = sampling_profile.get("population_strata", {})
    sample_strata = sampling_profile.get("sample_strata", {})
    eligible_population = int(sampling_profile.get("eligible_unique_links") or 0)
    sampling_balance: list[dict[str, Any]] = []
    for stratum, population_count in sorted(population_strata.items()):
        sampled_count = int(sample_strata.get(stratum, 0))
        population_share = population_count / eligible_population if eligible_population else 0
        sample_share = sampled_count / sample_count if sample_count else 0
        sampling_balance.append(
            {
                "stratum": stratum,
                "population_count": population_count,
                "population_share": round(population_share, 6),
                "sample_count": sampled_count,
                "sample_share": round(sample_share, 6),
                "absolute_share_difference": round(
                    abs(sample_share - population_share), 6
                ),
            }
        )
    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    issue_samples = [
        {
            "link_id": row.get("link_id"),
            "status": row.get("status"),
            "administrative_prefix": row.get("administrative_prefix"),
            "road_rank": row.get("road_rank"),
            "provider_result_code": row.get("provider_result_code"),
            "provider_result_message": row.get("provider_result_message"),
            "missing_expected_fields": row.get("missing_expected_fields"),
        }
        for row in rows
        if row.get("status") != "ok"
    ][:25]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "dataset": "TAAS detailed-link road risk joined to sampled Jeju reference links",
        "grain": "one audit request per sampled national standard road link",
        "status": "pass" if not failed_checks else "fail",
        "sampling": dict(sampling_profile),
        "summary": {
            "sampled_links": sample_count,
            "unique_sampled_links": unique_link_count,
            "request_success_count": request_success_count,
            "request_success_rate": round(request_success_count / sample_count, 6)
            if sample_count
            else None,
            "record_covered_links": record_covered_count,
            "record_coverage_rate": round(record_covered_count / sample_count, 6)
            if sample_count
            else None,
            "returned_records": returned_record_count,
            "complete_records": complete_record_count,
            "live_request_count": sum(row.get("fetch_source") == "live" for row in rows),
            "cache_hit_count": sum(row.get("fetch_source") == "cache" for row in rows),
            "multi_record_response_count": sum(
                int(row.get("record_count") or 0) > 1 for row in rows
            ),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "provider_error_counts": {
            f"{code}|{message}": count
            for (code, message), count in sorted(provider_errors.items())
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "sampling_balance": sampling_balance,
        "segment_breakdown": segment_breakdown,
        "risk_distribution": {
            "value_count": len(risk_values),
            "zero_value_count": sum(value == 0 for value in risk_values),
            "zero_value_rate": round(
                sum(value == 0 for value in risk_values) / len(risk_values), 6
            )
            if risk_values
            else None,
            "minimum": min(risk_values) if risk_values else None,
            "p25": _quantile(risk_values, 0.25),
            "median": median(risk_values) if risk_values else None,
            "mean": fmean(risk_values) if risk_values else None,
            "p75": _quantile(risk_values, 0.75),
            "maximum": max(risk_values) if risk_values else None,
            "grade_counts": dict(sorted(risk_grades.items())),
            "grade_value_summary": {
                grade: {
                    "count": len(values),
                    "minimum": min(values),
                    "median": median(values),
                    "maximum": max(values),
                }
                for grade, values in sorted(grade_values.items())
            },
        },
        "issue_samples": issue_samples,
        "assumptions": [
            "The first three digits of the national link ID are used only as a sampling segment, not as a verified administrative-area label.",
            "TAAS coverage is measured for the sampled link endpoint LineString queries and is not yet a census of all Jeju links.",
            "TAAS risk is treated as structural prior information, not a real-time incident probability.",
        ],
    }


def audit_taas_links(
    link_rows: Iterable[Mapping[str, Any]],
    spec: SourceSpec,
    *,
    api_key: str,
    sample_size: int,
    seed: int,
    cache_dir: str | Path,
    request_delay_seconds: float = 0.1,
    refresh_cache: bool = False,
    timeout_seconds: float = 30.0,
    thresholds: TaasAuditThresholds | None = None,
    client: httpx.Client | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the sampled TAAS audit and return report, link results, and features."""

    if request_delay_seconds < 0:
        raise ValueError("request_delay_seconds must be non-negative")
    sample, sampling_profile = stratified_link_sample(
        link_rows, sample_size=sample_size, seed=seed
    )
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": "Jeju-RoadOps-TAAS-Audit/0.1"},
    )
    results: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    try:
        for index, link in enumerate(sample):
            result = fetch_taas_link_risk(
                spec,
                api_key=api_key,
                link_id=link["link_id"],
                search_line_string=link["search_line_string"],
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                timeout_seconds=timeout_seconds,
                client=http_client,
            )
            result.update(
                {
                    "administrative_prefix": link["administrative_prefix"],
                    "road_rank": link.get("road_rank") or "missing",
                    "road_name": link.get("road_name") or "",
                    "lane_count": link.get("lane_count") or "",
                    "maximum_speed_limit": link.get("maximum_speed_limit") or "",
                    "road_type": link.get("road_type") or "",
                    "search_line_string": link["search_line_string"],
                }
            )
            records = result.pop("records", [])
            results.append(result)
            for record_index, record in enumerate(records):
                features.append(
                    {
                        "link_id": link["link_id"],
                        "source_record_index": record_index,
                        "administrative_prefix": link["administrative_prefix"],
                        "road_rank": link.get("road_rank") or "missing",
                        "road_name": link.get("road_name") or "",
                        "structural_risk_value": record.get("anals_value"),
                        "structural_risk_grade": record.get("anals_grd"),
                        "taas_index": record.get("index"),
                        "taas_line_string": record.get("line_string"),
                        "source_id": spec.source_id,
                        "source_fetched_at": result.get("fetched_at"),
                        "sample_only": True,
                    }
                )
            if (
                request_delay_seconds
                and result.get("fetch_source") == "live"
                and index < len(sample) - 1
            ):
                time.sleep(request_delay_seconds)
    finally:
        if owns_client:
            http_client.close()

    report = build_taas_audit_report(
        results, sampling_profile=sampling_profile, thresholds=thresholds
    )
    return report, results, features


def dataclass_thresholds() -> dict[str, Any]:
    """Return default thresholds in a JSON-friendly form."""

    return asdict(TaasAuditThresholds())
