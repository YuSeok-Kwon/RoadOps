from __future__ import annotations

import copy

from roadops.agent_flow import parse_agent_request, run_agent_flow


def _resources():
    return {
        "schema_version": 1,
        "scenario_id": "agent-test",
        "planning": {
            "planning_start_at": "2026-11-13T12:00:00+09:00",
            "horizon_hours": 0,
            "default_service_minutes": 10,
            "baseline_speed_kph": 40,
            "max_tasks_per_team": 2,
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
        "target_at": "2026-11-13T12:00:00+09:00",
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
        "risk_level": "high",
    }


def _event(event_id, latitude, longitude):
    return {
        "event_id": event_id,
        "event_latitude": latitude,
        "event_longitude": longitude,
    }


def _matrix():
    task_ids = ["link:4050000001:h0", "link:4050000002:h0"]
    origins = ["team-a", "team-b", *task_ids]
    team_times = {
        ("team-a", task_ids[0]): 5,
        ("team-a", task_ids[1]): 15,
        ("team-b", task_ids[0]): 15,
        ("team-b", task_ids[1]): 5,
    }
    routes = []
    for origin in origins:
        for destination in task_ids:
            if origin == destination:
                minutes = 0
            elif origin.startswith("team"):
                minutes = team_times[(origin, destination)]
            else:
                minutes = 5
            routes.append(
                {
                    "route_id": f"{origin}:{destination}",
                    "origin_id": origin,
                    "destination_task_id": destination,
                    "status": "ok",
                    "travel_time_minutes": minutes,
                    "distance_km": minutes,
                    "route_link_ids": [],
                }
            )
    return {
        "status": "pass",
        "scenario_id": "agent-test",
        "route_semantics": "test_network_time",
        "closed_link_ids": [],
        "routes": routes,
    }


def _quality_reports(status="pass"):
    return {
        "integrated_events": {"status": status, "failed_checks": []},
        "risk_forecasts": {"status": status, "failed_checks": []},
        "travel_time_matrix": {"status": "pass", "failed_checks": []},
    }


def _inputs():
    forecasts = [
        _forecast("event-1", "4050000001", 80),
        _forecast("event-2", "4050000002", 60),
    ]
    events = [
        _event("event-1", 33.01, 126.01),
        _event("event-2", 33.09, 126.09),
    ]
    return _resources(), forecasts, events, _matrix(), _quality_reports()


def test_request_parser_extracts_demo_constraints_and_alternatives():
    parsed = parse_agent_request(
        "팀 3개와 차량 3대로 2시간 안에 현재 순찰계획을 만들어줘. "
        "안전 우선과 업무 균형을 비교해줘."
    )

    assert parsed["team_count"] == 3
    assert parsed["vehicle_count"] == 3
    assert parsed["duration_hours"] == 2
    assert parsed["horizon_hours"] == 0
    assert parsed["requested_alternative_ids"] == [
        "safety_first",
        "balanced_operations",
    ]


def test_agent_flow_completes_all_seven_tools_and_requires_approval():
    result, report = run_agent_flow(
        "팀 2개와 차량 2대로 1시간 안에 현재 순찰계획을 만들어줘. "
        "안전 우선과 업무 균형을 비교해줘.",
        *_inputs(),
    )

    assert result["status"] == "pass"
    assert report["completed_tool_count"] == 7
    assert [row["tool_name"] for row in result["tool_trace"]] == [
        "request_interpreter",
        "data_quality_gate",
        "risk_task_builder",
        "travel_time_gate",
        "allocation_optimizer",
        "plan_validator",
        "result_explainer",
    ]
    assert all(row["status"] == "pass" for row in result["tool_trace"])
    assert len(result["final_response"]["alternatives"]) == 2
    assert result["final_response"]["manual_approval_required"] is True
    assert all(check["passed"] for check in result["validation_checks"])


def test_agent_flow_stops_on_request_resource_mismatch():
    result, report = run_agent_flow(
        "팀 3개와 차량 2대로 1시간 안에 현재 순찰계획을 만들어줘.",
        *_inputs(),
    )

    assert result["status"] == "fail"
    assert result["failure_reason"] == "data_quality_gate_failed"
    assert report["failed_tool"] == "data_quality_gate"
    assert report["completed_tool_count"] == 2


def test_agent_flow_stops_when_required_quality_report_is_missing():
    resources, forecasts, events, matrix, reports = _inputs()
    reports.pop("risk_forecasts")

    result, report = run_agent_flow(
        "팀 2개와 차량 2대로 1시간 안에 현재 순찰계획을 만들어줘.",
        resources,
        forecasts,
        events,
        matrix,
        reports,
    )

    assert result["failure_reason"] == "data_quality_gate_failed"
    assert report["failed_tool"] == "data_quality_gate"


def test_agent_flow_preserves_quality_limitations_in_final_response():
    resources, forecasts, events, matrix, reports = _inputs()
    reports["risk_forecasts"]["status"] = "pass_with_limitations"

    result, report = run_agent_flow(
        "팀 2개와 차량 2대로 1시간 안에 현재 순찰계획을 만들어줘.",
        resources,
        forecasts,
        events,
        matrix,
        reports,
    )

    assert result["status"] == "pass_with_limitations"
    assert report["quality_status"] == "pass_with_limitations"
    assert result["final_response"]["quality_limitations"]


def test_agent_flow_is_deterministic_for_identical_inputs():
    inputs = _inputs()
    request = "팀 2개와 차량 2대로 1시간 안에 현재 순찰계획을 만들어줘."

    first = run_agent_flow(request, *copy.deepcopy(inputs))
    second = run_agent_flow(request, *copy.deepcopy(inputs))

    assert first == second
