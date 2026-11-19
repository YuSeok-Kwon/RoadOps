from __future__ import annotations

import copy
import json
from pathlib import Path

from roadops.allocation_baselines import build_field_tasks
from roadops.resources import institutional_eligibility, validate_resource_plan


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
    assert report["governance_mode"] == "institution_aware"
    assert report["agency_count"] == 5
    assert report["authority_record_count"] == 10
    assert report["governance_source_count"] == 11
    assert east["managing_agency_id"] == "jeju-province-road-management"
    assert east["authorized_road_jurisdictions"] == [
        "jeju-provincial-road-1131",
        "jeju-provincial-road-1135",
        "jeju-provincial-road-1139",
    ]
    override = normalized["constraints"]["task_overrides"][0]
    assert normalized["governance"]["defaults"]["dispatch_approver_id"] == (
        "province-road-operator-designate"
    )
    assert override["dispatch_approver_id"] is None
    assert override["police_handoff_level"] == "coordinate"

    renormalized, second_report = validate_resource_plan(normalized)
    assert second_report["status"] == "pass"
    assert renormalized == normalized


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


def test_resource_validation_rejects_unknown_governance_references():
    payload = copy.deepcopy(_sample())
    payload["teams"][0]["managing_agency_id"] = "unknown-agency"
    payload["constraints"]["task_overrides"][0][
        "police_handoff_channel_id"
    ] = "unknown-channel"

    _, report = validate_resource_plan(payload)

    codes = {error["code"] for error in report["errors"]}
    assert report["status"] == "fail"
    assert "unknown_agency" in codes
    assert "valid_handoff_channel_required" in codes


def test_institutional_eligibility_checks_agency_and_jurisdiction():
    normalized, report = validate_resource_plan(_sample())
    assert report["status"] == "pass"
    team = normalized["teams"][0]
    allowed = institutional_eligibility(
        team,
        {
            "managing_agency_id": "jeju-province-road-management",
            "road_jurisdiction": "jeju-provincial-road-1131",
            "road_team_dispatch_eligible": True,
        },
    )
    denied = institutional_eligibility(
        team,
        {
            "managing_agency_id": "jeju-city-road-management",
            "road_jurisdiction": "jeju_city_managed_road",
            "road_team_dispatch_eligible": True,
        },
    )

    assert allowed == {"eligible": True, "reasons": []}
    assert denied["eligible"] is False
    assert denied["reasons"] == [
        "managing_agency_not_authorized",
        "road_jurisdiction_not_authorized",
    ]


def test_field_task_exposes_pending_approval_and_police_handoff():
    normalized, report = validate_resource_plan(_sample())
    assert report["status"] == "pass"
    tasks, task_report = build_field_tasks(
        [
            {
                "horizon_hours": 0,
                "event_id": "event-1",
                "source_id": "test",
                "event_type": "road_closure",
                "effective_link_id": "4050418600",
                "road_name": "test road",
                "score_available": True,
                "ranking_eligible": True,
                "forecast_priority_score": 80,
                "forecast_score_lower_bound": 75,
                "forecast_score_upper_bound": 85,
                "risk_level": "high",
            }
        ],
        [
            {
                "event_id": "event-1",
                "event_latitude": 33.4,
                "event_longitude": 126.5,
            }
        ],
        horizon_hours=0,
        resource_plan=normalized,
    )

    task = tasks[0]
    assert task["managing_agency_id"] == "jeju-province-road-management"
    assert task["road_jurisdiction"] == "jeju-provincial-road-1131"
    assert task["administrative_city"] == "서귀포시"
    assert task["administrative_unit"] == "남원읍"
    assert task["authority_status"] == "official_provincial_road_scope"
    assert task["managing_agency_name"] == "제주특별자치도 도로관리과"
    assert task["dispatch_approver_verification_status"] == (
        "operator_configuration_required"
    )
    assert task["dispatch_approval_status"] == "pending"
    assert task["response_mode"] == "joint_response"
    assert task["handoff_actions"] == [
        {
            "handoff_type": "police",
            "level": "coordinate",
            "channel_id": "jeju-police-traffic-coordination",
            "target_agency_id": "jeju-police",
            "target_agency_name": "제주경찰청",
            "contact_method": "교통통제 협조 요청(긴급 112 / 민원 182)",
            "automation_status": "manual_operator_handoff",
            "status": "pending",
        }
    ]
    assert [row["status"] for row in task["handoff_statuses"]] == [
        "pending",
        "not_requested",
    ]
    assert task_report["approval_required_task_count"] == 1
    assert task_report["handoff_action_count"] == 1
    assert task_report["official_authority_task_count"] == 1
