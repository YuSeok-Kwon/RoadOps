"""Quality gates for dynamic road data joined to a reference network.

실시간 도로 데이터의 링크 ID·스키마·신선도를 기준망과 비교합니다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from roadops.spatial import normalize_link_id


@dataclass(frozen=True)
class LinkCompatibilityThresholds:
    """Minimum quality required before dynamic records enter RoadOps scoring."""

    reference_id_validity_min: float = 0.99
    reference_id_uniqueness_min: float = 1.0
    source_id_validity_min: float = 0.99
    exact_join_rate_min: float = 0.95
    record_key_completeness_min: float = 0.99
    record_key_uniqueness_min: float = 1.0
    required_field_population_min: float = 0.95
    timestamp_validity_min: float = 0.99
    timestamp_not_future_min: float = 0.99


def _canonicalize(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in row.items()}


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


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
    observed = numerator / denominator if denominator else None
    return {
        "check_id": check_id,
        "dimension": dimension,
        "severity": severity,
        "numerator": numerator,
        "denominator": denominator,
        "observed_rate": round(observed, 6) if observed is not None else None,
        "minimum_rate": minimum_rate,
        "passed": observed is not None and observed >= minimum_rate,
        "meaning": meaning,
    }


def _maximum_check(
    *,
    check_id: str,
    dimension: str,
    severity: str,
    observed_value: float | None,
    maximum_value: float,
    unit: str,
    meaning: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "dimension": dimension,
        "severity": severity,
        "observed_value": (
            round(observed_value, 3) if observed_value is not None else None
        ),
        "maximum_value": maximum_value,
        "unit": unit,
        "passed": observed_value is not None and observed_value <= maximum_value,
        "meaning": meaning,
    }


def _parse_timestamp(value: Any, timezone: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        parsed = None
        for pattern in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _record_key(
    row: Mapping[str, Any],
    fields: tuple[str, ...],
    *,
    link_field: str,
    timestamp_field: str | None,
    timezone: ZoneInfo,
) -> tuple[str, ...] | None:
    values: list[str] = []
    for field in fields:
        raw = row.get(field)
        if not _present(raw):
            return None
        if field == link_field:
            values.append(normalize_link_id(raw) or str(raw).strip())
        elif timestamp_field is not None and field == timestamp_field:
            timestamp = _parse_timestamp(raw, timezone)
            values.append(timestamp.isoformat() if timestamp else str(raw).strip())
        else:
            values.append(str(raw).strip())
    return tuple(values)


def _append_issue(
    samples: list[dict[str, Any]],
    counts: Counter[str],
    *,
    issue: str,
    sample_limit: int,
    row_index: int | None = None,
    **details: Any,
) -> None:
    counts[issue] += 1
    if len(samples) >= sample_limit:
        return
    sample = {"issue": issue}
    if row_index is not None:
        sample["row_index"] = row_index
    sample.update({key: value for key, value in details.items() if value is not None})
    samples.append(sample)


def profile_link_compatibility(
    source_rows: Iterable[Mapping[str, Any]],
    reference_link_rows: Iterable[Mapping[str, Any]],
    *,
    source_id: str,
    link_field: str = "link_id",
    expected_fields: Iterable[str] = (),
    record_key_fields: Iterable[str] = (),
    timestamp_field: str | None = None,
    source_timezone: str = "Asia/Seoul",
    freshness_max_minutes: float | None = None,
    now: datetime | None = None,
    thresholds: LinkCompatibilityThresholds | None = None,
    issue_sample_limit: int = 25,
) -> dict[str, Any]:
    """Measure schema, grain, freshness, and exact-link compatibility."""

    if issue_sample_limit < 0:
        raise ValueError("issue_sample_limit must be non-negative")
    if freshness_max_minutes is not None and freshness_max_minutes < 0:
        raise ValueError("freshness_max_minutes must be non-negative")

    rules = thresholds or LinkCompatibilityThresholds()
    timezone = ZoneInfo(source_timezone)
    current_time = now or datetime.now(timezone)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone)
    else:
        current_time = current_time.astimezone(timezone)

    normalized_link_field = link_field.strip().lower()
    normalized_timestamp_field = (
        timestamp_field.strip().lower() if timestamp_field else None
    )
    normalized_expected_fields = tuple(
        dict.fromkeys(field.strip().lower() for field in expected_fields if field.strip())
    )
    normalized_record_key = tuple(
        dict.fromkeys(field.strip().lower() for field in record_key_fields if field.strip())
    )

    source = [_canonicalize(row) for row in source_rows]
    references = [_canonicalize(row) for row in reference_link_rows]
    issue_counts: Counter[str] = Counter()
    issue_samples: list[dict[str, Any]] = []

    reference_ids = [
        normalize_link_id(row.get("link_id")) for row in references
    ]
    valid_reference_ids = [link_id for link_id in reference_ids if link_id is not None]
    reference_counts = Counter(valid_reference_ids)
    reference_set = set(valid_reference_ids)
    reference_duplicate_excess = sum(
        count - 1 for count in reference_counts.values() if count > 1
    )

    valid_source_ids: list[str] = []
    matched_source_ids: list[str] = []
    unmatched_source_ids: list[str] = []
    invalid_source_id_count = 0
    field_population: Counter[str] = Counter()
    parsed_timestamps: list[datetime] = []
    future_timestamp_count = 0
    future_tolerance = timedelta(minutes=5)
    complete_record_keys: list[tuple[str, ...]] = []

    for row_index, row in enumerate(source):
        raw_link_id = row.get(normalized_link_field)
        link_id = normalize_link_id(raw_link_id)
        if link_id is None:
            invalid_source_id_count += 1
            _append_issue(
                issue_samples,
                issue_counts,
                issue="invalid_source_link_id",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                raw_link_id=str(raw_link_id) if raw_link_id is not None else None,
            )
        else:
            valid_source_ids.append(link_id)
            if link_id in reference_set:
                matched_source_ids.append(link_id)
            else:
                unmatched_source_ids.append(link_id)
                _append_issue(
                    issue_samples,
                    issue_counts,
                    issue="unmatched_source_link_id",
                    row_index=row_index,
                    sample_limit=issue_sample_limit,
                    link_id=link_id,
                )

        for field in normalized_expected_fields:
            if _present(row.get(field)):
                field_population[field] += 1
            else:
                _append_issue(
                    issue_samples,
                    issue_counts,
                    issue=f"missing_required_field:{field}",
                    row_index=row_index,
                    sample_limit=issue_sample_limit,
                    link_id=link_id,
                )

        if normalized_timestamp_field is not None:
            timestamp = _parse_timestamp(row.get(normalized_timestamp_field), timezone)
            if timestamp is None:
                _append_issue(
                    issue_samples,
                    issue_counts,
                    issue="invalid_source_timestamp",
                    row_index=row_index,
                    sample_limit=issue_sample_limit,
                    link_id=link_id,
                )
            else:
                parsed_timestamps.append(timestamp)
                if timestamp > current_time + future_tolerance:
                    future_timestamp_count += 1
                    _append_issue(
                        issue_samples,
                        issue_counts,
                        issue="future_source_timestamp",
                        row_index=row_index,
                        sample_limit=issue_sample_limit,
                        link_id=link_id,
                        timestamp=timestamp.isoformat(),
                    )

        if normalized_record_key:
            key = _record_key(
                row,
                normalized_record_key,
                link_field=normalized_link_field,
                timestamp_field=normalized_timestamp_field,
                timezone=timezone,
            )
            if key is None:
                _append_issue(
                    issue_samples,
                    issue_counts,
                    issue="incomplete_record_key",
                    row_index=row_index,
                    sample_limit=issue_sample_limit,
                    link_id=link_id,
                )
            else:
                complete_record_keys.append(key)

    record_key_counts = Counter(complete_record_keys)
    duplicate_record_key_excess = sum(
        count - 1 for count in record_key_counts.values() if count > 1
    )
    for key, count in sorted(record_key_counts.items()):
        if count > 1:
            _append_issue(
                issue_samples,
                issue_counts,
                issue="duplicate_record_key",
                sample_limit=issue_sample_limit,
                record_key=list(key),
                occurrence_count=count,
            )

    checks = [
        _rate_check(
            check_id="reference_link_id_validity",
            dimension="validity",
            severity="critical",
            numerator=len(valid_reference_ids),
            denominator=len(references),
            minimum_rate=rules.reference_id_validity_min,
            meaning="Reference rows with a valid ten-digit link_id.",
        ),
        _rate_check(
            check_id="reference_link_id_uniqueness",
            dimension="uniqueness",
            severity="critical",
            numerator=len(reference_counts),
            denominator=len(valid_reference_ids),
            minimum_rate=rules.reference_id_uniqueness_min,
            meaning="Valid reference link IDs that are unique.",
        ),
        _rate_check(
            check_id="source_link_id_validity",
            dimension="validity",
            severity="critical",
            numerator=len(valid_source_ids),
            denominator=len(source),
            minimum_rate=rules.source_id_validity_min,
            meaning="Dynamic source rows with a valid ten-digit link_id.",
        ),
        _rate_check(
            check_id="exact_link_join_rate",
            dimension="integrity",
            severity="critical",
            numerator=len(matched_source_ids),
            denominator=len(valid_source_ids),
            minimum_rate=rules.exact_join_rate_min,
            meaning="Valid source link IDs found in the supplied reference network.",
        ),
    ]

    if normalized_record_key:
        checks.extend(
            [
                _rate_check(
                    check_id="record_key_completeness",
                    dimension="completeness",
                    severity="high",
                    numerator=len(complete_record_keys),
                    denominator=len(source),
                    minimum_rate=rules.record_key_completeness_min,
                    meaning="Source rows with every configured record-key field populated.",
                ),
                _rate_check(
                    check_id="record_key_uniqueness",
                    dimension="uniqueness",
                    severity="high",
                    numerator=len(record_key_counts),
                    denominator=len(complete_record_keys),
                    minimum_rate=rules.record_key_uniqueness_min,
                    meaning="Complete source record keys that are unique.",
                ),
            ]
        )

    for field in normalized_expected_fields:
        checks.append(
            _rate_check(
                check_id=f"required_field_population:{field}",
                dimension="completeness",
                severity="high",
                numerator=field_population[field],
                denominator=len(source),
                minimum_rate=rules.required_field_population_min,
                meaning=f"Source rows with a populated {field} field.",
            )
        )

    latest_timestamp = max(parsed_timestamps) if parsed_timestamps else None
    earliest_timestamp = min(parsed_timestamps) if parsed_timestamps else None
    latest_age_minutes = (
        (current_time - latest_timestamp).total_seconds() / 60
        if latest_timestamp is not None
        else None
    )
    if normalized_timestamp_field is not None:
        checks.extend(
            [
                _rate_check(
                    check_id="source_timestamp_validity",
                    dimension="validity",
                    severity="high",
                    numerator=len(parsed_timestamps),
                    denominator=len(source),
                    minimum_rate=rules.timestamp_validity_min,
                    meaning="Source rows with a parseable timestamp.",
                ),
                _rate_check(
                    check_id="source_timestamp_not_future",
                    dimension="consistency",
                    severity="high",
                    numerator=len(parsed_timestamps) - future_timestamp_count,
                    denominator=len(parsed_timestamps),
                    minimum_rate=rules.timestamp_not_future_min,
                    meaning="Parsed timestamps no more than five minutes in the future.",
                ),
            ]
        )
        if freshness_max_minutes is not None:
            checks.append(
                _maximum_check(
                    check_id="source_freshness",
                    dimension="timeliness",
                    severity="high",
                    observed_value=latest_age_minutes,
                    maximum_value=freshness_max_minutes,
                    unit="minutes",
                    meaning="Age of the newest parseable source record.",
                )
            )

    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    unique_source_ids = set(valid_source_ids)
    unique_matched_ids = set(matched_source_ids)
    return {
        "schema_version": 1,
        "dataset": "dynamic_link_compatibility",
        "source_id": source_id,
        "grain": {
            "reference": "one row per link_id",
            "source_record_key": list(normalized_record_key),
        },
        "status": "pass" if not failed_checks else "fail",
        "failed_checks": failed_checks,
        "thresholds": asdict(rules),
        "summary": {
            "reference_link_rows": len(references),
            "reference_valid_unique_link_ids": len(reference_counts),
            "reference_duplicate_link_id_excess": reference_duplicate_excess,
            "source_rows": len(source),
            "valid_source_link_id_rows": len(valid_source_ids),
            "invalid_source_link_id_rows": invalid_source_id_count,
            "distinct_valid_source_link_ids": len(unique_source_ids),
            "matched_source_rows": len(matched_source_ids),
            "unmatched_valid_source_rows": len(unmatched_source_ids),
            "distinct_matched_link_ids": len(unique_matched_ids),
            "valid_id_exact_join_rate": (
                round(len(matched_source_ids) / len(valid_source_ids), 6)
                if valid_source_ids
                else None
            ),
            "all_record_exact_join_rate": (
                round(len(matched_source_ids) / len(source), 6) if source else None
            ),
            "reference_link_coverage": (
                round(len(unique_matched_ids) / len(reference_set), 6)
                if reference_set
                else None
            ),
            "complete_record_keys": len(complete_record_keys),
            "duplicate_record_key_excess": duplicate_record_key_excess,
        },
        "field_population": {
            field: {
                "populated_rows": field_population[field],
                "total_rows": len(source),
                "rate": (
                    round(field_population[field] / len(source), 6)
                    if source
                    else None
                ),
            }
            for field in normalized_expected_fields
        },
        "freshness": {
            "timestamp_field": normalized_timestamp_field,
            "source_timezone": source_timezone,
            "evaluated_at": current_time.isoformat(),
            "parseable_timestamp_rows": len(parsed_timestamps),
            "future_timestamp_rows": future_timestamp_count,
            "earliest_timestamp": (
                earliest_timestamp.isoformat() if earliest_timestamp else None
            ),
            "latest_timestamp": latest_timestamp.isoformat() if latest_timestamp else None,
            "latest_age_minutes": (
                round(latest_age_minutes, 3)
                if latest_age_minutes is not None
                else None
            ),
            "freshness_max_minutes": freshness_max_minutes,
        },
        "unmatched_link_prefixes": dict(
            Counter(link_id[:3] for link_id in unmatched_source_ids).most_common(10)
        ),
        "checks": checks,
        "issue_counts": dict(sorted(issue_counts.items())),
        "issue_sample": issue_samples,
        "issue_sample_truncated": sum(issue_counts.values()) > len(issue_samples),
    }
