import json

from roadops.map_snapshot import build_map_snapshot


def _link(link_id, road_name, coordinates):
    points = ",".join(f"{lon} {lat}" for lon, lat in coordinates)
    return {
        "link_id": link_id,
        "road_name": road_name,
        "geometry_wkt": f"LINESTRING ({points})",
    }


def test_build_map_snapshot_aggregates_risk_and_marks_unavailable_gateway():
    risk_rows = [
        {
            "effective_link_id": "4050000001",
            "horizon_hours": "0",
            "target_at": "2026-11-12T22:00:00+09:00",
            "generated_at": "2026-11-12T22:01:00+09:00",
            "road_name": "평화로",
            "forecast_status": "degraded",
            "forecast_semantics": "operational_priority_scenario_not_accident_probability",
            "ranking_eligible": "True",
            "forecast_priority_score": "40",
            "forecast_score_lower_bound": "35",
            "forecast_score_upper_bound": "45",
            "risk_level": "moderate",
            "evidence_coverage_ratio": "0.8",
            "integration_class": "exact_link_id",
            "event_type": "road_event",
            "risk_drivers": "event:closure:10",
            "quality_flags": "timestamp_missing",
            "weather_evidence_kind": "observation",
            "gateway_inflow_status": "unavailable",
        },
        {
            "effective_link_id": "4050000001",
            "horizon_hours": "0",
            "target_at": "2026-11-12T22:00:00+09:00",
            "generated_at": "2026-11-12T22:01:00+09:00",
            "road_name": "평화로",
            "forecast_status": "degraded",
            "forecast_semantics": "operational_priority_scenario_not_accident_probability",
            "ranking_eligible": "True",
            "forecast_priority_score": "55",
            "forecast_score_lower_bound": "50",
            "forecast_score_upper_bound": "65",
            "risk_level": "high",
            "evidence_coverage_ratio": "1",
            "integration_class": "exact_link_id",
            "event_type": "road_weather",
            "risk_drivers": "weather:rain:12",
            "quality_flags": "",
            "weather_evidence_kind": "observation",
            "gateway_inflow_status": "unavailable",
        },
    ]
    optimized = {
        "alternatives": [
            {
                "alternative_id": "safety_first",
                "objective": "maximize_risk_coverage",
                "metrics": {"risk_weighted_coverage_ratio": 1.0},
                "assignments": [
                    {
                        "team_id": "team-east",
                        "sequence": 1,
                        "task_id": "task-1",
                        "link_id": "4050000001",
                        "route_link_ids": ["4050000001"],
                        "travel_minutes": 5,
                    }
                ],
            }
        ]
    }
    replanning = {
        "base_alternative_id": "safety_first",
        "scenario_results": [],
    }
    resources = {
        "teams": [
            {
                "team_id": "team-east",
                "team_name": "동부팀",
                "start_latitude": 33.4,
                "start_longitude": 126.6,
            }
        ]
    }
    allocation = {
        "field_tasks": [
            {
                "task_id": "task-1",
                "link_id": "4050000001",
                "latitude": 33.4,
                "longitude": 126.4,
            }
        ]
    }
    queries, quality = build_map_snapshot(
        risk_rows=risk_rows,
        optimized=optimized,
        replanning=replanning,
        resources=resources,
        allocation=allocation,
        link_rows=[
            _link(
                "4050000001",
                "평화로",
                [(126.3, 33.3), (126.4, 33.4)],
            )
        ],
        generated_at="2026-11-13T01:00:00+09:00",
    )

    assert quality["status"] == "pass"
    assert len(queries["risk_links"]) == 1
    risk = queries["risk_links"][0]
    assert risk["priority_score"] == 55.0
    assert risk["score_lower_bound"] == 35.0
    assert risk["score_upper_bound"] == 65.0
    assert risk["event_count"] == 2
    assert "closure" in risk["risk_drivers"]
    assert "rain" in risk["risk_drivers"]
    assert json.loads(risk["geometry_json"])[0][0] == [126.3, 33.3]
    assert queries["data_availability"][0]["status"] == "unavailable"
    assert queries["map_metadata"][0]["freshness_status"] == "stale_snapshot"


def test_build_map_snapshot_reports_missing_required_geometry():
    queries, quality = build_map_snapshot(
        risk_rows=[
            {
                "effective_link_id": "4050000999",
                "horizon_hours": "3",
                "target_at": "2026-11-13T01:00:00+09:00",
                "forecast_priority_score": "20",
                "forecast_score_lower_bound": "10",
                "forecast_score_upper_bound": "30",
            }
        ],
        optimized={"alternatives": []},
        replanning={"scenario_results": []},
        resources={"teams": []},
        allocation={"field_tasks": []},
        link_rows=[],
        generated_at="2026-11-13T01:00:00+09:00",
    )

    assert quality["status"] == "degraded"
    assert quality["missing_required_link_ids"] == ["4050000999"]
    assert queries["risk_links"][0]["has_geometry"] is False
