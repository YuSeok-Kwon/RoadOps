from __future__ import annotations

import copy

from roadops.allocation_optimizer import build_constraint_allocation
from roadops.replanning import apply_heavy_rain_scenario, build_partial_replan


CLOSED_LINK_ID = "4059999999"


def _resources():
    return {
        "schema_version": 1,
        "scenario_id": "replan-test",
        "planning": {
            "planning_start_at": "2026-11-13T12:00:00+09:00",
            "horizon_hours": 0,
            "default_service_minutes": 5,
            "baseline_speed_kph": 40,
            "max_tasks_per_team": 2,
        },
        "vehicles": [
            {
                "vehicle_id": "vehicle-a",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": [],
            },
            {
                "vehicle_id": "vehicle-b",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": [],
            },
        ],
        "teams": [
            {
                "team_id": "team-a",
                "personnel_count": 2,
                "vehicle_id": "vehicle-a",
                "start_latitude": 33.0,
                "start_longitude": 126.0,
                "shift_start_at": "2026-11-13T12:00:00+09:00",
                "shift_end_at": "2026-11-13T13:00:00+09:00",
                "skills": ["patrol"],
                "equipment": [],
            },
            {
                "team_id": "team-b",
                "personnel_count": 2,
                "vehicle_id": "vehicle-b",
                "start_latitude": 33.1,
                "start_longitude": 126.1,
                "shift_start_at": "2026-11-13T12:00:00+09:00",
                "shift_end_at": "2026-11-13T13:00:00+09:00",
                "skills": ["patrol"],
                "equipment": [],
            },
        ],
        "constraints": {
            "mandatory_link_ids": [],
            "excluded_link_ids": [],
            "fixed_assignments": [
                {"team_id": "team-a", "link_id": "4050000001"}
            ],
            "task_overrides": [],
        },
    }


def _tasks():
    return [
        {
            "task_id": f"task-{index}",
            "link_id": f"405000000{index}",
            "road_name": f"테스트로 {index}",
            "priority_score": score,
            "service_minutes": 5,
            "required_skills": ["patrol"],
            "required_equipment": [],
            "excluded": False,
        }
        for index, score in enumerate((80, 70, 60, 50), start=1)
    ]


def _matrix(*, closure=False):
    task_ids = [f"task-{index}" for index in range(1, 5)]
    origins = ["team-a", "team-b", *task_ids]
    routes = []
    for origin in origins:
        for destination in task_ids:
            destination_index = int(destination[-1])
            if origin == destination:
                minutes = 0
            elif origin == "team-a":
                minutes = destination_index if destination_index <= 2 else 30
            elif origin == "team-b":
                minutes = destination_index - 2 if destination_index >= 3 else 30
            else:
                origin_index = int(origin[-1])
                same_zone = (origin_index <= 2) == (destination_index <= 2)
                minutes = 1 if same_zone else 30
            marker = origin == "team-b" and destination == "task-3"
            route_links = ["4051111111"]
            if marker and not closure:
                route_links = [CLOSED_LINK_ID]
            if marker and closure:
                minutes = 3
                route_links = ["4058888888"]
            routes.append(
                {
                    "route_id": f"{origin}:{destination}",
                    "origin_id": origin,
                    "destination_task_id": destination,
                    "status": "ok",
                    "travel_time_minutes": minutes,
                    "distance_km": minutes,
                    "network_travel_minutes": minutes,
                    "route_link_ids": route_links,
                }
            )
    return {
        "schema_version": 1,
        "scenario_id": "replan-test",
        "status": "pass",
        "route_semantics": "test_network_time",
        "closed_link_ids": [CLOSED_LINK_ID] if closure else [],
        "routes": routes,
    }


def _base_allocation():
    result, report = build_constraint_allocation(
        _resources(), _tasks(), _matrix()
    )
    assert report["status"] == "pass"
    return result


def test_closure_replans_only_affected_team_and_preserves_completed_fixed_work():
    base = _base_allocation()
    scenario = {
        "scenario_type": "road_closure",
        "reason_code": "test_closure",
        "affected_link_ids": [CLOSED_LINK_ID],
    }

    result, report = build_partial_replan(
        _resources(),
        _tasks(),
        base,
        _matrix(closure=True),
        scenario,
        completed_task_ids=["task-1"],
    )

    assert report["status"] == "pass"
    assert result["affected_team_ids"] == ["team-b"]
    assert result["change_diff"]["unchanged_team_ids"] == ["team-a"]
    assert result["change_diff"]["preserved_completed_task_ids"] == ["task-1"]
    assert result["change_diff"]["preserved_fixed_task_ids"] == ["task-1"]
    assert result["replanned_plan"]["constraint_violations"] == []
    assert all(
        CLOSED_LINK_ID not in row["route_link_ids"]
        for row in result["replanned_plan"]["assignments"]
        if row["task_id"] != "task-1"
    )
    assert CLOSED_LINK_ID in result["explanation"]["change_reason_messages"][0]
    assert result["manual_approval_required"] is True


def test_heavy_rain_scenario_adjusts_only_exposed_tasks_and_routes():
    tasks, matrix, metadata = apply_heavy_rain_scenario(
        _tasks(),
        _matrix(),
        affected_link_ids=["4050000003"],
        priority_delta=15,
        service_minutes_delta=10,
        travel_time_multiplier=1.5,
    )

    changed = next(task for task in tasks if task["task_id"] == "task-3")
    unchanged = next(task for task in tasks if task["task_id"] == "task-1")
    assert changed["priority_score"] == 75
    assert changed["service_minutes"] == 15
    assert unchanged["priority_score"] == 80
    assert metadata["changed_task_ids"] == ["task-3"]
    route = next(
        row
        for row in matrix["routes"]
        if row["origin_id"] == "team-b"
        and row["destination_task_id"] == "task-3"
    )
    assert route["travel_time_minutes"] == 1.5


def test_heavy_rain_replans_affected_team_and_preserves_unaffected_team():
    tasks, matrix, metadata = apply_heavy_rain_scenario(
        _tasks(),
        _matrix(),
        affected_link_ids=["4050000003"],
    )

    result, report = build_partial_replan(
        _resources(),
        tasks,
        _base_allocation(),
        matrix,
        metadata,
        completed_task_ids=["task-1"],
    )

    assert report["status"] == "pass"
    assert result["affected_team_ids"] == ["team-b"]
    assert result["change_diff"]["unchanged_team_ids"] == ["team-a"]
    assert result["change_diff"]["preserved_completed_task_ids"] == ["task-1"]
    assert result["replanned_plan"]["constraint_violations"] == []
    assert len(result["explanation"]["change_reason_messages"]) == 2


def test_non_prefix_completed_task_fails_before_replanning():
    base = _base_allocation()
    scenario = {
        "scenario_type": "road_closure",
        "affected_link_ids": [CLOSED_LINK_ID],
    }

    result, report = build_partial_replan(
        _resources(),
        _tasks(),
        base,
        _matrix(closure=True),
        scenario,
        completed_task_ids=["task-2"],
    )

    assert result["failure_reason"] == "completed_task_preservation_failed"
    assert report["failed_tool"] == "preservation_planner"


def test_partial_replan_is_deterministic_for_identical_inputs():
    inputs = (
        _resources(),
        _tasks(),
        _base_allocation(),
        _matrix(closure=True),
        {
            "scenario_type": "road_closure",
            "affected_link_ids": [CLOSED_LINK_ID],
        },
    )

    first = build_partial_replan(
        *copy.deepcopy(inputs), completed_task_ids=["task-1"]
    )
    second = build_partial_replan(
        *copy.deepcopy(inputs), completed_task_ids=["task-1"]
    )

    assert first == second
