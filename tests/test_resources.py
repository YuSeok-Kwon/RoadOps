from __future__ import annotations

import copy
import json
from pathlib import Path

from roadops.resources import validate_resource_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = (
    PROJECT_ROOT / "config/resource_scenarios/demo_three_teams_v0_1.json"
)


def _sample():
    with SAMPLE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_resource_sample_normalizes_vehicle_equipment_and_passes():
    normalized, report = validate_resource_plan(_sample())

    assert report["status"] == "pass"
    assert report["team_count"] == 3
    assert report["vehicle_count"] == 3
    assert report["total_personnel"] == 6
    east = next(
        team for team in normalized["teams"] if team["team_id"] == "team-east"
    )
    assert east["equipment"] == ["road_weather_kit", "traffic_cones"]
    assert normalized["planning"]["distance_semantics"] == (
        "straight_line_baseline_not_route_time"
    )


def test_resource_validation_rejects_duplicate_vehicle_and_capacity_overflow():
    payload = copy.deepcopy(_sample())
    payload["teams"][1]["vehicle_id"] = "patrol-east-01"
    payload["teams"][1]["personnel_count"] = 3

    _, report = validate_resource_plan(payload)

    codes = {error["code"] for error in report["errors"]}
    assert report["status"] == "fail"
    assert "vehicle_assigned_twice" in codes
    assert "vehicle_capacity_exceeded" in codes


def test_resource_validation_rejects_shift_and_link_constraint_conflicts():
    payload = copy.deepcopy(_sample())
    payload["teams"][0]["shift_end_at"] = "2026-11-12T22:05:00+09:00"
    payload["constraints"]["mandatory_link_ids"] = ["4060456800"]

    _, report = validate_resource_plan(payload)

    codes = {error["code"] for error in report["errors"]}
    assert report["status"] == "fail"
    assert "planning_start_outside_shift" in codes
    assert "mandatory_excluded_conflict" in codes
