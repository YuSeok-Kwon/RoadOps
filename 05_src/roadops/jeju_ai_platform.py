"""Auditable connector for Jeju's non-public AI road-control platform API."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from typing import Any, Iterable, Mapping
import urllib.parse
import urllib.request


FIELD_ALIASES = {
    "event_id": ("event_id", "eventId", "detect_id", "detectId", "id"),
    "event_type": ("event_type", "eventType", "detect_type", "detectType", "type"),
    "occurred_at": ("occurred_at", "occurredAt", "detected_at", "detectedAt", "timestamp"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lon", "lng", "x"),
    "status": ("status", "processing_status", "processingStatus"),
    "risk_level": ("risk_level", "riskLevel", "grade", "risk_grade"),
    "road_temperature": ("road_temperature", "roadTemperature", "surface_temp", "surfaceTemp"),
    "salinity": ("salinity", "residual_salinity", "residualSalinity"),
    "image_url": ("image_url", "imageUrl", "photo_url", "photoUrl"),
}

EVENT_TYPE_LABELS = {
    "pothole": "포트홀",
    "road_damage": "도로 파손",
    "fallen_object": "낙하물",
    "debris": "낙하물",
    "black_ice": "도로 결빙",
    "icing": "도로 결빙",
    "snow": "적설",
}


def _pick(row: Mapping[str, Any], field: str) -> Any:
    for alias in FIELD_ALIASES[field]:
        value = row.get(alias)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    for key in ("records", "items", "events", "data", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, Mapping)]
        if isinstance(value, Mapping):
            nested = extract_records(value)
            if nested:
                return nested
    return []


def normalize_platform_events(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    materialized = [dict(row) for row in records]
    output = []
    rejected = Counter()
    for index, raw in enumerate(materialized):
        latitude = _float(_pick(raw, "latitude"))
        longitude = _float(_pick(raw, "longitude"))
        event_id = str(_pick(raw, "event_id") or "").strip()
        event_type_raw = str(_pick(raw, "event_type") or "").strip()
        if not event_id:
            rejected["missing_event_id"] += 1
            continue
        if latitude is None or longitude is None:
            rejected["missing_coordinate"] += 1
            continue
        if not (33.0 <= latitude <= 34.0 and 126.0 <= longitude <= 127.2):
            rejected["outside_jeju_bounds"] += 1
            continue
        output.append(
            {
                "event_id": event_id,
                "source_id": "jeju_ai_road_control_platform",
                "source_record_index": index,
                "event_type_raw": event_type_raw or None,
                "event_type_label": EVENT_TYPE_LABELS.get(event_type_raw.lower(), event_type_raw or "유형 확인 필요"),
                "occurred_at": _pick(raw, "occurred_at"),
                "latitude": latitude,
                "longitude": longitude,
                "status": _pick(raw, "status"),
                "risk_level": _pick(raw, "risk_level"),
                "road_temperature": _float(_pick(raw, "road_temperature")),
                "residual_salinity": _float(_pick(raw, "salinity")),
                "image_url": _pick(raw, "image_url"),
                "fetched_at": fetched_at,
                "integration_status": "awaiting_standard_link_spatial_match",
            }
        )
    return output, {
        "source_record_count": len(materialized),
        "normalized_record_count": len(output),
        "rejected_counts": dict(sorted(rejected.items())),
        "observed_event_type_counts": dict(sorted(Counter(row["event_type_label"] for row in output).items())),
    }


def fetch_platform_json(
    endpoint_url: str,
    token: str,
    *,
    timeout_seconds: float = 30.0,
    allow_insecure_http: bool = False,
) -> tuple[Any, dict[str, Any]]:
    parsed = urllib.parse.urlparse(endpoint_url)
    if parsed.scheme not in ({"https"} if not allow_insecure_http else {"http", "https"}):
        raise ValueError("platform_endpoint_requires_https")
    if not parsed.hostname:
        raise ValueError("platform_endpoint_hostname_missing")
    request = urllib.request.Request(
        endpoint_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "RoadOps-Jeju/0.1",
        },
    )
    started = datetime.now().astimezone()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        http_status = getattr(response, "status", None)
    try:
        payload = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("platform_response_not_json") from exc
    return payload, {
        "status": "response_received",
        "http_status": http_status,
        "content_type": content_type,
        "fetched_at": started.isoformat(),
        "endpoint_host": parsed.hostname,
        "credential_exposed": False,
    }
