from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from roadops.risk_forecast import (
    RISK_FORECAST_FIELDS,
    build_risk_forecasts,
)


NOW = datetime(2026, 11, 12, 18, 7, tzinfo=ZoneInfo("Asia/Seoul"))
GRID = (53, 38)


def _event(**overrides):
    row = {
        "event_id": "event-1",
        "source_id": "jeju_cits_road_event",
        "event_type": "road_event",
        "event_code": "534",
        "snapshot_collected_at": "2026-11-12T18:00:00+09:00",
        "integration_class": "exact_link_id",
        "scoring_eligible": "True",
        "effective_link_id": "4050000001",
        "road_name": "평화로",
        "weather_grid_x": str(GRID[0]),
        "weather_grid_y": str(GRID[1]),
        "hub_geometry_prior_status": "matched",
        "hub_fatality_index_vs_straight": "1.0",
        "traffic_status": "matched",
        "traffic_observed_at": "2026-11-12T18:05:00+09:00",
        "traffic_volume": "100",
        "traffic_speed_kph": "40",
        "traffic_occupancy_rate": "10",
        "traffic_travel_time": "20",
        "maximum_speed_limit": "80",
        "cits_visibility": "",
        "cits_snow": "",
        "cits_road_temperature": "",
        "cits_water_film": "",
        "cits_friction": "",
        "taas_status": "ok",
        "taas_risk_grade": "01",
        "quality_flags": "",
    }
    row.update(overrides)
    return row


def _weather_rows():
    rows = []
    for horizon, precipitation, rainfall, wind in (
        (0, "0", "0", "2"),
        (1, "1", "7.0", "8"),
        (3, "1", "12.0", "10"),
        (6, "0", "0", "3"),
    ):
        target = NOW.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=horizon
        )
        row = {
            "generated_at": NOW.isoformat(),
            "grid_x": GRID[0],
            "grid_y": GRID[1],
            "horizon_hours": horizon,
            "target_at": target.isoformat(),
            "row_status": "usable",
            "observation_status": "matched",
            "observed_at": "2026-11-12T18:00:00+09:00",
            "observation_fetched_at": "2026-11-12T18:05:00+09:00",
            "observed_temperature_c": "14",
            "observed_rainfall_1h_raw": "0",
            "observed_precipitation_type": "0",
            "observed_humidity_percent": "70",
            "observed_wind_speed_mps": "2",
            "forecast_status": "matched",
            "forecast_source_id": (
                "kma_short_forecast"
                if horizon == 6
                else "kma_ultra_short_forecast"
            ),
            "forecast_base_at": "2026-11-12T17:00:00+09:00",
            "forecast_fetched_at": "2026-11-12T18:06:00+09:00",
            "forecast_valid_at": target.isoformat(),
            "forecast_temperature_c": "13",
            "forecast_rainfall_raw": rainfall,
            "forecast_precipitation_type": precipitation,
            "forecast_humidity_percent": "80",
            "forecast_wind_speed_mps": wind,
        }
        rows.append(row)
    return rows


def test_forecast_builds_one_row_per_event_and_horizon_without_future_leakage():
    rows, report = build_risk_forecasts(
        [_event()],
        _weather_rows(),
        generated_at=NOW,
    )

    assert len(rows) == 4
    assert all(set(row) == set(RISK_FORECAST_FIELDS) for row in rows)
    by_horizon = {row["horizon_hours"]: row for row in rows}
    assert by_horizon[0]["weather_evidence_kind"] == "observation"
    assert by_horizon[0]["weather_fetched_at"] == "2026-11-12T18:05:00+09:00"
    assert by_horizon[0]["traffic_assumption"] == "current_observation"
    assert by_horizon[1]["traffic_assumption"] == "unavailable_no_future_model"
    assert by_horizon[1]["traffic_score"] is None
    assert by_horizon[3]["event_assumption"] == (
        "persistence_scenario_without_end_time"
    )
    assert by_horizon[6]["gateway_inflow_status"] == "unavailable"
    assert report["failed_checks"] == []
    assert report["output_rows"] == 4


def test_forecast_rejects_weather_fetched_after_generation():
    weather = _weather_rows()
    weather[1]["forecast_fetched_at"] = "2026-11-12T18:08:00+09:00"

    _, report = build_risk_forecasts([_event()], weather, generated_at=NOW)

    assert report["status"] == "fail"
    assert "future_weather_fetch_leakage" in report["failed_checks"]


def test_forecast_rain_scenario_changes_priority_and_preserves_uncertainty():
    rows, _ = build_risk_forecasts(
        [_event()],
        _weather_rows(),
        generated_at=NOW,
    )

    by_horizon = {row["horizon_hours"]: row for row in rows}
    assert by_horizon[1]["weather_road_score"] >= 60
    assert by_horizon[1]["risk_delta_from_current"] > 0
    assert by_horizon[1]["risk_direction"] == "increasing"
    assert by_horizon[1]["forecast_score_upper_bound"] > (
        by_horizon[1]["forecast_score_lower_bound"]
    )
    assert "traffic:future_forecast_not_available" in (
        by_horizon[1]["forecast_limitations"]
    )


def test_excluded_event_is_held_at_every_horizon():
    rows, report = build_risk_forecasts(
        [
            _event(
                integration_class="excluded",
                scoring_eligible="False",
                effective_link_id="",
            )
        ],
        _weather_rows(),
        generated_at=NOW,
    )

    assert all(row["forecast_status"] == "hold" for row in rows)
    assert all(row["score_available"] is False for row in rows)
    assert report["status"] == "pass_with_limitations"


def test_duplicate_weather_grain_fails_the_structural_report():
    weather = _weather_rows()
    weather.append(dict(weather[0]))

    _, report = build_risk_forecasts(
        [_event()],
        weather,
        generated_at=NOW,
    )

    assert report["status"] == "fail"
    assert "weather_grid_horizon_uniqueness" in report["failed_checks"]


def test_validated_gateway_pressure_only_affects_nearby_target_hour():
    pressure = {
        "status": "partial",
        "airport": {
            "hourly_pressure": [
                {"hour": 18, "pressure_index": 1.0, "passenger_count": 200, "baseline_hourly_passengers": 100}
            ],
            "disruption_ratio": 0,
        },
    }
    event = _event(event_latitude="33.51", event_longitude="126.49")
    rows, report = build_risk_forecasts(
        [event],
        _weather_rows(),
        generated_at=NOW,
        gateway_pressure=pressure,
    )
    current = next(row for row in rows if row["horizon_hours"] == 0)
    assert current["gateway_inflow_status"] == "applied"
    assert current["gateway_score"] > 0
    assert "gateway:airport_inflow_pressure" in current["risk_drivers"]
    assert report["failed_checks"] == []


def test_operator_policy_drives_forecast_and_retains_recomputable_inputs():
    import json
    from pathlib import Path
    from roadops.map_snapshot import _aggregate_risks
    policy = json.loads((Path(__file__).resolve().parents[1] / "config/scoring/operator_priority_v0_2.json").read_text())
    policy["weights"] = {key: 100 if key == "event" else 0 for key in policy["weights"]}
    rows, report = build_risk_forecasts([_event()], _weather_rows(), generated_at=NOW, scoring_policy=policy)
    assert report["failed_checks"] == []
    assert rows[0]["forecast_priority_score"] == 70
    assert json.loads(rows[0]["priority_result_json"])["factors"][0]["contribution"] == 70
    assert rows[0]["forecast_version"].startswith("roadops-operator-priority-v0.2:")
    links = _aggregate_risks(rows, {})
    assert len(links[0]["priority_candidates"]) == 1
    assert links[0]["priority_candidates"][0]["event_id"] == "event-1"
    assert links[0]["scoring_policy_json"] == rows[0]["scoring_policy_json"]
