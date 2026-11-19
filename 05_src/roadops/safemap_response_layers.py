"""Collect authorized Safety Map response facilities and map overlays."""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping
import urllib.parse
import urllib.request

from roadops.safemap_crime import JEJU_BBOX, validate_wms_response


SAFEMAP_OPENAPI_BASE_URL = "https://www.safemap.go.kr/openapi2"
FACILITY_INTERFACES = {
    "police": "IF_0036",
    "fire": "IF_0038",
}
TRAFFIC_ACCIDENT_WMS_INTERFACE = "IF_0093_WMS"
TRAFFIC_ACCIDENT_WMS_LAYER = "A2SM_TFCACDHSPOT_NEW"
MAX_PAGE_SIZE = 1000


def web_mercator_to_wgs84(x: object, y: object) -> tuple[float, float]:
    """Convert EPSG:3857 coordinates returned by Safety Map to WGS84."""

    x_value = float(x)
    y_value = float(y)
    longitude = x_value * 180.0 / 20037508.34
    latitude = math.degrees(
        2.0 * math.atan(math.exp(y_value / 6378137.0)) - math.pi / 2.0
    )
    return longitude, latitude


def _request_json(
    interface_id: str,
    service_key: str,
    *,
    page_number: int,
    page_size: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "serviceKey": service_key,
            "numOfRows": page_size,
            "pageNo": page_number,
            "returnType": "JSON",
        }
    )
    request = urllib.request.Request(
        f"{SAFEMAP_OPENAPI_BASE_URL}/{interface_id}?{params}",
        headers={"User-Agent": "RoadOps-Jeju/0.1", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
    return json.loads(body.decode("utf-8-sig"))


def fetch_paginated_records(
    service_key: str,
    interface_id: str,
    *,
    page_size: int = MAX_PAGE_SIZE,
    timeout_seconds: float = 30.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch every page while respecting the provider's 1,000-row cap."""

    if not service_key:
        raise ValueError("safemap_service_key_required")
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
    records: list[dict[str, Any]] = []
    page_number = 1
    total_count: int | None = None
    while total_count is None or len(records) < total_count:
        payload = _request_json(
            interface_id,
            service_key,
            page_number=page_number,
            page_size=page_size,
            timeout_seconds=timeout_seconds,
        )
        header = payload.get("header") or {}
        raw_result_code = header.get("resultCode")
        result_code = "" if raw_result_code is None else str(raw_result_code)
        if result_code not in {"00", "0"}:
            raise ValueError(
                f"safemap_error:{interface_id}:{result_code}:"
                f"{str(header.get('resultMsg') or '')[:120]}"
            )
        body = payload.get("body") or {}
        total_count = int(body.get("totalCount") or 0)
        page_items = (body.get("items") or {}).get("item") or []
        if isinstance(page_items, Mapping):
            page_items = [page_items]
        if not isinstance(page_items, list):
            raise ValueError(f"safemap_invalid_items:{interface_id}")
        records.extend(dict(item) for item in page_items if isinstance(item, Mapping))
        if not page_items:
            break
        page_number += 1
        if page_number > 100:
            raise ValueError(f"safemap_page_limit_exceeded:{interface_id}")
    return records, {
        "interface_id": interface_id,
        "provider_total_count": total_count or 0,
        "fetched_count": len(records),
        "page_count": page_number - 1,
        "credential_exposed": False,
    }


def normalize_jeju_facilities(
    records: Iterable[Mapping[str, Any]],
    *,
    facility_kind: str,
) -> list[dict[str, Any]]:
    """Keep Jeju response facilities and expose only operational fields."""

    if facility_kind not in FACILITY_INTERFACES:
        raise ValueError(f"unsupported_facility_kind:{facility_kind}")
    interface_id = FACILITY_INTERFACES[facility_kind]
    provider_name = "경찰청" if facility_kind == "police" else "소방청"
    normalized: list[dict[str, Any]] = []
    for row in records:
        road_address = str(row.get("rn_adres") or row.get("adres") or "").strip()
        is_jeju = str(row.get("ctprvn_cd") or "") == "50" or "제주" in road_address
        if not is_jeju:
            continue
        try:
            longitude, latitude = web_mercator_to_wgs84(row.get("x"), row.get("y"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not (125.9 <= longitude <= 127.2 and 32.9 <= latitude <= 33.8):
            continue
        object_id = str(row.get("objt_id") or row.get("fclty_cd") or len(normalized))
        normalized.append(
            {
                "facility_id": f"safemap:{facility_kind}:{object_id}",
                "facility_kind": facility_kind,
                "facility_name": str(row.get("fclty_nm") or "이름 미확인"),
                "facility_type": str(row.get("fclty_ty") or "시설 유형 미확인"),
                "road_address": road_address or "주소 미확인",
                "phone_number": str(row.get("telno") or "").strip() or None,
                "longitude": round(longitude, 7),
                "latitude": round(latitude, 7),
                "provider_name": provider_name,
                "source_interface_id": interface_id,
                "handoff_role": facility_kind,
            }
        )
    return sorted(
        normalized,
        key=lambda row: (str(row["facility_kind"]), str(row["facility_name"])),
    )


def fetch_traffic_accident_wms(
    service_key: str,
    *,
    bbox: tuple[float, float, float, float] = JEJU_BBOX,
    width: int = 1200,
    height: int = 720,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch the authorized annual traffic-accident hotspot image for Jeju."""

    params = {
        "serviceKey": service_key,
        "srs": "EPSG:4326",
        "bbox": ",".join(str(value) for value in bbox),
        "format": "image/png",
        "width": width,
        "height": height,
        "transparent": "TRUE",
        "layers": TRAFFIC_ACCIDENT_WMS_LAYER,
        "styles": "",
    }
    request = urllib.request.Request(
        f"{SAFEMAP_OPENAPI_BASE_URL}/{TRAFFIC_ACCIDENT_WMS_INTERFACE}?"
        f"{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "RoadOps-Jeju/0.1", "Accept": "image/png"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        http_status = getattr(response, "status", None)
    image = validate_wms_response(body, content_type)
    return {
        "layer_id": "safemap_traffic_accident_hotspots",
        "bbox": list(bbox),
        "srs": "EPSG:4326",
        "width": width,
        "height": height,
        "data_url": image["data_url"],
        "analysis_year": 2025,
        "source_label": "생활안전지도·한국도로교통공단 교통사고다발구역",
        "license": "공공누리 제4유형: 출처표시·상업적 이용금지·변경금지",
        "risk_score_input": False,
    }, {
        "interface_id": TRAFFIC_ACCIDENT_WMS_INTERFACE,
        "status": "ready",
        "http_status": http_status,
        "content_type": content_type,
        "image_type": image["image_type"],
        "byte_count": image["byte_count"],
        "credential_exposed": False,
    }
