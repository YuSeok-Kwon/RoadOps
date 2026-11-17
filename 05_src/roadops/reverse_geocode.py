"""Cached reverse geocoding for human-readable RoadOps link locations."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "RoadOps-Jeju-research/0.1 (local public-sector hackathon prototype)"


def midpoint(parts: Iterable[Iterable[Iterable[float]]]) -> tuple[float, float] | None:
    points = [point for part in parts for point in part if len(point) >= 2]
    if not points:
        return None
    longitude, latitude = points[len(points) // 2][:2]
    return float(latitude), float(longitude)


def location_from_nominatim(payload: Mapping[str, Any], *, road_name: str | None = None) -> dict[str, Any]:
    address = dict(payload.get("address") or {})
    city = address.get("city") or address.get("county")
    unit = (
        address.get("village")
        or address.get("town")
        or address.get("city_district")
        or address.get("suburb")
        or address.get("quarter")
    )
    road = address.get("road") or road_name
    house_number = address.get("house_number")
    detail = " ".join(str(value) for value in (city, unit, road, house_number) if value)
    return {
        "location_label": detail or payload.get("display_name") or "위치 확인 필요",
        "display_address": payload.get("display_name"),
        "administrative_city": city,
        "administrative_unit": unit,
        "road_name_geocoded": road,
        "lot_or_house_number": house_number,
        "address_precision": "parcel_or_building" if house_number else "road_or_locality",
        "intersection_name": None,
        "provider": "OpenStreetMap Nominatim",
        "provider_place_id": payload.get("place_id"),
    }


def reverse_nominatim(
    latitude: float,
    longitude: float,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "lat": f"{latitude:.8f}",
            "lon": f"{longitude:.8f}",
            "format": "jsonv2",
            "addressdetails": 1,
            "accept-language": "ko",
            "zoom": 18,
        }
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


def enrich_link_locations(
    link_points: Iterable[Mapping[str, Any]],
    *,
    cache_path: Path,
    request_delay_seconds: float = 1.1,
    timeout_seconds: float = 30.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache: dict[str, Any] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    cache_misses = 0
    failures: list[dict[str, str]] = []
    for row in link_points:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        cache_key = f"{latitude:.6f},{longitude:.6f}"
        payload = cache.get(cache_key)
        if payload is None:
            if cache_misses:
                time.sleep(request_delay_seconds)
            try:
                payload = reverse_nominatim(latitude, longitude, timeout_seconds=timeout_seconds)
            except Exception as exc:  # provider/network boundary
                failures.append({"link_id": str(row["link_id"]), "reason": type(exc).__name__})
                continue
            cache[cache_key] = payload
            cache_misses += 1
        records.append(
            {
                "link_id": str(row["link_id"]),
                "latitude": latitude,
                "longitude": longitude,
                **location_from_nominatim(payload, road_name=str(row.get("road_name") or "") or None),
            }
        )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(cache_path)
    return records, {
        "status": "pass" if records and not failures else "pass_with_limitations" if records else "unavailable",
        "record_count": len(records),
        "cache_hit_count": len(records) - cache_misses,
        "cache_miss_count": cache_misses,
        "failure_count": len(failures),
        "failures": failures,
        "exact_parcel_or_building_count": sum(row["address_precision"] == "parcel_or_building" for row in records),
        "road_or_locality_count": sum(row["address_precision"] == "road_or_locality" for row in records),
    }
