from __future__ import annotations

import copy

from roadops.allocation_baselines import build_allocation_baselines


def _resource_plan(*, max_tasks=1, shift_end="2026-11-12T11:00:00+09:00"):
    return {
        "schema_version": 1,
        "scenario_id": "test-scenario",
        "planning": {
            "planning_start_at": "2026-11-12T10:00:00+09:00",
            "horizon_hours": 0,
            "default_service_minutes": 5,
            "baseline_speed_kph": 60,
            "max_tasks_per_team": max_tasks,
        },
        "vehicles": [
            {
                "vehicle_id": "vehicle-1",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": ["cones"],
            }
        ],
        "teams": [
            {
                "team_id": "team-1",
                "personnel_count": 2,
                "vehicle_id": "vehicle-1",
                "start_latitude": 33.0,
                "start_longitude": 126.0,
                "shift_start_at": "2026-11-12T09:00:00+09:00",
                "shift_end_at": shift_end,
                "skills": ["patrol"],
                "equipment": [],
            }
        ],
        "constraints": {
            "mandatory_link_ids": [],
            "excluded_link_ids": [],
            "fixed_assignments": [],
            "task_overrides": [],
        },
    }


def _forecast(event_id, link_id, score):
    return {
        "horizon_hours": 0,
        "event_id": event_id,
        "source_id": "test-source",
        "event_type": "road_event",
        "effective_link_id": link_id,
        "road_name": "테스트로",
        "score_available": True,
        "ranking_eligible": True,
        "forecast_priority_score": score,
        "forecast_score_lower_bound": score,
        "forecast_score_upper_bound": score,
        "risk_level": "high" if score >= 50 else "low",
    }


def _event(event_id, latitude, longitude):
    return {
        "event_id": event_id,
        "event_latitude": latitude,
        "event_longitude": longitude,
    }


def _plan(result, name):
    return next(plan for plan in result["plans"] if plan["strategy"] == name)


def test_baselines_collapse_duplicate_links_and_expose_strategy_difference():
    forecasts = [
        _forecast("event-high", "4050000001", 90),
        _forecast("event-high-duplicate", "4050000001", 80),
        _forecast("event-near", "4050000002", 20),
    ]
    events = [
        _event("event-high", 33.1, 126.0),
        _event("event-high-duplicate", 33.1, 126.0),
        _event("event-near", 33.01, 126.0),
    ]

    result, report = build_allocation_baselines(
        _resource_plan(), forecasts, events
    )

    risk = _plan(result, "risk_first")
    nearest = _plan(result, "nearest")
    assert report["task_build"]["field_task_count"] == 2
    assert report["task_build"]["collapsed_duplicate_event_count"] == 1
    assert risk["assignments"][0]["link_id"] == "4050000001"
    assert risk["assignments"][0]["event_count"] == 2
    assert nearest["assignments"][0]["link_id"] == "4050000002"
    assert risk["metrics"]["risk_weighted_coverage_ratio"] > (
        nearest["metrics"]["risk_weighted_coverage_ratio"]
    )
    assert all(plan["metrics"]["constraint_violation_count"] == 0 for plan in result["plans"])


def test_fixed_mandatory_and_excluded_constraints_are_visible_and_honored():
    resources = _resource_plan(max_tasks=2)
    resources["constraints"] = {
        "mandatory_link_ids": ["4050000002"],
        "excluded_link_ids": ["4050000003"],
        "fixed_assignments": [
            {"team_id": "team-1", "link_id": "4050000001"}
        ],
        "task_overrides": [
            {
                "link_id": "4050000001",
                "service_minutes": 8,
                "required_skills": ["patrol"],
                "required_equipment": ["cones"],
            }
        ],
    }
    forecasts = [
        _forecast("event-1", "4050000001", 60),
        _forecast("event-2", "4050000002", 40),
        _forecast("event-3", "4050000003", 100),
    ]
    events = [
        _event("event-1", 33.01, 126.0),
        _event("event-2", 33.02, 126.0),
        _event("event-3", 33.001, 126.0),
    ]

    result, _ = build_allocation_baselines(resources, forecasts, events)

    for plan in result["plans"]:
        assigned = {row["link_id"]: row for row in plan["assignments"]}
        assert assigned["4050000001"]["fixed_assignment"] is True
        assert assigned["4050000002"]["mandatory"] is True
        excluded = next(
            row
            for row in plan["unassigned_tasks"]
            if row["link_id"] == "4050000003"
        )
        assert excluded["reason"] == "excluded_by_operator"
        assert plan["constraint_violations"] == []
    assert result["status"] == "pass"


def test_infeasible_fixed_assignment_is_reported_without_reassignment():
    resources = _resource_plan(max_tasks=1)
    resources["constraints"]["fixed_assignments"] = [
        {"team_id": "team-1", "link_id": "4050000001"}
    ]
    resources["constraints"]["task_overrides"] = [
        {
            "link_id": "4050000001",
            "service_minutes": 5,
            "required_skills": ["specialist"],
            "required_equipment": [],
        }
    ]

    result, report = build_allocation_baselines(
        resources,
        [_forecast("event-1", "4050000001", 80)],
        [_event("event-1", 33.01, 126.0)],
    )

    for plan in result["plans"]:
        assert plan["assignments"] == []
        assert plan["unassigned_tasks"][0]["reason"] == "fixed_team_infeasible"
        assert plan["constraint_violations"][0]["code"] == (
            "fixed_assignment_unfulfilled"
        )
    assert report["status"] == "pass_with_limitations"
    assert report["failed_checks"] == []


def test_baseline_result_is_deterministic_for_identical_inputs():
    resources = _resource_plan(max_tasks=2)
    forecasts = [
        _forecast("event-1", "4050000001", 70),
        _forecast("event-2", "4050000002", 30),
    ]
    events = [
        _event("event-1", 33.02, 126.0),
        _event("event-2", 33.01, 126.0),
    ]

    first = build_allocation_baselines(
        copy.deepcopy(resources), copy.deepcopy(forecasts), copy.deepcopy(events)
    )
    second = build_allocation_baselines(
        copy.deepcopy(resources), copy.deepcopy(forecasts), copy.deepcopy(events)
    )

    assert first == second
