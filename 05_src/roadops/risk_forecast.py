"""Build auditable 0/1/3/6-hour RoadOps priority scenarios.

사고확률을 주장하지 않고 실황·예보·결측 근거를 분리한 위험 우선순위 시나리오를 만듭니다.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Iterable, Mapping

from roadops.gateway_pressure import gateway_contribution
from roadops.risk_scoring import score_risk_event


FORECAST_VERSION = "roadops-priority-scenario-v0.1"
DEFAULT_HORIZONS = (0, 1, 3, 6)
FUTURE_SENSOR_FIELDS = (
    "cits_visibility",
    "cits_snow",
    "cits_road_temperature",
    "cits_water_film",
    "cits_friction",
)
FUTURE_TRAFFIC_FIELDS = (
    "traffic_observed_at",
    "traffic_volume",
    "traffic_speed_kph",
    "traffic_occupancy_rate",
    "traffic_travel_time",
)

RISK_FORECAST_FIELDS = (
    "forecast_id",
    "generated_at",
    "target_at",
    "horizon_hours",
    "event_id",
    "source_id",
    "event_type",
    "event_code",
    "effective_link_id",
    "road_name",
    "integration_class",
    "forecast_version",
    "forecast_semantics",
    "forecast_status",
    "score_available",
    "ranking_eligible",
    "forecast_rank",
    "forecast_priority_score",
    "forecast_score_lower_bound",
    "forecast_score_upper_bound",
    "forecast_uncertainty_width",
    "risk_level",
    "evidence_coverage_ratio",
    "risk_delta_from_current",
    "risk_direction",
    "event_assumption",
    "traffic_assumption",
    "gateway_inflow_status",
    "gateway_inflow_pressure",
    "gateway_score",
    "weather_row_status",
    "weather_evidence_kind",
    "weather_source_id",
    "weather_base_at",
    "weather_valid_at",
    "weather_evidence_at",
    "weather_temperature_c",
    "weather_rainfall_raw",
    "weather_precipitation_type",
    "weather_humidity_percent",
    "weather_wind_speed_mps",
    "event_score",
    "structural_score",
    "weather_road_score",
    "traffic_score",
    "risk_drivers",
    "quality_flags",
    "forecast_limitations",
)


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _integer(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
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


def _forecast_id(event_id: str, horizon: int, target_at: datetime) -> str:
    raw = f"{event_id}|{horizon}|{target_at.isoformat()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _weather_index(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[tuple[int, int, int], dict[str, Any]], int]:
    index: dict[tuple[int, int, int], dict[str, Any]] = {}
    duplicate_rows = 0
    for source in rows:
        row = dict(source)
        grid_x = _integer(row.get("grid_x"))
        grid_y = _integer(row.get("grid_y"))
        horizon = _integer(row.get("horizon_hours"))
        if grid_x is None or grid_y is None or horizon is None:
            continue
        key = (grid_x, grid_y, horizon)
        if key in index:
            duplicate_rows += 1
            continue
        index[key] = row
    return index, duplicate_rows


def _weather_overlay(
    event: Mapping[str, Any],
    weather: Mapping[str, Any] | None,
    *,
    horizon: int,
    target_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = dict(event)
    limitations: set[str] = set()
    weather_kind: str | None = None
    weather_source_id: str | None = None
    weather_evidence_at: str | None = None

    if weather is None:
        row.update(
            {
                "weather_status": "missing",
                "weather_forecast_at": None,
                "weather_temperature_c": None,
                "weather_rainfall_1h_raw": None,
                "weather_precipitation_type": None,
                "weather_humidity_percent": None,
                "weather_wind_speed_mps": None,
            }
        )
        limitations.add("weather:timeline_row_missing")
    elif horizon == 0 and str(weather.get("observation_status")) == "matched":
        weather_kind = "observation"
        weather_source_id = "kma_ultra_short_nowcast"
        weather_evidence_at = _text(weather.get("observed_at"))
        row.update(
            {
                "weather_status": "matched",
                "weather_forecast_at": target_at.isoformat(),
                "weather_temperature_c": weather.get("observed_temperature_c"),
                "weather_rainfall_1h_raw": weather.get("observed_rainfall_1h_raw"),
                "weather_precipitation_type": weather.get(
                    "observed_precipitation_type"
                ),
                "weather_humidity_percent": weather.get(
                    "observed_humidity_percent"
                ),
                "weather_wind_speed_mps": weather.get("observed_wind_speed_mps"),
            }
        )
    elif str(weather.get("forecast_status")) == "matched":
        weather_kind = "forecast"
        weather_source_id = _text(weather.get("forecast_source_id"))
        weather_evidence_at = _text(weather.get("forecast_valid_at"))
        row.update(
            {
                "weather_status": "matched",
                "weather_forecast_at": target_at.isoformat(),
                "weather_temperature_c": weather.get("forecast_temperature_c"),
                "weather_rainfall_1h_raw": weather.get("forecast_rainfall_raw"),
                "weather_precipitation_type": weather.get(
                    "forecast_precipitation_type"
                ),
                "weather_humidity_percent": weather.get(
                    "forecast_humidity_percent"
                ),
                "weather_wind_speed_mps": weather.get("forecast_wind_speed_mps"),
            }
        )
        if horizon == 0:
            limitations.add("weather:current_forecast_fallback")
    else:
        row.update(
            {
                "weather_status": "missing",
                "weather_forecast_at": None,
                "weather_temperature_c": None,
                "weather_rainfall_1h_raw": None,
                "weather_precipitation_type": None,
                "weather_humidity_percent": None,
                "weather_wind_speed_mps": None,
            }
        )
        limitations.add("weather:usable_evidence_missing")

    if horizon > 0:
        for field in FUTURE_SENSOR_FIELDS:
            row[field] = None
        row["traffic_status"] = "future_forecast_unavailable"
        for field in FUTURE_TRAFFIC_FIELDS:
            row[field] = None
        limitations.update(
            {
                "event:persistence_scenario_without_end_time",
                "road_sensor:future_value_not_available",
                "traffic:future_forecast_not_available",
            }
        )

    metadata = {
        "weather_row_status": _text(weather.get("row_status")) if weather else None,
        "weather_evidence_kind": weather_kind,
        "weather_source_id": weather_source_id,
        "weather_base_at": (
            _text(weather.get("forecast_base_at")) if weather else None
        ),
        "weather_valid_at": (
            _text(weather.get("forecast_valid_at")) if weather else None
        ),
        "weather_evidence_at": weather_evidence_at,
        "weather_temperature_c": row.get("weather_temperature_c"),
        "weather_rainfall_raw": row.get("weather_rainfall_1h_raw"),
        "weather_precipitation_type": row.get("weather_precipitation_type"),
        "weather_humidity_percent": row.get("weather_humidity_percent"),
        "weather_wind_speed_mps": row.get("weather_wind_speed_mps"),
        "limitations": limitations,
    }
    return row, metadata


def _distribution(values: Iterable[Any]) -> dict[str, Any]:
    observed = sorted(
        number for value in values if (number := _number(value)) is not None
    )
    if not observed:
        return {"count": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "count": len(observed),
        "minimum": round(observed[0], 3),
        "median": round(median(observed), 3),
        "maximum": round(observed[-1], 3),
    }


def _risk_level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "moderate"
    return "low"


def build_risk_forecasts(
    events: Iterable[Mapping[str, Any]],
    weather_rows: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    gateway_pressure: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one inspectable priority scenario per event and horizon."""

    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    input_events = [dict(row) for row in events]
    input_weather = [dict(row) for row in weather_rows]
    ordered_horizons = sorted(set(int(value) for value in horizons))
    weather_index, duplicate_weather_rows = _weather_index(input_weather)
    target_base = generated_at.replace(minute=0, second=0, microsecond=0)
    output: list[dict[str, Any]] = []

    for event in input_events:
        event_id = str(event.get("event_id") or "")
        grid_x = _integer(event.get("weather_grid_x"))
        grid_y = _integer(event.get("weather_grid_y"))
        for horizon in ordered_horizons:
            weather = (
                weather_index.get((grid_x, grid_y, horizon))
                if grid_x is not None and grid_y is not None
                else None
            )
            weather_target = _datetime(weather.get("target_at")) if weather else None
            target_at = weather_target or target_base + timedelta(hours=horizon)
            scoring_row, weather_metadata = _weather_overlay(
                event,
                weather,
                horizon=horizon,
                target_at=target_at,
            )
            score_reference_at = generated_at if horizon == 0 else target_at
            scored = score_risk_event(
                scoring_row,
                generated_at=score_reference_at,
                allow_event_persistence_scenario=horizon > 0,
            )
            limitations = set(weather_metadata.pop("limitations"))
            gateway = gateway_contribution(event, gateway_pressure, target_at=target_at)
            gateway_points = float(gateway.get("contribution") or 0)
            priority_score = _number(scored.get("risk_score"))
            lower_bound = _number(scored.get("risk_score_lower_bound"))
            upper_bound = _number(scored.get("risk_score_upper_bound"))
            if scored.get("score_available") and gateway_points > 0:
                priority_score = min(100.0, float(priority_score or 0) + gateway_points)
                lower_bound = min(100.0, float(lower_bound or 0) + gateway_points)
                upper_bound = min(100.0, float(upper_bound or 0) + gateway_points)
                risk_drivers = " | ".join(
                    value for value in (
                        str(scored.get("risk_drivers") or ""),
                        f"gateway:airport_inflow_pressure:{gateway_points:.3f}",
                    ) if value
                )
            else:
                risk_drivers = scored.get("risk_drivers")
            if gateway["status"] == "unavailable":
                limitations.add("gateway_inflow:unavailable_not_scored")
            elif gateway["status"] != "applied":
                limitations.add(f"gateway_inflow:{gateway['status']}")
            forecast_row = {
                "forecast_id": _forecast_id(event_id, horizon, target_at),
                "generated_at": generated_at.isoformat(),
                "target_at": target_at.isoformat(),
                "horizon_hours": horizon,
                "event_id": scored.get("event_id"),
                "source_id": scored.get("source_id"),
                "event_type": scored.get("event_type"),
                "event_code": scored.get("event_code"),
                "effective_link_id": scored.get("effective_link_id"),
                "road_name": scored.get("road_name"),
                "integration_class": scored.get("integration_class"),
                "forecast_version": FORECAST_VERSION,
                "forecast_semantics": "operational_priority_scenario_not_accident_probability",
                "forecast_status": scored.get("scoring_status"),
                "score_available": scored.get("score_available"),
                "ranking_eligible": scored.get("ranking_eligible"),
                "forecast_rank": None,
                "forecast_priority_score": round(priority_score, 3) if priority_score is not None else None,
                "forecast_score_lower_bound": round(lower_bound, 3) if lower_bound is not None else None,
                "forecast_score_upper_bound": round(upper_bound, 3) if upper_bound is not None else None,
                "forecast_uncertainty_width": (
                    round(upper_bound - lower_bound, 3)
                    if upper_bound is not None and lower_bound is not None
                    else None
                ),
                "risk_level": _risk_level(priority_score) if priority_score is not None else scored.get("risk_level"),
                "evidence_coverage_ratio": scored.get("evidence_coverage_ratio"),
                "risk_delta_from_current": None,
                "risk_direction": None,
                "event_assumption": (
                    "current_snapshot"
                    if horizon == 0
                    else "persistence_scenario_without_end_time"
                ),
                "traffic_assumption": (
                    "current_observation"
                    if horizon == 0
                    else "unavailable_no_future_model"
                ),
                "gateway_inflow_status": gateway["status"],
                "gateway_inflow_pressure": gateway.get("pressure"),
                "gateway_score": gateway_points if gateway["status"] == "applied" else 0.0,
                **weather_metadata,
                "event_score": scored.get("event_score"),
                "structural_score": scored.get("structural_score"),
                "weather_road_score": scored.get("weather_road_score"),
                "traffic_score": scored.get("traffic_score"),
                "risk_drivers": risk_drivers,
                "quality_flags": scored.get("quality_flags"),
                "forecast_limitations": "|".join(sorted(limitations)),
            }
            output.append(forecast_row)

    by_event: dict[str, dict[int, dict[str, Any]]] = {}
    for row in output:
        by_event.setdefault(str(row["event_id"]), {})[int(row["horizon_hours"])] = row
    for event_rows in by_event.values():
        current_score = _number(
            event_rows.get(0, {}).get("forecast_priority_score")
        )
        for row in event_rows.values():
            score = _number(row.get("forecast_priority_score"))
            if current_score is None or score is None:
                continue
            delta = round(score - current_score, 3)
            row["risk_delta_from_current"] = delta
            row["risk_direction"] = (
                "increasing"
                if delta > 1
                else "decreasing"
                if delta < -1
                else "stable"
            )

    for horizon in ordered_horizons:
        eligible = [
            row
            for row in output
            if row["horizon_hours"] == horizon
            and row["ranking_eligible"]
            and _number(row["forecast_priority_score"]) is not None
        ]
        eligible.sort(
            key=lambda row: (
                -float(row["forecast_priority_score"]),
                -float(row["forecast_score_lower_bound"] or 0),
                str(row["event_id"]),
            )
        )
        for rank, row in enumerate(eligible, start=1):
            row["forecast_rank"] = rank

    failed_checks: list[str] = []
    expected_rows = len(input_events) * len(ordered_horizons)
    if len(output) != expected_rows:
        failed_checks.append("event_horizon_row_count")
    identifiers = [str(row["forecast_id"]) for row in output]
    if len(identifiers) != len(set(identifiers)):
        failed_checks.append("forecast_id_uniqueness")
    input_event_ids = [str(row.get("event_id") or "") for row in input_events]
    if len(input_event_ids) != len(set(input_event_ids)):
        failed_checks.append("input_event_id_uniqueness")
    if duplicate_weather_rows:
        failed_checks.append("weather_grid_horizon_uniqueness")
    observed_horizons = {
        _integer(row.get("horizon_hours")) for row in input_weather
    }
    if not set(ordered_horizons).issubset(observed_horizons):
        failed_checks.append("required_weather_horizons")
    if any(
        row["horizon_hours"] > 0
        and row["traffic_assumption"] == "current_observation"
        for row in output
    ):
        failed_checks.append("future_traffic_leakage")
    if not gateway_pressure and any(
        row["gateway_inflow_status"] != "unavailable" for row in output
    ):
        failed_checks.append("gateway_status_mismatch")
    if any(set(row) != set(RISK_FORECAST_FIELDS) for row in output):
        failed_checks.append("schema_mismatch")

    status_counts = Counter(str(row["forecast_status"]) for row in output)
    score_counts = Counter(
        str(row["horizon_hours"])
        for row in output
        if row["score_available"]
    )
    score_distributions = {
        str(horizon): _distribution(
            row["forecast_priority_score"]
            for row in output
            if row["horizon_hours"] == horizon
        )
        for horizon in ordered_horizons
    }
    status = (
        "fail"
        if failed_checks
        else "pass_with_limitations"
        if status_counts.get("hold", 0) or status_counts.get("degraded", 0)
        else "pass"
    )
    report = {
        "schema_version": 1,
        "forecast_version": FORECAST_VERSION,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "horizons": ordered_horizons,
        "input_event_rows": len(input_events),
        "input_weather_rows": len(input_weather),
        "expected_rows": expected_rows,
        "output_rows": len(output),
        "status_counts": dict(sorted(status_counts.items())),
        "scored_rows_by_horizon": dict(sorted(score_counts.items())),
        "score_distributions_by_horizon": score_distributions,
        "duplicate_weather_rows": duplicate_weather_rows,
        "gateway_inflow_status": str((gateway_pressure or {}).get("status") or "unavailable"),
        "forecast_semantics": "operational_priority_scenario_not_accident_probability",
        "failed_checks": failed_checks,
    }
    return output, report
