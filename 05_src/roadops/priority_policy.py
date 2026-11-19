"""Operator-owned weights; the dashboard and batch forecasts share this contract."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .context_priority import number, reference_signals
from .risk_scoring import (
    score_event_component, score_structural_component, score_weather_road_component,
    score_traffic_component, TRAFFIC_MAX_AGE_MINUTES, WEATHER_MAX_OFFSET_MINUTES,
    MAX_FUTURE_SKEW_MINUTES,
)

VERSION = "roadops-operator-priority-v0.2"
LABELS = {
    "event": "현재 도로 위험상황", "structural": "과거 사고·도로 구조",
    "weather_road": "기상·노면 상태", "traffic": "실시간 교통",
    "gateway": "공항 유입", "accident_hotspot": "주변 사고다발지역",
    "similar_history": "과거 유사상황", "city_safety": "생활안전 순찰 수요",
}
DESCRIPTIONS = {
    "event": "돌발 70 · 통제 90 · 작업 55의 항목지수. 해당 정보가 없는 유형은 적용 대상에서 제외합니다.",
    "structural": "TAAS 위험등급(10·40·70·100)과 도로 선형 심각도를 7:3으로 결합합니다.",
    "weather_road": "비·눈·바람과 가시거리·마찰 등 확인된 위험 신호 중 가장 높은 항목지수입니다.",
    "traffic": "제한속도 대비 통행속도 저하와 점유율 중 높은 항목지수입니다. 미래 교통값은 추정하지 않습니다.",
    "gateway": "시간대별 공항 유입·운항차질 지수에 공항에서 20km까지의 거리감쇠를 적용합니다.",
}


def validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if policy.get("version") != VERSION or policy.get("method") not in {"available", "complete"}:
        raise ValueError("지원하지 않는 점수 계산 방식입니다.")
    weights = policy.get("weights", {})
    if set(weights) != set(LABELS):
        raise ValueError("점수 항목이 일치하지 않습니다.")
    parsed = {key: number(weights[key]) for key in LABELS}
    if any(value is None or not 0 <= value <= 100 for value in parsed.values()):
        raise ValueError("배점은 0~100의 유한한 숫자여야 합니다.")
    if abs(sum(parsed.values()) - 100) > 1e-6:
        raise ValueError("선택한 항목의 배점 합계는 100점이어야 합니다.")
    if not any(parsed[key] > 0 for key in ("event", "structural", "weather_road", "traffic")):
        raise ValueError("도로 관련 항목을 하나 이상 포함하세요.")
    return {"version": VERSION, "method": policy["method"], "weights": parsed}


def policy_id(policy: Mapping[str, Any]) -> str:
    normalized = validate_policy(policy)
    return VERSION + ":" + hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()[:12]


def build_priority_inputs(event, scored, gateway, *, as_of, horizon, **references):
    traffic_age = number(scored.get("traffic_age_minutes_at_scoring"))
    weather_offset = number(scored.get("weather_offset_minutes_at_scoring"))
    components = {
        "event": score_event_component(event),
        "structural": score_structural_component(event),
        "weather_road": score_weather_road_component(event, weather_current=weather_offset is not None and abs(weather_offset) <= WEATHER_MAX_OFFSET_MINUTES),
        "traffic": score_traffic_component(event, traffic_current=traffic_age is not None and -MAX_FUTURE_SKEW_MINUTES <= traffic_age <= TRAFFIC_MAX_AGE_MINUTES),
    }
    factors = [{"key": key, "label": LABELS[key], "value": component["score"],
                "coverage": component["coverage"], "status": component["status"],
                "driver": component["driver"], "description": DESCRIPTIONS[key]}
               for key, component in components.items()]
    weather_fields = {
        "kma_wind_speed": ("weather_wind_speed_mps", "풍속", "m/s"),
        "kma_precipitation_type": ("weather_precipitation_type", "강수형태 코드", ""),
        "kma_rainfall_1h": ("weather_rainfall_1h_raw", "시간당 강수량", ""),
        "cits_visibility": ("cits_visibility", "가시거리", "m 가정"),
        "cits_friction": ("cits_friction", "노면 마찰계수", ""),
        "cits_road_temperature": ("cits_road_temperature", "노면온도", "°C"),
        "cits_snow": ("cits_snow", "적설 센서값", ""),
        "cits_water_film": ("cits_water_film", "수막 센서값", ""),
    }
    weather_driver = components["weather_road"]["driver"]
    for row in factors:
        if row["key"] == "weather_road" and weather_driver in weather_fields:
            field, label, unit = weather_fields[weather_driver]
            row["description"] += f" 이 도로의 주요 근거: {label} {event.get(field)}{unit}."
        elif row["key"] == "traffic" and row["value"] is not None:
            if row["driver"] == "speed_to_limit_ratio":
                row["description"] += f" 통행속도 {event.get('traffic_speed_kph')}km/h, 제한속도 {event.get('maximum_speed_limit')}km/h."
            else:
                row["description"] += f" 점유율 {event.get('traffic_occupancy_rate')}%."
        elif row["key"] == "structural" and row["value"] is not None:
            detail = components["structural"]["details"]
            row["description"] += f" TAAS 항목지수 {detail.get('taas_subscore') if detail.get('taas_subscore') is not None else '미확인'}, 도로 선형 항목지수 {detail.get('geometry_subscore') if detail.get('geometry_subscore') is not None else '미확인'}."
    gateway_available = gateway["status"] in {"applied", "available_no_positive_pressure"}
    factors.append({"key": "gateway", "label": LABELS["gateway"],
                    "value": (float(gateway["contribution"]) / 6 * 100) if gateway_available else None,
                    "coverage": 1 if gateway_available else 0, "status": gateway["status"],
                    "description": DESCRIPTIONS["gateway"]})
    factors.extend(reference_signals(event, scored, as_of=as_of, horizon=horizon, **references))
    # A different weighting may resolve low coverage, but cannot rescue stale or excluded inputs.
    flags = str(scored.get("quality_flags") or "")
    blocked = not scored.get("score_available") and "hold:insufficient_evidence_coverage" not in flags
    return {"event_id": event.get("event_id"), "event_type": event.get("event_type"),
            "blocked": blocked, "factors": factors}


def calculate_priority(inputs: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    policy = validate_policy(policy)
    factors = []
    originals = {row["key"]: row for row in inputs.get("factors", [])}
    for key, weight in policy["weights"].items():
        row = dict(originals.get(key, {"key": key, "label": LABELS[key], "value": None, "coverage": 0, "status": "unavailable", "description": "자료가 없습니다."}))
        value = number(row.get("value"))
        coverage = number(row.get("coverage")) or 0
        if value is None or not 0 <= value <= 100 or not 0 <= coverage <= 1:
            value, coverage = None, 0
        # Both sources describe past accidents: only the incremental hotspot signal is added.
        if key == "accident_hotspot" and weight > 0 and policy["weights"]["structural"] > 0 and value is not None:
            structural = number(originals.get("structural", {}).get("value"))
            if structural is not None:
                row["overlap_deduction"] = min(value, max(0, structural))
                value = max(0, value - structural)
                row["description"] += " 과거 사고·도로 구조와 함께 선택해 겹치는 항목지수를 차감했습니다."
        row.update(value=value, coverage=coverage, weight=weight, contribution=None)
        if weight == 0:
            row["status"] = "excluded"
        factors.append(row)
    applicable = [row for row in factors if row["weight"] > 0 and row["status"] != "not_applicable"]
    expected = sum(row["weight"] for row in applicable)
    observed = sum(row["weight"] * row["coverage"] for row in applicable if row["value"] is not None)
    coverage = observed / expected if expected else 0
    threshold = 1 - 1e-9 if policy["method"] == "complete" else .6 - 1e-9
    road_evidence = any(row["key"] in {"event", "structural", "weather_road", "traffic"} and row["value"] is not None and row["coverage"] > 0 for row in applicable)
    available = not inputs.get("blocked") and coverage >= threshold and observed > 0 and road_evidence
    score = None
    if available:
        for row in applicable:
            if row["value"] is not None:
                row["contribution"] = round(row["weight"] * row["coverage"] * row["value"] / observed, 6)
        score = round(sum(row["contribution"] or 0 for row in factors), 3)
    lower = sum(row["weight"] * row["coverage"] * (row["value"] or 0) for row in applicable) / expected if expected else None
    upper = lower + (1 - coverage) * 100 if lower is not None else None
    return {"score": score, "available": available, "coverage": round(coverage, 6), "factors": factors,
            "lower": round(lower, 3) if available else None, "upper": round(upper, 3) if available else None,
            "method": policy["method"], "policy_id": policy_id(policy)}
