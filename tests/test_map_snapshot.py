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
        "planning": {"max_tasks_per_team": 3},
        "governance": {
            "effective_at": "2026-11-17",
            "source_records": [
                {
                    "source_id": "official-source",
                    "title": "official source",
                    "url": "https://example.go.kr/source",
                }
            ],
            "agencies": [
                {
                    "agency_id": "province-road",
                    "agency_name": "제주특별자치도 도로관리과",
                    "department_name": "도로관리과",
                },
                {"agency_id": "jeju-city", "agency_name": "제주시 건설과"},
                {"agency_id": "police", "agency_name": "제주경찰청"},
                {"agency_id": "fire", "agency_name": "제주소방안전본부"},
            ],
            "approvers": [
                {
                    "approver_id": "operator-approver",
                    "role": "운영기관 지정 승인권자",
                    "display_name": "지정 필요",
                    "verification_status": "operator_configuration_required",
                }
            ],
            "handoff_channels": [
                {"handoff_type": "police", "channel_id": "police-channel", "target_agency_id": "police", "status": "active"},
                {"handoff_type": "fire", "channel_id": "fire-channel", "target_agency_id": "fire", "status": "active"},
            ],
            "defaults": {"dispatch_approver_id": "operator-approver"},
            "authority_records": [
                {
                    "link_id": "4050000001",
                    "road_class": "지방도",
                    "road_number": "1135",
                    "road_name": "평화로",
                    "administrative_city": "제주시",
                    "administrative_unit": "애월읍",
                    "administrative_city_agency_id": "jeju-city",
                    "managing_agency_id": "province-road",
                    "road_jurisdiction": "jeju-provincial-road-1135",
                    "jurisdiction_basis": "official basis",
                    "authority_status": "official_provincial_road_scope",
                    "source_ids": ["official-source"],
                }
            ],
        },
        "vehicles": [
            {
                "vehicle_id": "patrol-east-01",
                "vehicle_type": "patrol_car",
                "personnel_capacity": 2,
                "status": "available",
                "equipment": ["traffic_cones"],
            }
        ],
        "teams": [
            {
                "team_id": "team-east",
                "team_name": "동부팀",
                "vehicle_id": "patrol-east-01",
                "personnel_count": 2,
                "start_latitude": 33.4,
                "start_longitude": 126.6,
                "skills": ["general_patrol"],
                "managing_agency_id": "province-road",
                "authorized_road_jurisdictions": ["jeju-provincial-road-1135"],
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
        weather_rows=[
            {
                "horizon_hours": "0",
                "target_at": "2026-11-13T01:00:00+09:00",
                "row_status": "usable",
                "forecast_status": "matched",
                "forecast_temperature_c": "12",
                "forecast_precipitation_type": "0",
                "forecast_sky_code": "3",
                "forecast_humidity_percent": "80",
                "forecast_wind_speed_mps": "2.5",
                "forecast_source_id": "kma_ultra_short_forecast",
            },
            {
                "horizon_hours": "0",
                "target_at": "2026-11-13T01:00:00+09:00",
                "row_status": "usable",
                "forecast_status": "matched",
                "forecast_temperature_c": "15",
                "forecast_precipitation_type": "1",
                "forecast_sky_code": "4",
                "forecast_humidity_percent": "90",
                "forecast_wind_speed_mps": "4.2",
                "forecast_source_id": "kma_ultra_short_forecast",
            },
        ],
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
    assert queries["teams"][0]["vehicle_status"] == "available"
    assert queries["teams"][0]["vehicle_personnel_capacity"] == 2
    assert queries["teams"][0]["max_tasks_per_team"] == 3
    assert queries["teams"][0]["managing_agency_name"] == (
        "제주특별자치도 도로관리과"
    )
    assert "start_location_name" in queries["teams"][0]
    assert "start_location_address" in queries["teams"][0]
    authority = queries["governance_authorities"][0]
    assert authority["administrative_city"] == "제주시"
    assert authority["road_jurisdiction"] == "jeju-provincial-road-1135"
    assert authority["dispatch_approver_verification_status"] == (
        "operator_configuration_required"
    )
    assert quality["counts"]["authority_record_count"] == 1
    current_weather = queries["weather_forecast"][0]
    assert current_weather["temperature_min_c"] == 12.0
    assert current_weather["temperature_max_c"] == 15.0
    assert current_weather["precipitation_summary"] == "비"
    assert current_weather["maximum_wind_speed_mps"] == 4.2


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
        weather_rows=[],
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
