"""Validate RoadOps priority forecasts against later nowcast snapshots.

사고 확률이 아닌 운영 우선순위 점수를 동시점 유지 기준선과 재현 가능하게 비교합니다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Iterable, Mapping


VALIDATION_VERSION = "roadops-forecast-validation-v0.1"
MIN_MATCHED_POINTS = 20
MIN_TARGET_TIMES = 3


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def aggregate_link_forecasts(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse event-level forecasts to the link grain used by the dashboard."""

    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        row = dict(source)
        link_id = _text(row.get("effective_link_id") or row.get("link_id"))
        target_at = _text(row.get("target_at"))
        horizon = _integer(row.get("horizon_hours"))
        if link_id is None or target_at is None or horizon is None:
            continue
        groups[(link_id, target_at, horizon)].append(row)

    output: list[dict[str, Any]] = []
    for (link_id, target_at, horizon), candidates in sorted(groups.items()):
        scored = [
            row
            for row in candidates
            if _number(row.get("forecast_priority_score") or row.get("priority_score"))
            is not None
            and (
                _truthy(row.get("ranking_eligible"))
                if row.get("ranking_eligible") is not None
                else True
            )
        ]
        representative = max(
            scored or candidates,
            key=lambda row: _number(
                row.get("forecast_priority_score") or row.get("priority_score")
            )
            or -1.0,
        )
        scores = [
            value
            for row in scored
            if (value := _number(row.get("forecast_priority_score") or row.get("priority_score")))
            is not None
        ]
        lower_bounds = [
            value
            for row in scored
            if (value := _number(row.get("forecast_score_lower_bound") or row.get("score_lower_bound")))
            is not None
        ]
        upper_bounds = [
            value
            for row in scored
            if (value := _number(row.get("forecast_score_upper_bound") or row.get("score_upper_bound")))
            is not None
        ]
        output.append(
            {
                "link_id": link_id,
                "road_name": _text(representative.get("road_name")),
                "horizon_hours": horizon,
                "target_at": target_at,
                "generated_at": _text(representative.get("generated_at")),
                "priority_score": max(scores) if scores else None,
                "score_lower_bound": min(lower_bounds) if lower_bounds else None,
                "score_upper_bound": max(upper_bounds) if upper_bounds else None,
                "ranking_eligible": bool(scores),
                "forecast_status": _text(representative.get("forecast_status")),
                "forecast_semantics": _text(representative.get("forecast_semantics")),
                "weather_evidence_kind": _text(representative.get("weather_evidence_kind")),
                "weather_base_at": _text(representative.get("weather_base_at")),
                "weather_fetched_at": _text(representative.get("weather_fetched_at")),
                "weather_valid_at": _text(representative.get("weather_valid_at")),
            }
        )
    return output


def validate_forecast_snapshots(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime,
    horizons: Iterable[int] = (0, 1, 3, 6),
    outcome_delay_minutes: int = 90,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Match each earliest forecast vintage to the first later nowcast outcome."""

    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    normalized = []
    for snapshot in snapshots:
        snapshot_generated_at = _text(snapshot.get("generated_at"))
        for source in snapshot.get("rows", []):
            row = dict(source)
            row["snapshot_id"] = _text(snapshot.get("snapshot_id"))
            row["snapshot_generated_at"] = snapshot_generated_at
            normalized.append(row)

    leakage_failures: list[dict[str, Any]] = []
    for row in normalized:
        horizon = _integer(row.get("horizon_hours"))
        forecast_at = _datetime(row.get("generated_at") or row.get("snapshot_generated_at"))
        target_at = _datetime(row.get("target_at"))
        if horizon is None or forecast_at is None or target_at is None:
            leakage_failures.append({"check": "valid_timestamp", "link_id": row.get("link_id")})
            continue
        if horizon > 0 and forecast_at > target_at:
            leakage_failures.append({"check": "forecast_after_target", "link_id": row.get("link_id")})
        for field in ("weather_base_at", "weather_fetched_at"):
            evidence_at = _datetime(row.get(field))
            if evidence_at is not None and evidence_at > forecast_at:
                leakage_failures.append(
                    {"check": f"future_{field}", "link_id": row.get("link_id")}
                )

    forecasts: dict[tuple[int, str, str], dict[str, Any]] = {}
    current_by_target_link: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    current_by_snapshot_link: dict[tuple[str, str], dict[str, Any]] = {}
    for row in normalized:
        horizon = _integer(row.get("horizon_hours"))
        link_id = _text(row.get("link_id"))
        target_at = _text(row.get("target_at"))
        score = _number(row.get("priority_score"))
        generated = _datetime(row.get("generated_at") or row.get("snapshot_generated_at"))
        if horizon is None or link_id is None or target_at is None or score is None or generated is None:
            continue
        if horizon == 0:
            current_by_target_link[(target_at, link_id)].append(row)
            snapshot_id = _text(row.get("snapshot_id"))
            if snapshot_id:
                current_by_snapshot_link[(snapshot_id, link_id)] = row
        else:
            key = (horizon, target_at, link_id)
            existing = forecasts.get(key)
            existing_at = _datetime(existing.get("generated_at") or existing.get("snapshot_generated_at")) if existing else None
            if existing_at is None or generated < existing_at:
                forecasts[key] = row

    for rows in current_by_target_link.values():
        rows.sort(key=lambda row: _datetime(row.get("generated_at") or row.get("snapshot_generated_at")) or generated_at)

    matched: list[dict[str, Any]] = []
    for (horizon, target_text, link_id), forecast in sorted(forecasts.items()):
        forecast_at = _datetime(forecast.get("generated_at") or forecast.get("snapshot_generated_at"))
        target_at = _datetime(target_text)
        if forecast_at is None or target_at is None:
            continue
        outcomes = current_by_target_link.get((target_text, link_id), [])
        outcome = next(
            (
                row
                for row in outcomes
                if (observed_at := _datetime(row.get("generated_at") or row.get("snapshot_generated_at")))
                and target_at <= observed_at <= target_at + timedelta(minutes=outcome_delay_minutes)
            ),
            None,
        )
        baseline = current_by_snapshot_link.get(
            (_text(forecast.get("snapshot_id")) or "", link_id)
        )
        if outcome is None or baseline is None:
            continue
        forecast_score = _number(forecast.get("priority_score"))
        outcome_score = _number(outcome.get("priority_score"))
        baseline_score = _number(baseline.get("priority_score"))
        if forecast_score is None or outcome_score is None or baseline_score is None:
            continue
        lower = _number(forecast.get("score_lower_bound"))
        upper = _number(forecast.get("score_upper_bound"))
        forecast_error = abs(forecast_score - outcome_score)
        baseline_error = abs(baseline_score - outcome_score)
        matched.append(
            {
                "horizon_hours": horizon,
                "link_id": link_id,
                "road_name": _text(forecast.get("road_name")),
                "forecast_generated_at": forecast_at.isoformat(),
                "target_at": target_at.isoformat(),
                "outcome_generated_at": _text(outcome.get("generated_at") or outcome.get("snapshot_generated_at")),
                "forecast_score": round(forecast_score, 3),
                "persistence_score": round(baseline_score, 3),
                "outcome_score": round(outcome_score, 3),
                "forecast_absolute_error": round(forecast_error, 3),
                "persistence_absolute_error": round(baseline_error, 3),
                "interval_contains_outcome": (
                    lower <= outcome_score <= upper
                    if lower is not None and upper is not None
                    else None
                ),
                "comparison": (
                    "forecast_better"
                    if forecast_error < baseline_error
                    else "persistence_better"
                    if baseline_error < forecast_error
                    else "tie"
                ),
            }
        )

    metrics = []
    requested_horizons = sorted(set(int(value) for value in horizons))
    for horizon in requested_horizons:
        if horizon == 0:
            current_rows = [
                row for row in normalized
                if _integer(row.get("horizon_hours")) == 0
                and _number(row.get("priority_score")) is not None
            ]
            metrics.append(
                {
                    "horizon_hours": 0,
                    "validation_status": "descriptive_only",
                    "comparison_status": "not_applicable",
                    "matched_points": len(current_rows),
                    "target_times": len({_text(row.get("target_at")) for row in current_rows}),
                    "link_count": len({_text(row.get("link_id")) for row in current_rows}),
                    "forecast_mae": None,
                    "persistence_mae": None,
                    "mae_improvement": None,
                    "interval_coverage_ratio": None,
                    "note": "현재 시점은 예측 정확도가 아닌 현재 상태 산출 가용성만 확인합니다.",
                }
            )
            continue
        horizon_rows = [row for row in matched if row["horizon_hours"] == horizon]
        point_count = len(horizon_rows)
        target_count = len({row["target_at"] for row in horizon_rows})
        if point_count == 0:
            validation_status = "pending"
            comparison_status = "not_available"
        elif point_count < MIN_MATCHED_POINTS or target_count < MIN_TARGET_TIMES:
            validation_status = "insufficient_evidence"
            comparison_status = "provisional"
        else:
            validation_status = "evaluated"
            comparison_status = "evaluated"
        forecast_mae = mean(row["forecast_absolute_error"] for row in horizon_rows) if horizon_rows else None
        persistence_mae = mean(row["persistence_absolute_error"] for row in horizon_rows) if horizon_rows else None
        bounded = [row for row in horizon_rows if row["interval_contains_outcome"] is not None]
        metrics.append(
            {
                "horizon_hours": horizon,
                "validation_status": validation_status,
                "comparison_status": comparison_status,
                "matched_points": point_count,
                "target_times": target_count,
                "link_count": len({row["link_id"] for row in horizon_rows}),
                "forecast_mae": round(forecast_mae, 3) if forecast_mae is not None else None,
                "persistence_mae": round(persistence_mae, 3) if persistence_mae is not None else None,
                "mae_improvement": (
                    round(persistence_mae - forecast_mae, 3)
                    if forecast_mae is not None and persistence_mae is not None
                    else None
                ),
                "interval_coverage_ratio": (
                    round(sum(bool(row["interval_contains_outcome"]) for row in bounded) / len(bounded), 3)
                    if bounded else None
                ),
                "forecast_wins": sum(row["comparison"] == "forecast_better" for row in horizon_rows),
                "ties": sum(row["comparison"] == "tie" for row in horizon_rows),
                "persistence_wins": sum(row["comparison"] == "persistence_better" for row in horizon_rows),
                "note": (
                    "비교 표본이 부족해 성능 우위를 판단할 수 없습니다."
                    if validation_status == "insufficient_evidence"
                    else "비교할 수 있는 실제 시점이 아직 없습니다."
                    if validation_status == "pending"
                    else "지속 기준선과 같은 시점의 절대오차를 비교했습니다."
                ),
            }
        )

    status = "fail" if leakage_failures else (
        "pass" if all(row["validation_status"] in {"descriptive_only", "evaluated"} for row in metrics)
        else "pass_with_limitations"
    )
    report = {
        "schema_version": 1,
        "validation_version": VALIDATION_VERSION,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "forecast_semantics": "operational_priority_scenario_not_accident_probability",
        "baseline": "same_link_same_forecast_vintage_current_score_persistence",
        "minimum_evidence": {
            "matched_points": MIN_MATCHED_POINTS,
            "target_times": MIN_TARGET_TIMES,
        },
        "snapshot_count": len({_text(row.get("snapshot_id")) for row in normalized}),
        "leakage_failure_count": len(leakage_failures),
        "leakage_failures": leakage_failures,
        "metrics": metrics,
        "limitations": [
            "priority_score_validation_not_accident_probability_validation",
            "current_available_history_is_sparse",
            "same_time_persistence_is_the_required_baseline",
        ],
    }
    return report, matched
