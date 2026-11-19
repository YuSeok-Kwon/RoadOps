import json
from pathlib import Path

from roadops.depot_weather import build_depot_weather_rows, depot_weather_grids, depot_grid


def test_real_depots_require_exact_grids():
    resources = json.loads((Path(__file__).resolve().parents[1] / "config/resource_scenarios/demo_three_teams_v0_1.json").read_text())
    assert depot_weather_grids(resources["teams"]) == {(56, 37), (52, 38), (52, 37)}
    assert depot_grid({"start_latitude": None, "start_longitude": 126.5}) is None
    assert depot_grid({"start_latitude": "nan", "start_longitude": 126.5}) is None
    assert depot_grid({"start_latitude": 126.5, "start_longitude": 33.4}) is None


TEAM = {"team_id": "north", "start_location_name": "용담", "start_latitude": 33.5146684, "start_longitude": 126.4980536}
RAW = {"grid_x": "52", "grid_y": "38", "horizon_hours": "0", "generated_at": "2026-11-20T01:15:00+09:00",
       "observation_status": "matched", "forecast_status": "matched", "observed_temperature_c": "4", "observed_precipitation_type": "1",
       "observed_rainfall_1h_raw": "2", "observed_humidity_percent": "90", "forecast_temperature_c": "-2", "forecast_precipitation_type": "3"}


def test_current_uses_one_observation_source_and_future_uses_forecast():
    rows = build_depot_weather_rows([RAW, {**RAW, "horizon_hours": "1"}], [TEAM])
    assert len(rows) == 4
    assert rows[0]["evidence_kind"] == "observation"
    assert (rows[0]["temperature_c"], rows[0]["precipitation_type"]) == ("4", "1")
    assert rows[1]["evidence_kind"] == "forecast"
    assert (rows[1]["temperature_c"], rows[1]["precipitation_type"]) == ("-2", "3")
    assert rows[1]["rainfall_raw"] is None  # Never fill missing forecast from observation.
    assert rows[2]["status"] == "unavailable"  # No fallback to another horizon.


def test_unavailable_grid_never_uses_neighbor_or_stale_observation():
    assert build_depot_weather_rows([{**RAW, "grid_x": 51}], [TEAM])[0]["status"] == "unavailable"
    stale = {**RAW, "observation_status": "stale_or_future"}
    assert build_depot_weather_rows([stale], [TEAM])[0]["evidence_kind"] == "forecast"
    stale["forecast_status"] = "misaligned"
    row = build_depot_weather_rows([stale], [TEAM])[0]
    assert row["status"] == "unavailable" and row["temperature_c"] is None


def test_latest_grid_snapshot_wins_regardless_of_input_order():
    newer = {**RAW, "generated_at": "2026-11-20T01:30:00+09:00", "observed_temperature_c": "8"}
    for ordered in ([RAW, newer], [newer, RAW]):
        assert build_depot_weather_rows(ordered, [TEAM])[0]["temperature_c"] == "8"
