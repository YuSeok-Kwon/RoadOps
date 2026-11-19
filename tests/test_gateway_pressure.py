from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.gateway_pressure import build_gateway_pressure, gateway_contribution


def _audit():
    return {
        "sources": [
            {
                "source_id": "kac_hourly_arrival_passengers",
                "readiness": "ready_for_feature_spike",
                "passenger_fields": ["passenger_count"],
                "time_fields": ["hour"],
            },
            {
                "source_id": "kac_realtime_flights",
                "readiness": "ready_for_feature_spike",
                "status_fields": ["status"],
            },
            {
                "source_id": "komsa_ferry_schedule",
                "readiness": "blocked_or_limited",
                "capacity_fields": ["capacity"],
                "status_fields": ["control_reason"],
            },
        ]
    }


def test_builds_airport_pressure_only_from_validated_jeju_fields():
    result = build_gateway_pressure(
        {
            "kac_hourly_arrival_passengers": [
                {"airport": "CJU", "hour": hour, "passenger_count": count}
                for hour, count in ((9, 100), (10, 100), (11, 200))
            ],
            "kac_realtime_flights": [
                {"airport": "CJU", "status": "정상"},
                {"airport": "CJU", "status": "지연"},
            ],
        },
        _audit(),
        generated_at="2026-11-17T10:00:00+09:00",
    )
    assert result["status"] == "partial"
    by_hour = {row["hour"]: row for row in result["airport"]["hourly_pressure"]}
    assert by_hour[11]["pressure_index"] == 1.0
    assert result["airport"]["disruption_ratio"] == 0.5


def test_gateway_contribution_is_spatially_limited_and_gated():
    pressure = build_gateway_pressure(
        {
            "kac_hourly_arrival_passengers": [
                {"airport": "CJU", "hour": 10, "passenger_count": 100},
                {"airport": "CJU", "hour": 11, "passenger_count": 200},
            ],
            "kac_realtime_flights": [{"airport": "CJU", "status": "정상"}],
        },
        _audit(),
        generated_at="2026-11-17T10:00:00+09:00",
    )
    applied = gateway_contribution(
        {"event_latitude": 33.51, "event_longitude": 126.49},
        pressure,
        target_at=datetime(2026, 11, 17, 11, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    distant = gateway_contribution(
        {"event_latitude": 33.25, "event_longitude": 126.56},
        pressure,
        target_at=datetime(2026, 11, 17, 11, tzinfo=ZoneInfo("Asia/Seoul")),
    )
    assert applied["status"] == "applied"
    assert applied["contribution"] > 0
    assert distant["contribution"] == 0
