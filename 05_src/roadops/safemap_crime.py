"""Fetch the authorized Safety Map crime-caution WMS without exposing its key."""

from __future__ import annotations

import base64
from typing import Any
import urllib.parse
import urllib.request


SAFEMAP_CRIME_WMS_URL = "https://www.safemap.go.kr/openapi2/IF_0087_WMS"
JEJU_BBOX = (126.08, 33.10, 126.98, 33.62)


def validate_wms_response(body: bytes, content_type: str) -> dict[str, Any]:
    is_png = body.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = body.startswith(b"\xff\xd8\xff")
    image_type = "image/png" if is_png else "image/jpeg" if is_jpeg else None
    if not image_type:
        preview = body[:200].decode("utf-8", errors="replace")
        raise ValueError(f"safemap_wms_response_not_image:{content_type}:{preview}")
    return {
        "image_type": image_type,
        "byte_count": len(body),
        "data_url": f"data:{image_type};base64,{base64.b64encode(body).decode('ascii')}",
    }


def fetch_crime_caution_wms(
    service_key: str,
    *,
    bbox: tuple[float, float, float, float] = JEJU_BBOX,
    width: int = 1200,
    height: int = 720,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    params = {
        "serviceKey": service_key,
        "srs": "EPSG:4326",
        "bbox": ",".join(str(value) for value in bbox),
        "format": "image/png",
        "width": width,
        "height": height,
        "transparent": "TRUE",
        "layers": "A2SM_CRMNLHSPOT_TOT",
        "styles": "A2SM_CrmnlHspot_Tot_Tot",
    }
    request = urllib.request.Request(
        f"{SAFEMAP_CRIME_WMS_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "RoadOps-Jeju/0.1", "Accept": "image/png"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        http_status = getattr(response, "status", None)
    image = validate_wms_response(body, content_type)
    return {
        "layer_id": "safemap_crime_caution_all",
        "bbox": list(bbox),
        "srs": "EPSG:4326",
        "width": width,
        "height": height,
        "data_url": image["data_url"],
        "analysis_year": 2025,
        "license": "공공누리 제4유형: 출처표시·상업적 이용금지·변경금지",
        "source_label": "생활안전지도·경찰청 범죄주의구간(전체)",
    }, {
        "status": "ready",
        "http_status": http_status,
        "content_type": content_type,
        "image_type": image["image_type"],
        "byte_count": image["byte_count"],
        "credential_exposed": False,
    }
