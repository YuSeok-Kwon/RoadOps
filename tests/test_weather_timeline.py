from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.weather_timeline import (
    WEATHER_TIMELINE_FIELDS,
    build_weather_timeline,
)


NOW = datetime(2026, 11, 12, 18, 7, tzinfo=ZoneInfo("Asia/Seoul"))
GRID = (53, 38)


def _observation_records():
    return [
        {
            "baseDate": "20261112",
            "baseTime": "1700",
            "category": category,
            "obsrValue": value,
            "nx": GRID[0],
            "ny": GRID[1],
        }
        for category, value in {
            "T1H": "14.2",
            "RN1": "0",
            "PTY": "0",
            "REH": "70",
            "WSD": "3.1",
        }.items()
    ]


def _forecast_records(*, source: str, slots: dict[str, dict[str, str]]):
    rows = []
    short = source == "short"
    for time_value, values in slots.items():
        for category, value in values.items():
            rows.append(
                {
                    "baseDate": "20261112",
                    "baseTime": "1700" if short else "1730",
                    "fcstDate": "20261113" if time_value == "0000" else "20261112",
                    "fcstTime": time_value,
                    "category": category,
                    "fcstValue": value,
                    "nx": GRID[0],
                    "ny": GRID[1],
                }
            )
    return rows


def test_weather_timeline_separates_observation_and_forecast_horizons():
    ultra = _forecast_records(
        source="ultra",
        slots={
            "1800": {"T1H": "15", "RN1": "0", "PTY": "0", "WSD": "3"},
            "1900": {"T1H": "15", "RN1": "0", "PTY": "0", "WSD": "3"},
            "2100": {"T1H": "13", "RN1": "1.0", "PTY": "1", "WSD": "5"},
        },
    )
    short = _forecast_records(
        source="short",
        slots={
            "0000": {"TMP": "11", "PCP": "3.0mm", "PTY": "1", "WSD": "7"}
        },
    )
    metadata = {
        (source_id, GRID[0], GRID[1]): {
            "fetched_at": "2026-11-12T18:06:00+09:00"
        }
        for source_id in (
            "kma_ultra_short_nowcast",
            "kma_ultra_short_forecast",
            "kma_short_forecast",
        )
    }

    rows, report = build_weather_timeline(
        [GRID],
        observation_records={GRID: _observation_records()},
        ultra_forecast_records={GRID: ultra},
        short_forecast_records={GRID: short},
        fetch_metadata=metadata,
        generated_at=NOW,
    )

    assert len(rows) == 4
    assert all(set(row) == set(WEATHER_TIMELINE_FIELDS) for row in rows)
    by_horizon = {row["horizon_hours"]: row for row in rows}
    assert by_horizon[0]["observed_at"] == "2026-11-12T17:00:00+09:00"
    assert by_horizon[0]["observed_temperature_c"] == 14.2
    assert by_horizon[1]["forecast_source_id"] == "kma_ultra_short_forecast"
    assert by_horizon[3]["forecast_rainfall_raw"] == "1.0"
    assert by_horizon[6]["forecast_source_id"] == "kma_short_forecast"
    assert by_horizon[6]["forecast_temperature_c"] == 11.0
    assert report["status"] == "pass"
    assert report["row_status_counts"] == {"usable": 4}
    assert report["failed_checks"] == []


def test_weather_timeline_holds_future_horizon_without_forecast():
    rows, report = build_weather_timeline(
        [GRID],
        observation_records={GRID: _observation_records()},
        ultra_forecast_records={GRID: []},
        short_forecast_records={GRID: []},
        fetch_metadata={},
        generated_at=NOW,
        horizons=(0, 1),
    )

    by_horizon = {row["horizon_hours"]: row for row in rows}
    assert by_horizon[0]["row_status"] == "usable"
    assert by_horizon[1]["row_status"] == "hold"
    assert by_horizon[1]["quality_flags"] == "forecast:missing"
    assert report["status"] == "pass_with_limitations"
    assert report["row_status_counts"] == {"hold": 1, "usable": 1}


def test_weather_timeline_uses_forecast_as_degraded_current_fallback():
    ultra = _forecast_records(
        source="ultra",
        slots={"1800": {"T1H": "15", "RN1": "0", "PTY": "0"}},
    )

    rows, _ = build_weather_timeline(
        [GRID],
        observation_records={GRID: []},
        ultra_forecast_records={GRID: ultra},
        short_forecast_records={GRID: []},
        fetch_metadata={},
        generated_at=NOW,
        horizons=(0,),
    )

    assert rows[0]["row_status"] == "degraded"
    assert rows[0]["observation_status"] == "missing"
    assert rows[0]["forecast_status"] == "matched"
