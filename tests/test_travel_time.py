from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.travel_time import (
    ROUTE_SEMANTICS,
    build_travel_time_matrix,
    recheck_allocation_plans,
    replay_cached_travel_matrix,
    travel_matrix_cache_key,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))


def _resources():
    return {
        "schema_version": 1,
        "scenario_id": "route-test",
        "planning": {
            "planning_start_at": "2026-11-13T12:00:00+09:00",
            "horizon_hours": 0,
            "default_service_minutes": 10,
            "baseline_speed_kph": 40,
            "max_tasks_per_team": 3,
        },
        "vehicles": [
            {
                "vehicle_id": "vehicle-1",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": [],
            }
        ],
        "teams": [
            {
                "team_id": "team-1",
                "personnel_count": 2,
                "vehicle_id": "vehicle-1",
                "start_latitude": 33.0,
                "start_longitude": 126.0,
                "shift_start_at": "2026-11-13T11:00:00+09:00",
                "shift_end_at": "2026-11-13T14:00:00+09:00",
                "skills": [],
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


def _nodes():
    return [
        {"node_id": "4050000001", "latitude": 33.00, "longitude": 126.00},
        {"node_id": "4050000002", "latitude": 33.00, "longitude": 126.01},
        {"node_id": "4050000003", "latitude": 33.00, "longitude": 126.02},
        {"node_id": "4050000004", "latitude": 33.01, "longitude": 126.01},
        {"node_id": "4050000005", "latitude": 33.00, "longitude": 126.03},
    ]


def _link(link_id, start, end, geometry, speed=60):
    return {
        "link_id": link_id,
        "start_node_id": start,
        "end_node_id": end,
        "maximum_speed_limit": speed,
        "geometry_wkt": geometry,
    }


def _links():
    return [
        _link(
            "4050000101",
            "4050000001",
            "4050000002",
            "LINESTRING (126.00 33.00,126.01 33.00)",
        ),
        _link(
            "4050000102",
            "4050000002",
            "4050000003",
            "LINESTRING (126.01 33.00,126.02 33.00)",
        ),
        _link(
            "4050000103",
            "4050000001",
            "4050000004",
            "LINESTRING (126.00 33.00,126.01 33.01)",
            speed=30,
        ),
        _link(
            "4050000104",
            "4050000004",
            "4050000003",
            "LINESTRING (126.01 33.01,126.02 33.00)",
            speed=30,
        ),
        _link(
            "4050000105",
            "4050000003",
            "4050000005",
            "LINESTRING (126.02 33.00,126.03 33.00)",
        ),
    ]


def _tasks():
    return [
        {
            "task_id": "link:4050000105:h0",
            "link_id": "4050000105",
            "latitude": 33.0,
            "longitude": 126.025,
            "excluded": False,
        }
    ]


def _team_route(result):
    return next(
        row for row in result["routes"] if row["origin_type"] == "team_start"
    )


def test_travel_matrix_uses_directed_fastest_path_and_preserves_semantics():
    result, report = build_travel_time_matrix(
        _resources(), _tasks(), _nodes(), _links(), generated_at=NOW
    )

    route = _team_route(result)
    assert report["status"] == "pass"
    assert report["route_count"] == 2
    assert route["status"] == "ok"
    assert route["route_semantics"] == ROUTE_SEMANTICS
    assert route["route_link_ids"] == [
        "4050000101",
        "4050000102",
        "4050000105",
    ]
    assert route["travel_time_minutes"] > 0
    assert route["destination_coordinate_offset_meters"] < 1


def test_closed_link_is_removed_and_route_uses_slower_detour():
    open_result, _ = build_travel_time_matrix(
        _resources(), _tasks(), _nodes(), _links(), generated_at=NOW
    )
    closed_result, closed_report = build_travel_time_matrix(
        _resources(),
        _tasks(),
        _nodes(),
        _links(),
        closed_link_ids=["4050000101"],
        generated_at=NOW,
    )

    open_route = _team_route(open_result)
    closed_route = _team_route(closed_result)
    assert closed_report["status"] == "pass"
    assert "4050000101" not in closed_route["route_link_ids"]
    assert closed_route["route_link_ids"] == [
        "4050000103",
        "4050000104",
        "4050000105",
    ]
    assert closed_route["travel_time_minutes"] > open_route["travel_time_minutes"]
    assert closed_report["closed_link_traversal_count"] == 0


def test_network_disconnection_uses_same_schema_and_explicit_failure():
    result, report = build_travel_time_matrix(
        _resources(),
        _tasks(),
        _nodes(),
        _links(),
        closed_link_ids=["4050000101", "4050000103"],
        generated_at=NOW,
    )

    team_route = _team_route(result)
    self_route = next(
        row for row in result["routes"] if row["origin_type"] == "field_task"
    )
    assert report["status"] == "pass_with_limitations"
    assert team_route["status"] == "unavailable"
    assert team_route["failure_reason"] == "no_directed_network_path"
    assert team_route["travel_time_minutes"] is None
    assert set(team_route) == set(self_route)
    assert report["failed_checks"] == []


def test_team_start_prefers_nearby_node_connected_to_a_task():
    nodes = [
        {"node_id": "4050000001", "latitude": 33.0, "longitude": 126.0},
        {"node_id": "4050000002", "latitude": 33.0, "longitude": 126.001},
        {"node_id": "4050000003", "latitude": 33.0, "longitude": 126.01},
        {"node_id": "4050000004", "latitude": 33.0, "longitude": 126.02},
    ]
    links = [
        _link(
            "4050000201",
            "4050000002",
            "4050000003",
            "LINESTRING (126.001 33.00,126.01 33.00)",
        ),
        _link(
            "4050000202",
            "4050000003",
            "4050000004",
            "LINESTRING (126.01 33.00,126.02 33.00)",
        ),
    ]
    tasks = [
        {
            "task_id": "link:4050000202:h0",
            "link_id": "4050000202",
            "latitude": 33.0,
            "longitude": 126.015,
            "excluded": False,
        }
    ]

    result, report = build_travel_time_matrix(
        _resources(), tasks, nodes, links, generated_at=NOW
    )

    route = _team_route(result)
    assert report["status"] == "pass"
    assert route["status"] == "ok"
    assert route["origin_node_id"] == "4050000002"
    assert route["route_link_ids"] == ["4050000201", "4050000202"]
    assert route["origin_connector_distance_meters"] > 0


def test_cache_replay_preserves_values_and_marks_provenance():
    result, report = build_travel_time_matrix(
        _resources(), _tasks(), _nodes(), _links(), generated_at=NOW
    )
    replay, replay_report = replay_cached_travel_matrix(
        result,
        cache_key="cache-key",
        resource_validation=report["resource_validation"],
        graph_report=report["graph"],
    )

    assert replay["execution"]["mode"] == "cache_replay"
    assert replay_report["source_mode_counts"] == {"cache_replay": 2}
    assert [row["travel_time_minutes"] for row in replay["routes"]] == [
        row["travel_time_minutes"] for row in result["routes"]
    ]
    assert all(row["source_mode"] == "cache_replay" for row in replay["routes"])


def test_cache_key_changes_when_a_closure_changes():
    common = {
        "resource_payload": _resources(),
        "field_tasks": _tasks(),
        "network_identity": {"nodes": "a", "links": "b"},
        "parameters": {"speed": 30},
    }

    open_key = travel_matrix_cache_key(**common, closed_link_ids=[])
    closed_key = travel_matrix_cache_key(
        **common, closed_link_ids=["4050000101"]
    )

    assert open_key != closed_key


def test_allocation_recheck_exposes_shift_violation_hidden_by_old_estimate():
    resources = _resources()
    matrix, _ = build_travel_time_matrix(
        resources, _tasks(), _nodes(), _links(), generated_at=NOW
    )
    plans = [
        {
            "strategy": "risk_first",
            "assignments": [
                {
                    "team_id": "team-1",
                    "task_id": "link:4050000105:h0",
                    "sequence": 1,
                    "service_minutes": 118,
                }
            ],
            "metrics": {"total_estimated_travel_minutes": 1.0},
        }
    ]

    recheck = recheck_allocation_plans(plans, matrix, resources)[0]

    assert recheck["network_total_travel_minutes"] > 2
    assert recheck["shift_exceeded_team_ids"] == ["team-1"]
    assert recheck["team_results"][0]["shift_exceeded_minutes"] > 0
    assert recheck["unavailable_route_leg_count"] == 0
