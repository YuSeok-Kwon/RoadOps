from __future__ import annotations

import copy

from roadops.allocation_optimizer import build_constraint_allocation


def _resources(*, mandatory=None, fixed=True, max_tasks=2):
    constraints = {
        "mandatory_link_ids": (
            mandatory if mandatory is not None else ["4050000002"]
        ),
        "excluded_link_ids": [],
        "fixed_assignments": (
            [{"team_id": "team-a", "link_id": "4050000001"}]
            if fixed
            else []
        ),
        "task_overrides": [],
    }
    return {
        "schema_version": 1,
        "scenario_id": "optimizer-test",
        "planning": {
            "planning_start_at": "2026-11-13T12:00:00+09:00",
            "horizon_hours": 0,
            "default_service_minutes": 10,
            "baseline_speed_kph": 40,
            "max_tasks_per_team": max_tasks,
        },
        "vehicles": [
            {
                "vehicle_id": "vehicle-a",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": ["cones"],
            },
            {
                "vehicle_id": "vehicle-b",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": ["cones"],
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
        "constraints": constraints,
    }


def _tasks(count=3):
    rows = []
    for index, score in enumerate((80, 60, 20), start=1):
        rows.append(
            {
                "task_id": f"task-{index}",
                "link_id": f"405000000{index}",
                "road_name": f"테스트로 {index}",
                "priority_score": score,
                "service_minutes": 10,
                "required_skills": ["patrol"],
                "required_equipment": ["cones"],
                "excluded": False,
            }
        )
    while len(rows) < count:
        index = len(rows) + 1
        rows.append(
            {
                "task_id": f"task-{index}",
                "link_id": f"40500000{index:02d}",
                "road_name": f"테스트로 {index}",
                "priority_score": 1,
                "service_minutes": 1,
                "required_skills": [],
                "required_equipment": [],
                "excluded": False,
            }
        )
    return rows


def _matrix(*, unreachable_task=None):
    task_ids = ["task-1", "task-2", "task-3"]
    origins = ["team-a", "team-b", *task_ids]
    team_times = {
        ("team-a", "task-1"): 5,
        ("team-a", "task-2"): 30,
        ("team-a", "task-3"): 15,
        ("team-b", "task-1"): 20,
        ("team-b", "task-2"): 5,
        ("team-b", "task-3"): 10,
    }
    rows = []
    for origin in origins:
        for task_id in task_ids:
            if task_id == unreachable_task:
                minutes = None
            elif origin == task_id:
                minutes = 0
            elif origin.startswith("team"):
                minutes = team_times[(origin, task_id)]
            else:
                minutes = 5
            rows.append(
                {
                    "route_id": f"{origin}:{task_id}",
                    "origin_id": origin,
                    "destination_task_id": task_id,
                    "status": "ok" if minutes is not None else "unavailable",
                    "failure_reason": None if minutes is not None else "no_path",
                    "travel_time_minutes": minutes,
                    "distance_km": minutes,
                    "route_link_ids": [],
                }
            )
    return {"status": "pass", "routes": rows}


def test_optimizer_honors_fixed_mandatory_shift_and_uniqueness_constraints():
    result, report = build_constraint_allocation(
        _resources(), _tasks(), _matrix()
    )

    assert report["status"] == "pass"
    assert len(result["alternatives"]) == 2
    for plan in result["alternatives"]:
        assigned = {row["task_id"]: row for row in plan["assignments"]}
        assert len(assigned) == len(plan["assignments"])
        assert assigned["task-1"]["team_id"] == "team-a"
        assert assigned["task-1"]["fixed_assignment"] is True
        assert assigned["task-2"]["mandatory"] is True
        assert plan["metrics"]["risk_weighted_coverage_ratio"] == 1.0
        assert plan["metrics"]["constraint_violation_count"] == 0
        assert all(
            team["elapsed_minutes"] <= team["available_minutes"]
            for team in plan["team_summaries"]
        )


def test_unreachable_optional_task_is_unassigned_with_explicit_reason():
    result, report = build_constraint_allocation(
        _resources(), _tasks(), _matrix(unreachable_task="task-3")
    )

    assert report["status"] == "pass"
    for plan in result["alternatives"]:
        row = next(
            task for task in plan["unassigned_tasks"] if task["task_id"] == "task-3"
        )
        assert row["reason"] == "no_team_with_available_road_route"
        assert plan["metrics"]["assigned_task_count"] == 2


def test_unreachable_mandatory_task_fails_instead_of_relaxing_constraint():
    resources = _resources(mandatory=["4050000003"])

    result, report = build_constraint_allocation(
        resources, _tasks(), _matrix(unreachable_task="task-3")
    )

    assert result["status"] == "fail"
    assert result["failure_reason"] == "no_globally_feasible_plan"
    assert report["failed_checks"] == ["global_plan_feasibility"]


def test_exact_solver_refuses_unbounded_task_count():
    resources = _resources(fixed=False, mandatory=[], max_tasks=2)

    result, report = build_constraint_allocation(
        resources, _tasks(count=11), _matrix()
    )

    assert result["status"] == "fail"
    assert result["failure_reason"] == "exact_solver_task_limit_exceeded"
    assert report["failed_checks"] == ["exact_solver_task_limit_exceeded"]


def test_optimizer_is_deterministic_for_identical_inputs():
    resources = _resources()
    tasks = _tasks()
    matrix = _matrix()

    first = build_constraint_allocation(
        copy.deepcopy(resources), copy.deepcopy(tasks), copy.deepcopy(matrix)
    )
    second = build_constraint_allocation(
        copy.deepcopy(resources), copy.deepcopy(tasks), copy.deepcopy(matrix)
    )

    assert first == second
