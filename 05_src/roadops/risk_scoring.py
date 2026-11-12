"""Calculate transparent, quality-gated RoadOps risk scores.

명시적인 규칙과 품질 게이트로 RoadOps 위험점수를 계산합니다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Mapping


SCORE_VERSION = "roadops-risk-v0.1"
SCORING_STATUSES = ("usable", "degraded", "hold")
RISK_LEVELS = ("low", "moderate", "high", "critical")

COMPONENT_WEIGHTS = {
    "event": 35.0,
    "structural": 25.0,
    "weather_road": 25.0,
    "traffic": 15.0,
}
STRUCTURAL_SUBWEIGHTS = {"taas": 0.7, "jeju_datahub_geometry": 0.3}
EVENT_SOURCE_SCORES = {
    "jeju_cits_road_event": (70.0, "active_road_event"),
    "jeju_cits_road_close": (90.0, "active_road_closure"),
    "jeju_cits_road_work": (55.0, "active_road_work"),
}
TAAS_GRADE_SCORES = {"01": 10.0, "02": 40.0, "03": 70.0, "04": 100.0}
PRECIPITATION_TYPE_SCORES = {
    "0": 0.0,
    "1": 40.0,
    "2": 65.0,
    "3": 80.0,
    "4": 50.0,
    "5": 30.0,
    "6": 50.0,
    "7": 65.0,
}

SNAPSHOT_MAX_AGE_MINUTES = 60.0
TRAFFIC_MAX_AGE_MINUTES = 30.0
WEATHER_MAX_OFFSET_MINUTES = 60.0
MAX_FUTURE_SKEW_MINUTES = 5.0
MIN_EVIDENCE_COVERAGE = 0.6

RISK_SCORE_FIELDS = (
    "risk_rank",
    "event_id",
    "source_id",
    "event_type",
    "event_code",
    "effective_link_id",
    "road_name",
    "integration_class",
    "score_version",
    "scoring_status",
    "score_available",
    "ranking_eligible",
    "requires_operator_review",
    "risk_score",
    "risk_score_lower_bound",
    "risk_score_upper_bound",
    "risk_uncertainty_width",
    "risk_level",
    "evidence_coverage_ratio",
    "evidence_weight",
    "expected_weight",
    "snapshot_age_minutes_at_scoring",
    "traffic_age_minutes_at_scoring",
    "weather_offset_minutes_at_scoring",
    "event_component_status",
    "event_score",
    "event_weight",
    "event_contribution",
    "structural_component_status",
    "structural_score",
    "structural_weight",
    "structural_contribution",
    "structural_evidence_coverage",
    "taas_subscore",
    "geometry_subscore",
    "weather_road_component_status",
    "weather_road_score",
    "weather_road_weight",
    "weather_road_contribution",
    "weather_road_driver",
    "traffic_component_status",
    "traffic_score",
    "traffic_weight",
    "traffic_contribution",
    "traffic_driver",
    "risk_drivers",
    "quality_flags",
)


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _minutes_between(later: datetime, earlier: datetime | None) -> float | None:
    if earlier is None:
        return None
    return round((later - earlier).total_seconds() / 60, 3)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return min(maximum, max(minimum, value))


def _rounded(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _component(
    *,
    status: str,
    score: float | None,
    lower: float,
    upper: float,
    coverage: float,
    driver: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "score": _rounded(score),
        "lower": _rounded(_clamp(lower)),
        "upper": _rounded(_clamp(upper)),
        "coverage": round(min(1.0, max(0.0, coverage)), 6),
        "driver": driver,
        "details": dict(details or {}),
    }


def parse_rainfall_millimeters(value: Any) -> float | None:
    """Parse KMA rainfall text while preserving unknown values as missing."""

    text = _text(value)
    if text is None:
        return None
    compact = text.replace(" ", "").lower()
    if compact in {"0", "0.0", "강수없음", "없음", "no rain", "norain"}:
        return 0.0
    if "미만" in compact or compact.startswith("<"):
        match = re.search(r"\d+(?:\.\d+)?", compact)
        return float(match.group()) / 2 if match else 0.5
    match = re.search(r"-?\d+(?:\.\d+)?", compact)
    if not match:
        return None
    number = float(match.group())
    return number if number >= 0 else None


def _rainfall_score(rainfall_mm: float) -> float:
    if rainfall_mm <= 0:
        return 0.0
    if rainfall_mm < 1:
        return 20.0
    if rainfall_mm < 5:
        return 40.0
    if rainfall_mm < 10:
        return 60.0
    if rainfall_mm < 30:
        return 80.0
    return 100.0


def _wind_score(wind_speed_mps: float) -> float:
    if wind_speed_mps < 5:
        return 0.0
    if wind_speed_mps < 9:
        return 20.0
    if wind_speed_mps < 14:
        return 50.0
    if wind_speed_mps < 20:
        return 75.0
    return 100.0


def _visibility_score(visibility_meters: float) -> float:
    if visibility_meters < 100:
        return 100.0
    if visibility_meters < 500:
        return 80.0
    if visibility_meters < 1_000:
        return 60.0
    if visibility_meters < 5_000:
        return 35.0
    if visibility_meters < 10_000:
        return 15.0
    return 0.0


def _friction_score(friction: float) -> float:
    if friction < 0.3:
        return 100.0
    if friction < 0.5:
        return 80.0
    if friction < 0.7:
        return 55.0
    if friction < 0.85:
        return 25.0
    return 0.0


def _road_temperature_score(temperature_c: float) -> float:
    if temperature_c <= 0:
        return 60.0
    if temperature_c <= 2:
        return 40.0
    if temperature_c <= 5:
        return 20.0
    return 0.0


def score_event_component(row: Mapping[str, Any]) -> dict[str, Any]:
    source_id = str(row.get("source_id") or "")
    definition = EVENT_SOURCE_SCORES.get(source_id)
    if definition is None:
        return _component(
            status="not_applicable",
            score=None,
            lower=0,
            upper=0,
            coverage=0,
            driver="no_discrete_event_component",
        )
    score, driver = definition
    return _component(
        status="available",
        score=score,
        lower=score,
        upper=score,
        coverage=1,
        driver=driver,
        details={"event_code": _text(row.get("event_code"))},
    )


def score_structural_component(row: Mapping[str, Any]) -> dict[str, Any]:
    taas_score: float | None = None
    if str(row.get("taas_status") or "") == "ok":
        grade = str(row.get("taas_risk_grade") or "").zfill(2)
        taas_score = TAAS_GRADE_SCORES.get(grade)

    geometry_score: float | None = None
    if str(row.get("hub_geometry_prior_status") or "") == "matched":
        fatality_index = _number(row.get("hub_fatality_index_vs_straight"))
        if fatality_index is not None:
            geometry_score = _clamp((fatality_index - 1.0) * 100.0)

    observed: list[tuple[str, float, float]] = []
    if taas_score is not None:
        observed.append(("taas", STRUCTURAL_SUBWEIGHTS["taas"], taas_score))
    if geometry_score is not None:
        observed.append(
            (
                "jeju_datahub_geometry",
                STRUCTURAL_SUBWEIGHTS["jeju_datahub_geometry"],
                geometry_score,
            )
        )
    coverage = sum(weight for _, weight, _ in observed)
    if not observed:
        return _component(
            status="missing",
            score=None,
            lower=0,
            upper=100,
            coverage=0,
            driver="structural_evidence_missing",
            details={"taas_subscore": None, "geometry_subscore": None},
        )

    weighted_observed = sum(weight * score for _, weight, score in observed)
    estimate = weighted_observed / coverage
    missing_weight = 1.0 - coverage
    status = "available" if coverage == 1 else "partial"
    driver = max(observed, key=lambda item: (item[2], item[0]))[0]
    return _component(
        status=status,
        score=estimate,
        lower=weighted_observed,
        upper=weighted_observed + missing_weight * 100,
        coverage=coverage,
        driver=driver,
        details={
            "taas_subscore": taas_score,
            "geometry_subscore": _rounded(geometry_score),
            "double_count_rule": "bounded_70_30_single_structural_component",
        },
    )


def _valid_sensor_number(value: Any, *, maximum: float | None = None) -> float | None:
    number = _number(value)
    if number is None or number < 0:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def score_weather_road_component(
    row: Mapping[str, Any],
    *,
    weather_current: bool = True,
) -> dict[str, Any]:
    source_id = str(row.get("source_id") or "")
    sensor_expected = source_id == "jeju_cits_road_weather"
    signals: list[tuple[str, float]] = []

    kma_available = False
    if str(row.get("weather_status") or "") == "matched" and weather_current:
        precipitation_type = _text(row.get("weather_precipitation_type"))
        if precipitation_type in PRECIPITATION_TYPE_SCORES:
            signals.append(
                (
                    "kma_precipitation_type",
                    PRECIPITATION_TYPE_SCORES[precipitation_type],
                )
            )
            kma_available = True
        rainfall = parse_rainfall_millimeters(row.get("weather_rainfall_1h_raw"))
        if rainfall is not None:
            signals.append(("kma_rainfall_1h", _rainfall_score(rainfall)))
            kma_available = True
        wind = _valid_sensor_number(row.get("weather_wind_speed_mps"))
        if wind is not None:
            signals.append(("kma_wind_speed", _wind_score(wind)))
            kma_available = True

    sensor_signals: list[tuple[str, float]] = []
    visibility = _valid_sensor_number(row.get("cits_visibility"))
    if visibility is not None:
        sensor_signals.append(("cits_visibility", _visibility_score(visibility)))
    friction = _valid_sensor_number(row.get("cits_friction"), maximum=1.0)
    if friction is not None:
        sensor_signals.append(("cits_friction", _friction_score(friction)))
    road_temperature = _number(row.get("cits_road_temperature"))
    if (
        road_temperature is not None
        and road_temperature != -1
        and road_temperature >= -80
    ):
        sensor_signals.append(
            ("cits_road_temperature", _road_temperature_score(road_temperature))
        )
    snow = _valid_sensor_number(row.get("cits_snow"))
    if snow is not None:
        sensor_signals.append(("cits_snow", 70.0 if snow > 0 else 0.0))
    water_film = _valid_sensor_number(row.get("cits_water_film"))
    if water_film is not None:
        sensor_signals.append(("cits_water_film", 40.0 if water_film > 0 else 0.0))
    signals.extend(sensor_signals)

    expected_inputs = 2 if sensor_expected else 1
    available_inputs = int(kma_available) + int(bool(sensor_signals) and sensor_expected)
    coverage = available_inputs / expected_inputs
    if not signals:
        return _component(
            status="missing",
            score=None,
            lower=0,
            upper=100,
            coverage=0,
            driver="weather_and_road_evidence_missing",
        )

    driver, score = max(signals, key=lambda item: (item[1], item[0]))
    missing_expected_input = coverage < 1
    return _component(
        status="available" if not missing_expected_input else "partial",
        score=score,
        lower=score,
        upper=100 if missing_expected_input else score,
        coverage=coverage,
        driver=driver,
        details={
            "kma_available": kma_available,
            "road_sensor_available": bool(sensor_signals),
            "combination_rule": "maximum_observed_hazard_signal",
        },
    )


def _speed_exposure_score(speed_ratio: float) -> float:
    if speed_ratio <= 0.5:
        return 20.0
    if speed_ratio <= 0.8:
        return 35.0
    if speed_ratio <= 1.0:
        return 55.0
    if speed_ratio <= 1.2:
        return 75.0
    return 100.0


def _occupancy_score(occupancy_percent: float) -> float:
    if occupancy_percent <= 0:
        return 0.0
    if occupancy_percent < 25:
        return 25.0
    if occupancy_percent < 50:
        return 50.0
    if occupancy_percent < 75:
        return 75.0
    return 100.0


def score_traffic_component(
    row: Mapping[str, Any],
    *,
    traffic_current: bool = True,
) -> dict[str, Any]:
    if str(row.get("traffic_status") or "") != "matched" or not traffic_current:
        return _component(
            status="missing_or_stale",
            score=None,
            lower=0,
            upper=100,
            coverage=0,
            driver="traffic_evidence_missing_or_stale",
        )

    signals: list[tuple[str, float]] = []
    speed = _valid_sensor_number(row.get("traffic_speed_kph"))
    speed_limit = _valid_sensor_number(row.get("maximum_speed_limit"))
    if speed is not None and speed_limit is not None and speed_limit > 0:
        signals.append(("speed_to_limit_ratio", _speed_exposure_score(speed / speed_limit)))
    occupancy = _valid_sensor_number(row.get("traffic_occupancy_rate"), maximum=100)
    if occupancy is not None:
        signals.append(("occupancy_rate", _occupancy_score(occupancy)))

    coverage = len(signals) / 2
    if not signals:
        return _component(
            status="missing",
            score=None,
            lower=0,
            upper=100,
            coverage=0,
            driver="traffic_measurements_missing",
        )
    driver, score = max(signals, key=lambda item: (item[1], item[0]))
    return _component(
        status="available" if coverage == 1 else "partial",
        score=score,
        lower=score,
        upper=100 if coverage < 1 else score,
        coverage=coverage,
        driver=driver,
        details={
            "speed_kph": speed,
            "speed_limit_kph": speed_limit,
            "occupancy_percent": occupancy,
            "traffic_volume_scored": False,
        },
    )


def _risk_level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "moderate"
    return "low"


def _empty_hold_row(
    row: Mapping[str, Any],
    *,
    reason: str,
    snapshot_age: float | None,
    traffic_age: float | None,
    weather_offset: float | None,
) -> dict[str, Any]:
    output = {field: None for field in RISK_SCORE_FIELDS}
    output.update(
        {
            "event_id": _text(row.get("event_id")),
            "source_id": _text(row.get("source_id")),
            "event_type": _text(row.get("event_type")),
            "event_code": _text(row.get("event_code")),
            "effective_link_id": _text(row.get("effective_link_id")),
            "road_name": _text(row.get("road_name")),
            "integration_class": _text(row.get("integration_class")),
            "score_version": SCORE_VERSION,
            "scoring_status": "hold",
            "score_available": False,
            "ranking_eligible": False,
            "requires_operator_review": True,
            "snapshot_age_minutes_at_scoring": snapshot_age,
            "traffic_age_minutes_at_scoring": traffic_age,
            "weather_offset_minutes_at_scoring": weather_offset,
            "quality_flags": reason,
        }
    )
    return output


def score_risk_event(
    row: Mapping[str, Any],
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    """Score one integrated event without converting missing evidence to zero."""

    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    snapshot_age = _minutes_between(
        generated_at, _datetime(row.get("snapshot_collected_at"))
    )
    traffic_age = _minutes_between(
        generated_at, _datetime(row.get("traffic_observed_at"))
    )
    weather_offset = _minutes_between(
        generated_at, _datetime(row.get("weather_forecast_at"))
    )
    integration_class = str(row.get("integration_class") or "")
    eligible = _boolean(row.get("scoring_eligible"))

    if not eligible or integration_class == "excluded":
        return _empty_hold_row(
            row,
            reason="hold:excluded_or_not_scoring_eligible",
            snapshot_age=snapshot_age,
            traffic_age=traffic_age,
            weather_offset=weather_offset,
        )
    if (
        snapshot_age is None
        or snapshot_age > SNAPSHOT_MAX_AGE_MINUTES
        or snapshot_age < -MAX_FUTURE_SKEW_MINUTES
    ):
        return _empty_hold_row(
            row,
            reason="hold:snapshot_missing_stale_or_future",
            snapshot_age=snapshot_age,
            traffic_age=traffic_age,
            weather_offset=weather_offset,
        )

    traffic_current = (
        traffic_age is not None
        and -MAX_FUTURE_SKEW_MINUTES <= traffic_age <= TRAFFIC_MAX_AGE_MINUTES
    )
    weather_current = (
        weather_offset is not None
        and abs(weather_offset) <= WEATHER_MAX_OFFSET_MINUTES
    )

    components = {
        "event": score_event_component(row),
        "structural": score_structural_component(row),
        "weather_road": score_weather_road_component(
            row, weather_current=weather_current
        ),
        "traffic": score_traffic_component(row, traffic_current=traffic_current),
    }
    applicable = {
        name: component
        for name, component in components.items()
        if component["status"] != "not_applicable"
    }
    expected_weight = sum(COMPONENT_WEIGHTS[name] for name in applicable)
    evidence_weights = {
        name: COMPONENT_WEIGHTS[name] * float(component["coverage"])
        for name, component in applicable.items()
        if component["score"] is not None
    }
    evidence_weight = sum(evidence_weights.values())
    evidence_coverage = evidence_weight / expected_weight if expected_weight else 0

    if expected_weight <= 0 or evidence_coverage < MIN_EVIDENCE_COVERAGE:
        return _empty_hold_row(
            row,
            reason="hold:insufficient_evidence_coverage",
            snapshot_age=snapshot_age,
            traffic_age=traffic_age,
            weather_offset=weather_offset,
        )

    estimate = sum(
        evidence_weights[name] * float(applicable[name]["score"])
        for name in evidence_weights
    ) / evidence_weight
    lower = sum(
        COMPONENT_WEIGHTS[name] * float(component["lower"])
        for name, component in applicable.items()
    ) / expected_weight
    upper = sum(
        COMPONENT_WEIGHTS[name] * float(component["upper"])
        for name, component in applicable.items()
    ) / expected_weight
    contributions = {
        name: evidence_weights[name] * float(applicable[name]["score"]) / evidence_weight
        for name in evidence_weights
    }

    quality_flags = {
        flag
        for flag in str(row.get("quality_flags") or "").split("|")
        if flag
    }
    if integration_class == "spatial_fallback":
        quality_flags.add("integration:spatial_fallback")
    if not traffic_current:
        quality_flags.add("traffic:missing_or_stale_at_scoring")
    if not weather_current:
        quality_flags.add("weather:missing_or_stale_at_scoring")
    for name, component in applicable.items():
        if float(component["coverage"]) < 1:
            quality_flags.add(f"component:{name}:{component['status']}")
    if weather_component := components.get("weather_road"):
        if weather_component["driver"] == "cits_visibility":
            quality_flags.add("assumption:cits_visibility_unit_meters")

    degraded = bool(quality_flags) or evidence_coverage < 1
    scoring_status = "degraded" if degraded else "usable"
    rounded_score = round(_clamp(estimate), 3)
    rounded_lower = round(_clamp(lower), 3)
    rounded_upper = round(_clamp(upper), 3)
    driver_names = sorted(
        contributions,
        key=lambda name: (-contributions[name], name),
    )[:3]
    risk_drivers = "|".join(
        f"{name}:{applicable[name]['driver']}:{contributions[name]:.3f}"
        for name in driver_names
    )

    event_component = components["event"]
    structural_component = components["structural"]
    weather_component = components["weather_road"]
    traffic_component = components["traffic"]
    output = {
        "risk_rank": None,
        "event_id": _text(row.get("event_id")),
        "source_id": _text(row.get("source_id")),
        "event_type": _text(row.get("event_type")),
        "event_code": _text(row.get("event_code")),
        "effective_link_id": _text(row.get("effective_link_id")),
        "road_name": _text(row.get("road_name")),
        "integration_class": integration_class,
        "score_version": SCORE_VERSION,
        "scoring_status": scoring_status,
        "score_available": True,
        "ranking_eligible": True,
        "requires_operator_review": scoring_status != "usable",
        "risk_score": rounded_score,
        "risk_score_lower_bound": rounded_lower,
        "risk_score_upper_bound": rounded_upper,
        "risk_uncertainty_width": round(rounded_upper - rounded_lower, 3),
        "risk_level": _risk_level(rounded_score),
        "evidence_coverage_ratio": round(evidence_coverage, 6),
        "evidence_weight": round(evidence_weight, 3),
        "expected_weight": round(expected_weight, 3),
        "snapshot_age_minutes_at_scoring": snapshot_age,
        "traffic_age_minutes_at_scoring": traffic_age,
        "weather_offset_minutes_at_scoring": weather_offset,
        "event_component_status": event_component["status"],
        "event_score": event_component["score"],
        "event_weight": (
            COMPONENT_WEIGHTS["event"]
            if event_component["status"] != "not_applicable"
            else None
        ),
        "event_contribution": _rounded(contributions.get("event")),
        "structural_component_status": structural_component["status"],
        "structural_score": structural_component["score"],
        "structural_weight": COMPONENT_WEIGHTS["structural"],
        "structural_contribution": _rounded(contributions.get("structural")),
        "structural_evidence_coverage": structural_component["coverage"],
        "taas_subscore": structural_component["details"].get("taas_subscore"),
        "geometry_subscore": structural_component["details"].get(
            "geometry_subscore"
        ),
        "weather_road_component_status": weather_component["status"],
        "weather_road_score": weather_component["score"],
        "weather_road_weight": COMPONENT_WEIGHTS["weather_road"],
        "weather_road_contribution": _rounded(
            contributions.get("weather_road")
        ),
        "weather_road_driver": weather_component["driver"],
        "traffic_component_status": traffic_component["status"],
        "traffic_score": traffic_component["score"],
        "traffic_weight": COMPONENT_WEIGHTS["traffic"],
        "traffic_contribution": _rounded(contributions.get("traffic")),
        "traffic_driver": traffic_component["driver"],
        "risk_drivers": risk_drivers,
        "quality_flags": "|".join(sorted(quality_flags)),
    }
    return output


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


def score_risk_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Score integrated events and return a reproducibility and safety report."""

    input_rows = [dict(row) for row in rows]
    output_rows = [
        score_risk_event(row, generated_at=generated_at) for row in input_rows
    ]
    ranked_rows = sorted(
        (row for row in output_rows if row["score_available"]),
        key=lambda row: (-float(row["risk_score"]), str(row["event_id"])),
    )
    for rank, row in enumerate(ranked_rows, start=1):
        row["risk_rank"] = rank
    output_rows.sort(
        key=lambda row: (
            row["risk_rank"] is None,
            row["risk_rank"] or 0,
            str(row["event_id"]),
        )
    )

    event_ids = [row.get("event_id") for row in output_rows]
    scored_rows = [row for row in output_rows if row["score_available"]]
    hold_rows = [row for row in output_rows if row["scoring_status"] == "hold"]
    checks = [
        {
            "check_id": "one_output_row_per_input_event",
            "passed": len(output_rows) == len(input_rows),
            "observed": len(output_rows),
            "expected": len(input_rows),
        },
        {
            "check_id": "event_id_uniqueness",
            "passed": len(event_ids) == len(set(event_ids)) and None not in event_ids,
            "unique": len(set(event_ids)),
            "rows": len(event_ids),
        },
        {
            "check_id": "score_range",
            "passed": all(0 <= float(row["risk_score"]) <= 100 for row in scored_rows),
            "scored_rows": len(scored_rows),
        },
        {
            "check_id": "interval_contains_estimate",
            "passed": all(
                float(row["risk_score_lower_bound"])
                <= float(row["risk_score"])
                <= float(row["risk_score_upper_bound"])
                for row in scored_rows
            ),
            "scored_rows": len(scored_rows),
        },
        {
            "check_id": "hold_rows_have_no_score",
            "passed": all(row["risk_score"] is None for row in hold_rows),
            "hold_rows": len(hold_rows),
        },
        {
            "check_id": "excluded_rows_are_held",
            "passed": all(
                row["scoring_status"] == "hold"
                for row in output_rows
                if row["integration_class"] == "excluded"
            ),
            "excluded_rows": sum(
                row["integration_class"] == "excluded" for row in output_rows
            ),
        },
        {
            "check_id": "component_contributions_reconcile",
            "passed": all(
                abs(
                    sum(
                        float(row[field] or 0)
                        for field in (
                            "event_contribution",
                            "structural_contribution",
                            "weather_road_contribution",
                            "traffic_contribution",
                        )
                    )
                    - float(row["risk_score"])
                )
                <= 0.01
                for row in scored_rows
            ),
            "scored_rows": len(scored_rows),
        },
    ]
    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    status_counts = Counter(str(row["scoring_status"]) for row in output_rows)
    level_counts = Counter(
        str(row["risk_level"]) for row in scored_rows if row["risk_level"]
    )
    report = {
        "schema_version": 1,
        "dataset": "roadops_explainable_risk_scores_v0_1",
        "generated_at": generated_at.isoformat(),
        "score_version": SCORE_VERSION,
        "status": "fail" if failed_checks else "pass_with_limitations",
        "grain": "one score row per integrated C-ITS source event",
        "input_rows": len(input_rows),
        "output_rows": len(output_rows),
        "scored_rows": len(scored_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "risk_level_counts": dict(sorted(level_counts.items())),
        "score_distribution": _distribution(row["risk_score"] for row in scored_rows),
        "evidence_coverage_distribution": _distribution(
            row["evidence_coverage_ratio"] for row in scored_rows
        ),
        "uncertainty_width_distribution": _distribution(
            row["risk_uncertainty_width"] for row in scored_rows
        ),
        "policy": {
            "component_weights": COMPONENT_WEIGHTS,
            "structural_subweights": STRUCTURAL_SUBWEIGHTS,
            "event_source_scores": {
                key: value[0] for key, value in EVENT_SOURCE_SCORES.items()
            },
            "taas_grade_scores": TAAS_GRADE_SCORES,
            "risk_level_thresholds": {
                "critical": 75,
                "high": 50,
                "moderate": 25,
                "low": 0,
            },
            "freshness_minutes": {
                "snapshot_max": SNAPSHOT_MAX_AGE_MINUTES,
                "traffic_max": TRAFFIC_MAX_AGE_MINUTES,
                "weather_absolute_offset_max": WEATHER_MAX_OFFSET_MINUTES,
                "future_skew_max": MAX_FUTURE_SKEW_MINUTES,
            },
            "minimum_evidence_coverage": MIN_EVIDENCE_COVERAGE,
            "missingness_rule": (
                "Missing evidence is excluded from the estimate and expands the "
                "lower-upper interval; it is never imputed as zero."
            ),
            "double_count_rule": (
                "TAAS and Jeju Data Hub geometry evidence share one bounded 25-point "
                "structural component at 70:30 rather than being added independently."
            ),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "top_scored_events": [
            {
                "risk_rank": row["risk_rank"],
                "event_id": row["event_id"],
                "source_id": row["source_id"],
                "effective_link_id": row["effective_link_id"],
                "risk_score": row["risk_score"],
                "risk_level": row["risk_level"],
                "scoring_status": row["scoring_status"],
                "risk_drivers": row["risk_drivers"],
            }
            for row in ranked_rows[:10]
        ],
        "limitations": [
            "Weights and thresholds are transparent operational policy defaults, not calibrated accident probabilities.",
            "C-ITS records have no provider event timestamp; snapshot collection time is used and forces degraded status.",
            "Provider event codes are preserved but not assigned code-specific severity without an authoritative code dictionary.",
            "TAAS values are zero-inflated and long-tailed, so v0.1 uses the provider grade rather than raw-value min-max scaling.",
            "Traffic volume is retained but not scored because its aggregation interval and many zero values are not yet validated.",
            "C-ITS visibility is provisionally interpreted as metres; rows driven by it carry an explicit assumption flag until the provider unit is confirmed.",
            "Multiple provider records on one link remain separate events; allocation must avoid duplicate field tasks later.",
        ],
    }
    return output_rows, report
