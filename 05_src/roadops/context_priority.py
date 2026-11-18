"""Inspectable 0–100 reference signals for operator-defined priority scoring.

Policy defaults are not fitted accident or crime probabilities.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

POLICY_VERSION = "roadops-context-v0.2"
HOTSPOT_RADIUS_KM = 1.0
HOTSPOT_MAX_POINTS = 100.0
HISTORY_MAX_POINTS = 100.0
SAFETY_MAX_POINTS = 100.0
PATROL_GROUPS = {"강력범죄", "절도범죄", "폭력범죄"}


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return None
    return parsed if math.isfinite(parsed) else None


def timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def point(row: Mapping[str, Any], prefix: str = "") -> tuple[float, float] | None:
    lat, lon = number(row.get(f"{prefix}latitude")), number(row.get(f"{prefix}longitude"))
    return (lat, lon) if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 else None


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat_a, lat_b = math.radians(a[0]), math.radians(b[0])
    delta_lat, delta_lon = lat_b - lat_a, math.radians(b[1] - a[1])
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, value)))


def evidence(key: str, label: str, status: str, detail: str, points: float | None = None, **facts: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status,
            "value": round(points, 6) if points is not None else None, "coverage": 1.0 if points is not None else 0.0,
            "description": detail, **facts}


def usable_dataset(dataset: Mapping[str, Any] | None, as_of: datetime) -> bool:
    if not dataset or dataset.get("status") in {"fail", "unavailable", "connection_failed"}:
        return False
    generated = timestamp(dataset.get("generated_at") or dataset.get("current_observed_at"))
    return generated is not None and generated <= as_of


def accident_evidence(event: Mapping[str, Any], scored: Mapping[str, Any], dataset: Mapping[str, Any] | None, as_of: datetime) -> dict[str, Any]:
    label = "주변 교통사고 다발지역"
    location = point(event, "event_")
    if not location or not usable_dataset(dataset, as_of):
        return evidence("accident_hotspot", label, "unavailable", "도로 위치 또는 사고다발지역 자료가 없어 보정하지 않았습니다.")
    candidates = []
    for row in dataset.get("records", []):
        year, count, coordinates = number(row.get("analysis_year")), number(row.get("accident_count")), point(row)
        if coordinates and year is not None and as_of.year - 3 <= year < as_of.year and count is not None and count >= 0:
            distance = distance_km(location, coordinates)
            signal = HOTSPOT_MAX_POINTS * max(0, 1 - distance / HOTSPOT_RADIUS_KM) * min(1, count / 40)
            candidates.append((signal, distance, row))
    if not candidates:
        return evidence("accident_hotspot", label, "unavailable", "최근 분석연도의 유효한 사고다발지역 자료가 없습니다.")
    signal, distance, row = max(candidates, key=lambda item: (item[0], -item[1]))
    increment = signal
    if distance >= HOTSPOT_RADIUS_KM:
        detail = f"도로 위치 1km 이내에 제공자료의 사고다발지역이 없습니다. 최근접 지역은 {distance:.1f}km입니다."
    else:
        detail = (f"{row['location_name']} · {distance:.2f}km · {int(row['analysis_year'])}년 사고 {int(row['accident_count'])}건. "
                  f"거리감쇠 × 사고건수/40(최대 1) × 100으로 항목지수를 계산합니다.")
    return evidence("accident_hotspot", label, "applied" if increment > 0 else "no_addition", detail, increment,
                    source="한국도로교통공단 사고다발지역", hotspot_id=row.get("hotspot_id"), distance_km=round(distance, 3),
                    radius_km=HOTSPOT_RADIUS_KM)


def history_evidence(event: Mapping[str, Any], dataset: Mapping[str, Any] | None, as_of: datetime, horizon: int) -> dict[str, Any]:
    label = "과거 유사상황의 사건 장소"
    if not usable_dataset(dataset, as_of) or "scoring_records" not in dataset:
        return evidence("similar_history", label, "unavailable", "날짜별로 검토할 수 있는 과거 수집 이력이 없습니다.")
    link = str(event.get("effective_link_id") or "")
    if not link:
        return evidence("similar_history", label, "unavailable", "과거 사건과 연결할 도로구간 번호가 없습니다.")
    daily_matches: dict[str, float] = {}
    eligible_days = set()
    for row in dataset["scoring_records"]:
        observed = timestamp(row.get("observed_at"))
        similarity, coverage = number(row.get("similarity_score")), number(row.get("evidence_coverage_ratio"))
        if (not observed or not timedelta(days=1) <= as_of - observed <= timedelta(days=90)
                or row.get("event_snapshot_available") is not True
                or similarity is None or not 80 <= similarity <= 100 or coverage is None or not .6 <= coverage <= 1):
            continue
        day = observed.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        eligible_days.add(day)
        if link in {str(value) for value in row.get("event_link_ids", [])}:
            daily_matches[day] = max(daily_matches.get(day, 0), similarity * coverage / 100)
    if not eligible_days:
        return evidence("similar_history", label, "unavailable", "24시간 이전·최근 90일의 유사도 80% 이상 기록이 부족합니다. 당일 반복 수집은 가산하지 않습니다.")
    points = HISTORY_MAX_POINTS * min(1, sum(daily_matches.values()) / 3)
    detail = (f"비교 가능한 {len(eligible_days)}일 중 같은 도로의 사건 기록 {len(daily_matches)}일. "
              "하루 한 번만 세며 유사도·근거 반영률로 조정하고 3일 상당을 항목지수 100으로 환산합니다.")
    if horizon:
        detail += " 현재 상황과의 유사도를 유지한 예측 시나리오입니다."
    return evidence("similar_history", label, "applied" if points else "no_addition", detail, points,
                    source="C-ITS 과거 노면기상·도로 돌발정보", matched_days=sorted(daily_matches), compared_days=len(eligible_days))


def safety_evidence(event: Mapping[str, Any], dataset: Mapping[str, Any] | None, locations: Mapping[str, str], as_of: datetime) -> dict[str, Any]:
    label = "생활안전 순찰 수요"
    city = locations.get(str(event.get("effective_link_id") or ""))
    if not city or not usable_dataset(dataset, as_of):
        return evidence("city_safety", label, "unavailable", "도로의 행정시 또는 시 단위 생활안전 통계가 없습니다.")
    totals = {}
    years = set()
    for row in dataset.get("records", []):
        name, year = row.get("administrative_city"), number(row.get("analysis_year"))
        if name not in {"제주시", "서귀포시"} or year is None or not as_of.year - 3 <= year < as_of.year:
            continue
        counts = {item.get("crime_group"): number(item.get("occurrence_count")) for item in row.get("major_categories", [])}
        if all(counts.get(group) is not None and counts[group] >= 0 for group in PATROL_GROUPS):
            totals[name] = sum(counts[group] for group in PATROL_GROUPS)
            years.add(int(year))
    if city not in totals or len(totals) != 2 or len(years) != 1 or sum(totals.values()) <= 0:
        return evidence("city_safety", label, "unavailable", "동일 연도의 두 행정시 통계가 부족해 생활안전 수요를 비교하지 않았습니다.")
    share = totals[city] / sum(totals.values())
    detail = (f"{next(iter(years))}년 {city} 강력·절도·폭력 {int(totals[city]):,}건, 제주 두 행정시 합계의 {share:.1%}. "
              "시 단위 업무량 비중을 0–100으로 환산하며, 같은 시의 도로에는 동일하게 적용합니다. 도로별 범죄위험·인구당 발생률은 아닙니다.")
    return evidence("city_safety", label, "applied", detail, SAFETY_MAX_POINTS * share,
                    source="경찰청 행정시별 범죄 통계", administrative_city=city, city_share=round(share, 6))


def reference_signals(event: Mapping[str, Any], scored: Mapping[str, Any], *, as_of: datetime, horizon: int,
                      accident_hotspots: Mapping[str, Any] | None = None, historical_similarity: Mapping[str, Any] | None = None,
                      crime_statistics: Mapping[str, Any] | None = None, link_cities: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    return [accident_evidence(event, scored, accident_hotspots, as_of),
            history_evidence(event, historical_similarity, as_of, horizon),
            safety_evidence(event, crime_statistics, link_cities or {}, as_of)]
