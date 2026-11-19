"""Build a gated Jeju airport and ferry inflow-pressure feature."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import math
import re
from statistics import median
from typing import Any, Iterable, Mapping


GATEWAYS = (
    {"gateway_id": "jeju_airport", "mode": "air", "latitude": 33.5104, "longitude": 126.49135},
    {"gateway_id": "jeju_port", "mode": "sea", "latitude": 33.5219, "longitude": 126.5430},
    {"gateway_id": "seogwipo_port", "mode": "sea", "latitude": 33.2387, "longitude": 126.5612},
)


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _jeju_signal(row: Mapping[str, Any]) -> bool:
    return any(
        signal in str(value or "").upper()
        for value in row.values()
        for signal in ("CJU", "제주", "JEJU")
    )


def _hour(row: Mapping[str, Any], fields: Iterable[str]) -> int | None:
    for field in fields:
        text = str(row.get(field) or "").strip()
        if not text:
            continue
        if text.isdigit() and len(text) <= 2:
            value = int(text)
            if 0 <= value <= 23:
                return value
        matches = re.findall(r"(?<!\d)([01]?\d|2[0-3])(?::?\d{2})?(?!\d)", text)
        if matches:
            return int(matches[-1])
        if text.isdigit() and len(text) >= 10:
            value = int(text[-6:-4])
            if 0 <= value <= 23:
                return value
    return None


def _field_value(row: Mapping[str, Any], fields: Iterable[str]) -> float | None:
    for field in fields:
        value = _number(row.get(field))
        if value is not None and value >= 0:
            return value
    return None


def build_gateway_pressure(
    records_by_source: Mapping[str, Iterable[Mapping[str, Any]]],
    audit_report: Mapping[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    audit_by_source = {
        str(row.get("source_id")): dict(row)
        for row in audit_report.get("sources", [])
    }
    passenger_audit = audit_by_source.get("kac_hourly_arrival_passengers", {})
    passenger_rows = [
        dict(row)
        for row in records_by_source.get("kac_hourly_arrival_passengers", [])
        if _jeju_signal(row)
    ]
    passenger_fields = passenger_audit.get("passenger_fields", [])
    time_fields = passenger_audit.get("time_fields", [])
    hourly_counts: defaultdict[int, float] = defaultdict(float)
    rejected_passenger_rows = Counter()
    for row in passenger_rows:
        hour = _hour(row, time_fields)
        count = _field_value(row, passenger_fields)
        if hour is None:
            rejected_passenger_rows["hour_unavailable"] += 1
            continue
        if count is None:
            rejected_passenger_rows["passenger_count_unavailable"] += 1
            continue
        hourly_counts[hour] += count

    positive = [value for value in hourly_counts.values() if value > 0]
    baseline = median(positive) if positive else None
    hourly_pressure = []
    if baseline and baseline > 0:
        for hour in range(24):
            count = hourly_counts.get(hour)
            if count is None:
                continue
            ratio = count / baseline
            hourly_pressure.append(
                {
                    "hour": hour,
                    "passenger_count": round(count, 3),
                    "baseline_hourly_passengers": round(baseline, 3),
                    "passenger_ratio": round(ratio, 4),
                    "pressure_index": round(min(1.0, max(0.0, ratio - 1.0)), 4),
                }
            )

    flight_audit = audit_by_source.get("kac_realtime_flights", {})
    flight_rows = [
        dict(row)
        for row in records_by_source.get("kac_realtime_flights", [])
        if _jeju_signal(row)
    ]
    status_fields = flight_audit.get("status_fields", [])
    disrupted = sum(
        any(
            token in str(row.get(field) or "").lower()
            for field in status_fields
            for token in ("cancel", "delay", "취소", "지연", "결항")
        )
        for row in flight_rows
    )
    disruption_ratio = disrupted / len(flight_rows) if flight_rows else None

    ferry_audit = audit_by_source.get("komsa_ferry_schedule", {})
    ferry_rows = [
        dict(row)
        for row in records_by_source.get("komsa_ferry_schedule", [])
        if _jeju_signal(row)
    ]
    capacity_fields = ferry_audit.get("capacity_fields", [])
    ferry_capacity = sum(
        value
        for row in ferry_rows
        if (value := _field_value(row, capacity_fields)) is not None
    )
    ferry_status_fields = ferry_audit.get("status_fields", [])
    controlled_ferries = sum(
        any(str(row.get(field) or "").strip() not in {"", "0", "정상"} for field in ferry_status_fields)
        for row in ferry_rows
    )

    required_sources = ("kac_realtime_flights", "kac_hourly_arrival_passengers")
    source_readiness = {
        source_id: audit_by_source.get(source_id, {}).get("readiness", "missing_audit")
        for source_id in audit_by_source
    }
    air_ready = bool(hourly_pressure) and all(
        source_readiness.get(source_id) == "ready_for_feature_spike"
        for source_id in required_sources
    )
    sea_ready = bool(ferry_rows) and source_readiness.get("komsa_ferry_schedule") == "ready_for_feature_spike"
    status = "available" if air_ready and sea_ready else "partial" if air_ready else "unavailable"
    return {
        "schema_version": 1,
        "dataset": "jeju_gateway_inflow_pressure",
        "generated_at": generated_at,
        "status": status,
        "semantics": "operational_access_pressure_not_population_or_accident_probability",
        "airport": {
            "status": "available" if air_ready else "unavailable",
            "hourly_pressure": hourly_pressure,
            "flight_count": len(flight_rows),
            "disrupted_flight_count": disrupted,
            "disruption_ratio": round(disruption_ratio, 4) if disruption_ratio is not None else None,
            "rejected_passenger_rows": dict(sorted(rejected_passenger_rows.items())),
        },
        "ferry": {
            "status": "available" if sea_ready else "unavailable",
            "schedule_count": len(ferry_rows),
            "scheduled_capacity_proxy": round(ferry_capacity, 3) if ferry_capacity else None,
            "controlled_schedule_count": controlled_ferries,
            "actual_passenger_count_available": False,
        },
        "source_readiness": source_readiness,
        "score_gate": {
            "airport_requires_hourly_passengers_and_realtime_flights": True,
            "ferry_capacity_is_context_only": True,
            "maximum_priority_point_contribution": 6.0,
            "maximum_gateway_distance_km": 20.0,
        },
    }


def _distance_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    radius = 6371.0088
    lat1 = math.radians(latitude_a)
    lat2 = math.radians(latitude_b)
    dlat = lat2 - lat1
    dlon = math.radians(longitude_b - longitude_a)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def gateway_contribution(
    event: Mapping[str, Any],
    pressure: Mapping[str, Any] | None,
    *,
    target_at: datetime,
) -> dict[str, Any]:
    if not pressure or pressure.get("status") not in {"available", "partial"}:
        return {"status": "unavailable", "pressure": None, "contribution": 0.0}
    latitude = _number(event.get("event_latitude"))
    longitude = _number(event.get("event_longitude"))
    if latitude is None or longitude is None:
        return {"status": "event_coordinate_unavailable", "pressure": None, "contribution": 0.0}
    hourly = {
        int(row["hour"]): row
        for row in pressure.get("airport", {}).get("hourly_pressure", [])
        if row.get("hour") is not None
    }
    row = hourly.get(target_at.hour)
    if not row:
        return {"status": "target_hour_unavailable", "pressure": None, "contribution": 0.0}
    airport = next(item for item in GATEWAYS if item["gateway_id"] == "jeju_airport")
    distance = _distance_km(latitude, longitude, airport["latitude"], airport["longitude"])
    exposure = max(0.0, 1.0 - distance / 20.0)
    pressure_index = float(row.get("pressure_index") or 0)
    disruption = float(pressure.get("airport", {}).get("disruption_ratio") or 0)
    combined = min(1.0, pressure_index * 0.85 + disruption * 0.15)
    contribution = round(6.0 * combined * exposure, 3)
    return {
        "status": "applied" if contribution > 0 else "available_no_positive_pressure",
        "pressure": round(combined, 4),
        "contribution": contribution,
        "nearest_gateway_id": "jeju_airport",
        "distance_km": round(distance, 3),
        "spatial_exposure": round(exposure, 4),
        "passenger_count": row.get("passenger_count"),
        "baseline_hourly_passengers": row.get("baseline_hourly_passengers"),
    }
