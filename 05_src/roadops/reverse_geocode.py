"""Cached reverse geocoding for human-readable RoadOps link locations."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
SGIS_AUTH_URL = "https://sgisapi.mods.go.kr/OpenAPI3/auth/authentication.json"
SGIS_REVERSE_URL = "https://sgisapi.mods.go.kr/OpenAPI3/addr/rgeocodewgs84.json"
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


def _fetch_json(url: str, params: Mapping[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


def sgis_access_token(
    consumer_key: str,
    consumer_secret: str,
    *,
    timeout_seconds: float = 30.0,
) -> str:
    payload = _fetch_json(
        SGIS_AUTH_URL,
        {"consumer_key": consumer_key, "consumer_secret": consumer_secret},
        timeout_seconds=timeout_seconds,
    )
    if str(payload.get("errCd")) not in {"0", "None"}:
        raise RuntimeError(f"sgis_auth_error:{payload.get('errCd')}:{payload.get('errMsg')}")
    token = (payload.get("result") or {}).get("accessToken")
    if not token:
        raise RuntimeError("sgis_access_token_missing")
    return str(token)


def reverse_sgis(
    latitude: float,
    longitude: float,
    *,
    access_token: str,
    address_type: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    payload = _fetch_json(
        SGIS_REVERSE_URL,
        {
            "accessToken": access_token,
            "x_coor": f"{longitude:.8f}",
            "y_coor": f"{latitude:.8f}",
            "addr_type": address_type,
        },
        timeout_seconds=timeout_seconds,
    )
    if str(payload.get("errCd")) != "0":
        raise RuntimeError(f"sgis_reverse_error:{payload.get('errCd')}:{payload.get('errMsg')}")
    return payload


def _sgis_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, list):
        return dict(result[0]) if result and isinstance(result[0], Mapping) else {}
    if isinstance(result, Mapping):
        for key in ("resultdata", "results", "data"):
            nested = result.get(key)
            if isinstance(nested, list) and nested and isinstance(nested[0], Mapping):
                return dict(nested[0])
        return dict(result)
    return {}


def location_from_sgis(
    parcel_payload: Mapping[str, Any],
    road_payload: Mapping[str, Any],
    *,
    road_name: str | None = None,
) -> dict[str, Any]:
    parcel = _sgis_record(parcel_payload)
    road = _sgis_record(road_payload)
    city = parcel.get("sgg_nm") or road.get("sgg_nm")
    unit = parcel.get("emdong_nm") or road.get("emdong_nm")
    main_no = str(parcel.get("main_no") or "").strip()
    sub_no = str(parcel.get("sub_no") or "").strip()
    lot_number = "-".join(value for value in (main_no, sub_no) if value and value != "0") or None
    official_road = road.get("road_nm") or road_name
    road_main = str(road.get("road_nm_main_no") or "").strip()
    road_sub = str(road.get("road_nm_sub_no") or "").strip()
    road_number = "-".join(value for value in (road_main, road_sub) if value and value != "0") or None
    detail = " ".join(str(value) for value in (city, unit, official_road, road_number or lot_number) if value)
    return {
        "location_label": detail or parcel.get("full_addr") or road.get("full_addr") or "위치 확인 필요",
        "display_address": road.get("full_addr") or parcel.get("full_addr"),
        "administrative_city": city,
        "administrative_unit": unit,
        "road_name_geocoded": official_road,
        "lot_or_house_number": lot_number or road_number,
        "address_precision": "official_parcel" if lot_number else "official_road_address" if road_number else "official_locality",
        "intersection_name": None,
        "provider": "SGIS 국가데이터처",
        "provider_place_id": parcel.get("adm_dr_cd") or road.get("road_cd"),
    }


def enrich_link_locations(
    link_points: Iterable[Mapping[str, Any]],
    *,
    cache_path: Path,
    request_delay_seconds: float = 1.1,
    timeout_seconds: float = 30.0,
    sgis_consumer_key: str | None = None,
    sgis_consumer_secret: str | None = None,
    sgis_cache_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache: dict[str, Any] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    sgis_cache: dict[str, Any] = {}
    if sgis_cache_path and sgis_cache_path.exists():
        sgis_cache = json.loads(sgis_cache_path.read_text(encoding="utf-8"))
    sgis_token = None
    sgis_auth_error = None
    if sgis_consumer_key and sgis_consumer_secret:
        try:
            sgis_token = sgis_access_token(
                sgis_consumer_key,
                sgis_consumer_secret,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # provider boundary
            sgis_auth_error = type(exc).__name__
    cache_misses = 0
    sgis_cache_misses = 0
    official_count = 0
    failures: list[dict[str, str]] = []
    for row in link_points:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        cache_key = f"{latitude:.6f},{longitude:.6f}"
        if sgis_token:
            official_payloads = sgis_cache.get(cache_key)
            if not isinstance(official_payloads, Mapping):
                official_payloads = {}
            for payload_name, address_type in (("parcel", 21), ("road", 10)):
                if payload_name in official_payloads:
                    continue
                if sgis_cache_misses:
                    time.sleep(request_delay_seconds)
                try:
                    official_payloads[payload_name] = reverse_sgis(
                        latitude,
                        longitude,
                        access_token=sgis_token,
                        address_type=address_type,
                        timeout_seconds=timeout_seconds,
                    )
                    sgis_cache_misses += 1
                except Exception as exc:  # fall through to public map provider
                    failures.append(
                        {
                            "link_id": str(row["link_id"]),
                            "reason": f"sgis_{payload_name}:{type(exc).__name__}",
                        }
                    )
            if official_payloads:
                sgis_cache[cache_key] = official_payloads
                records.append(
                    {
                        "link_id": str(row["link_id"]),
                        "latitude": latitude,
                        "longitude": longitude,
                        **location_from_sgis(
                            official_payloads.get("parcel", {}),
                            official_payloads.get("road", {}),
                            road_name=str(row.get("road_name") or "") or None,
                        ),
                    }
                )
                official_count += 1
                continue
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
    if sgis_cache_path:
        sgis_cache_path.parent.mkdir(parents=True, exist_ok=True)
        sgis_temporary = sgis_cache_path.with_suffix(sgis_cache_path.suffix + ".tmp")
        sgis_temporary.write_text(json.dumps(sgis_cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sgis_temporary.replace(sgis_cache_path)
    return records, {
        "status": "pass" if records and not failures else "pass_with_limitations" if records else "unavailable",
        "record_count": len(records),
        "cache_hit_count": len(records) - cache_misses,
        "cache_miss_count": cache_misses,
        "failure_count": len(failures),
        "failures": failures,
        "exact_parcel_or_building_count": sum(
            row["address_precision"]
            in {"parcel_or_building", "official_parcel", "official_road_address"}
            for row in records
        ),
        "road_or_locality_count": sum(
            row["address_precision"] in {"road_or_locality", "official_locality"}
            for row in records
        ),
        "official_sgis_count": official_count,
        "openstreetmap_fallback_count": len(records) - official_count,
        "sgis_credentials_configured": bool(sgis_consumer_key and sgis_consumer_secret),
        "sgis_auth_error": sgis_auth_error,
    }
