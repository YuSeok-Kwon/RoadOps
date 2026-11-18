from datetime import datetime
import struct
from zoneinfo import ZoneInfo

import httpx

from roadops.kma_radar import fetch_radar_frames, radar_base_time


SEOUL = ZoneInfo("Asia/Seoul")


def png(width: int = 635, height: int = 620) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"mock"


def test_radar_base_time_uses_kst_delay_and_five_minute_floor():
    as_of = datetime(2026, 11, 18, 21, 43, 52, tzinfo=SEOUL)
    assert radar_base_time(as_of) == datetime(2026, 11, 18, 21, 20, tzinfo=SEOUL)


def test_fetch_radar_frames_collects_hsr_and_qpf_without_exposing_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=png(), request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload = fetch_radar_frames(
            "secret-auth-key",
            as_of=datetime(2026, 11, 18, 21, 43, tzinfo=SEOUL),
            client=client,
        )

    assert payload["status"] == "ready"
    assert payload["ready_frame_count"] == 4
    assert [row["horizon_hours"] for row in payload["records"]] == [0, 1, 3, 6]
    assert payload["records"][0]["frame_kind"] == "radar_observation"
    assert payload["records"][1]["frame_kind"] == "precipitation_nowcast"
    assert all(row["image_data_uri"].startswith("data:image/png;base64,") for row in payload["records"])
    assert all(row["image_width"] == 635 and row["image_height"] == 620 for row in payload["records"])
    assert "secret-auth-key" not in str(payload)
    assert len(seen) == 4
    assert seen[0].url.params["cmp"] == "HSR"
    assert [request.url.params.get("ef") for request in seen[1:]] == ["60", "180", "360"]


def test_fetch_radar_frames_keeps_available_frames_when_one_response_is_invalid():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("ef") == "180":
            return httpx.Response(200, content=b"service error", request=request)
        return httpx.Response(200, content=png(), request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload = fetch_radar_frames(
            "secret-auth-key",
            as_of=datetime(2026, 11, 18, 21, 43, tzinfo=SEOUL),
            client=client,
        )

    assert payload["status"] == "partial"
    assert payload["ready_frame_count"] == 3
    failed = next(row for row in payload["records"] if row["horizon_hours"] == 3)
    assert failed["status"] == "unavailable"
    assert failed["error_message"] == "response_is_not_png"
