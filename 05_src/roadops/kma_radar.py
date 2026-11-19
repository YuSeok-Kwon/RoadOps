"""Fetch KMA API Hub radar observations and precipitation nowcast images."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
import hashlib
import struct
from typing import Any
from zoneinfo import ZoneInfo

import httpx


SEOUL = ZoneInfo("Asia/Seoul")
HSR_ENDPOINT = "https://apihub.kma.go.kr/api/typ03/cgi/rdr/nph-rdr_cmp1_img"
QPF_ENDPOINT = "https://apihub.kma.go.kr/api/typ03/cgi/rdr/nph-qpf_ana_img"
HORIZONS = (0, 1, 3, 6)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def radar_base_time(as_of: datetime | None = None) -> datetime:
    """Return a conservative five-minute KST base time for published radar frames."""

    current = as_of or datetime.now(SEOUL)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SEOUL)
    current = current.astimezone(SEOUL) - timedelta(minutes=20)
    return current.replace(
        minute=(current.minute // 5) * 5,
        second=0,
        microsecond=0,
    )


def _png_dimensions(content: bytes) -> tuple[int, int]:
    if not content.startswith(PNG_SIGNATURE) or len(content) < 24:
        raise ValueError("response_is_not_png")
    width, height = struct.unpack(">II", content[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("invalid_png_dimensions")
    return width, height


def _common_params(auth_key: str, base_time: datetime) -> dict[str, Any]:
    return {
        "tm": base_time.strftime("%Y%m%d%H%M"),
        "map": "HR",
        "grid": 2,
        "legend": 1,
        "size": 800,
        "itv": 5,
        "zoom_level": 0,
        "zoom_x": "0000000",
        "zoom_y": "0000000",
        "gov": "",
        "authKey": auth_key,
    }


def _request_spec(
    auth_key: str,
    base_time: datetime,
    horizon_hours: int,
) -> tuple[str, dict[str, Any], str, str]:
    params = _common_params(auth_key, base_time)
    if horizon_hours == 0:
        params.update(
            {
                "cmp": "HSR",
                "qcd": "HSLP",
                "obs": "ECHD",
                "color": "C4",
                "aws": 0,
            }
        )
        return (
            HSR_ENDPOINT,
            params,
            "radar_observation",
            "기상청 레이더 강수 실황",
        )
    params.update(
        {
            "qpf": "M",
            "eva": 1,
            "option": 1,
            "ef": horizon_hours * 60,
        }
    )
    return (
        QPF_ENDPOINT,
        params,
        "precipitation_nowcast",
        f"기상청 {horizon_hours}시간 후 강수예측",
    )


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return (message or type(exc).__name__)[:240]


def fetch_radar_frames(
    auth_key: str,
    *,
    as_of: datetime | None = None,
    timeout_seconds: float = 30.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch current HSR and 1/3/6-hour QPF frames without exposing credentials."""

    if not auth_key.strip():
        raise ValueError("missing_kma_api_hub_auth_key")

    fetched_at = as_of or datetime.now(SEOUL)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=SEOUL)
    fetched_at = fetched_at.astimezone(SEOUL)
    base_time = radar_base_time(fetched_at)
    owned_client = client is None
    active_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    records: list[dict[str, Any]] = []
    try:
        for horizon_hours in HORIZONS:
            endpoint, params, frame_kind, label = _request_spec(
                auth_key,
                base_time,
                horizon_hours,
            )
            valid_at = base_time + timedelta(hours=horizon_hours)
            record: dict[str, Any] = {
                "horizon_hours": horizon_hours,
                "status": "unavailable",
                "frame_kind": frame_kind,
                "label": label,
                "base_at": base_time.isoformat(),
                "valid_at": valid_at.isoformat(),
                "provider": "기상청 API허브",
                "credential_exposed": False,
            }
            try:
                response = active_client.get(endpoint, params=params, timeout=timeout_seconds)
                response.raise_for_status()
                width, height = _png_dimensions(response.content)
                record.update(
                    {
                        "status": "ready",
                        "image_data_uri": "data:image/png;base64,"
                        + base64.b64encode(response.content).decode("ascii"),
                        "image_sha256": hashlib.sha256(response.content).hexdigest(),
                        "image_bytes": len(response.content),
                        "image_width": width,
                        "image_height": height,
                    }
                )
            except (httpx.HTTPError, ValueError) as exc:
                record.update(
                    {
                        "error_type": type(exc).__name__,
                        "error_message": _safe_error_message(exc),
                    }
                )
            records.append(record)
    finally:
        if owned_client:
            active_client.close()

    ready_count = sum(record["status"] == "ready" for record in records)
    status = "ready" if ready_count == len(records) else "partial" if ready_count else "unavailable"
    return {
        "schema_version": 1,
        "dataset": "kma_radar_frames",
        "status": status,
        "generated_at": fetched_at.isoformat(),
        "base_at": base_time.isoformat(),
        "ready_frame_count": ready_count,
        "frame_count": len(records),
        "credential_exposed": False,
        "records": records,
        "sources": [
            {
                "source_id": "kma_api_hub_hsr",
                "name": "기상청 레이더 합성영상 HSR",
                "documentation_url": "https://apihub.kma.go.kr/",
                "status": "ready" if records[0]["status"] == "ready" else "unavailable",
            },
            {
                "source_id": "kma_api_hub_qpf",
                "name": "기상청 초단기 강수예측영상",
                "documentation_url": "https://apihub.kma.go.kr/",
                "status": "ready"
                if all(record["status"] == "ready" for record in records[1:])
                else "partial",
            },
        ],
    }
