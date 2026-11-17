"""Build reviewed map rows for the RoadOps field-operations dashboard.

RoadOps 현장 운영 대시보드에서 사용하는 검토 완료 지도 행을 생성합니다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from typing import Any, Iterable, Mapping

from roadops.spatial import parse_link_geometry_wkt


MAP_SNAPSHOT_VERSION = "roadops-map-snapshot-v0.1"
MAJOR_ROAD_NAMES = {
    "1100로",
    "516로",
    "남조로",
    "번영로",
    "비자림로",
    "산록남로",
    "일주동로",
    "일주서로",
    "중산간동로",
    "중산간서로",
    "평화로",
}


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _weather_forecast_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate island grid forecasts into honest horizon ranges."""

    grouped: defaultdict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        try:
            horizon = int(row.get("horizon_hours") or 0)
        except (TypeError, ValueError):
            continue
        if horizon in {0, 1, 3, 6}:
            grouped[horizon].append(row)

    precipitation_labels = {
        "0": "강수 없음",
        "1": "비",
        "2": "비 또는 눈",
        "3": "눈",
        "5": "빗방울",
        "6": "빗방울 또는 눈날림",
        "7": "눈날림",
    }
    sky_labels = {"1": "맑음", "3": "구름 많음", "4": "흐림"}
    result: list[dict[str, Any]] = []
    for horizon in (0, 1, 3, 6):
        candidates = grouped.get(horizon, [])
        usable = [
            row
            for row in candidates
            if str(row.get("row_status")) == "usable"
            and str(row.get("forecast_status")) == "matched"
        ]
        temperatures = [
            value
            for value in (_number(row.get("forecast_temperature_c")) for row in usable)
            if value is not None
        ]
        wind_speeds = [
            value
            for value in (_number(row.get("forecast_wind_speed_mps")) for row in usable)
            if value is not None
        ]
        humidities = [
            value
            for value in (_number(row.get("forecast_humidity_percent")) for row in usable)
            if value is not None
        ]
        precipitation_codes = {
            str(row.get("forecast_precipitation_type") or "0").strip()
            for row in usable
        }
        active_precipitation = sorted(code for code in precipitation_codes if code != "0")
        precipitation = (
            " · ".join(
                precipitation_labels.get(code, "강수 가능")
                for code in active_precipitation
            )
            if active_precipitation
            else "강수 없음"
        )
        sky_codes = Counter(
            str(row.get("forecast_sky_code") or "").strip()
            for row in usable
            if str(row.get("forecast_sky_code") or "").strip()
        )
        target_counts = Counter(
            str(row.get("target_at"))
            for row in usable
            if row.get("target_at")
        )
        sources = sorted(
            {
                str(row.get("forecast_source_id"))
                for row in usable
                if row.get("forecast_source_id")
            }
        )
        quality_flags = sorted(
            {
                flag
                for row in candidates
                for flag in str(row.get("quality_flags") or "").split("|")
                if flag
            }
        )
        result.append(
            {
                "horizon_hours": horizon,
                "target_at": target_counts.most_common(1)[0][0] if target_counts else None,
                "status": "usable" if usable else "unavailable",
                "grid_count": len(candidates),
                "usable_grid_count": len(usable),
                "coverage_ratio": (
                    round(len(usable) / len(candidates), 3) if candidates else 0.0
                ),
                "temperature_min_c": round(min(temperatures), 1) if temperatures else None,
                "temperature_max_c": round(max(temperatures), 1) if temperatures else None,
                "humidity_min_percent": round(min(humidities), 1) if humidities else None,
                "humidity_max_percent": round(max(humidities), 1) if humidities else None,
                "maximum_wind_speed_mps": round(max(wind_speeds), 1) if wind_speeds else None,
                "precipitation_summary": precipitation if usable else "예보 확인 불가",
                "sky_summary": (
                    sky_labels.get(sky_codes.most_common(1)[0][0], "하늘 상태 확인 필요")
                    if sky_codes
                    else "하늘 상태 확인 불가"
                ),
                "forecast_sources": " | ".join(sources),
                "quality_flags": " | ".join(quality_flags) or "none",
            }
        )
    return result


def _parts(row: Mapping[str, Any]) -> list[list[list[float]]]:
    geometry = parse_link_geometry_wkt(row.get("geometry_wkt"))
    if geometry is None:
        return []
    return [
        [[round(point.longitude, 8), round(point.latitude, 8)] for point in part]
        for part in geometry
    ]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _route_link_ids(payload: Mapping[str, Any]) -> set[str]:
    link_ids: set[str] = set()
    for alternative in payload.get("alternatives", []):
        for assignment in alternative.get("assignments", []):
            link_ids.update(str(value) for value in assignment.get("route_link_ids", []))
    return link_ids


def _replan_link_ids(payload: Mapping[str, Any]) -> set[str]:
    link_ids: set[str] = set()
    for result in payload.get("scenario_results", []):
        link_ids.update(str(value) for value in result.get("scenario", {}).get("affected_link_ids", []))
        for assignment in result.get("replanned_plan", {}).get("assignments", []):
            link_ids.update(str(value) for value in assignment.get("route_link_ids", []))
    return link_ids


def _geometry_for_links(
    link_ids: Iterable[str], link_geometries: Mapping[str, list[list[list[float]]]]
) -> list[list[list[float]]]:
    result: list[list[list[float]]] = []
    for link_id in link_ids:
        result.extend(link_geometries.get(str(link_id), []))
    return result


def _aggregate_risks(
    rows: Iterable[Mapping[str, Any]],
    link_geometries: Mapping[str, list[list[list[float]]]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        link_id = str(row.get("effective_link_id") or "")
        if not link_id:
            continue
        try:
            horizon = int(row.get("horizon_hours") or 0)
        except (TypeError, ValueError):
            continue
        grouped[(horizon, link_id)].append(row)

    result: list[dict[str, Any]] = []
    for (horizon, link_id), candidates in sorted(grouped.items()):
        ranked = sorted(
            candidates,
            key=lambda item: (_number(item.get("forecast_priority_score")) or -1.0),
            reverse=True,
        )
        representative = ranked[0]
        scores = [
            value
            for value in (_number(row.get("forecast_priority_score")) for row in candidates)
            if value is not None
        ]
        lower_bounds = [
            value
            for value in (_number(row.get("forecast_score_lower_bound")) for row in candidates)
            if value is not None
        ]
        upper_bounds = [
            value
            for value in (_number(row.get("forecast_score_upper_bound")) for row in candidates)
            if value is not None
        ]
        drivers = sorted(
            {
                driver
                for row in candidates
                for driver in str(row.get("risk_drivers") or "").split("|")
                if driver
            }
        )
        flags = sorted(
            {
                flag
                for row in candidates
                for flag in str(row.get("quality_flags") or "").split("|")
                if flag
            }
        )
        geometry = link_geometries.get(link_id, [])
        result.append(
            {
                "horizon_hours": horizon,
                "link_id": link_id,
                "road_name": representative.get("road_name") or "도로명 미상",
                "target_at": representative.get("target_at"),
                "generated_at": representative.get("generated_at"),
                "forecast_status": representative.get("forecast_status"),
                "forecast_semantics": representative.get("forecast_semantics"),
                "ranking_eligible": any(
                    _boolean(row.get("ranking_eligible")) for row in candidates
                ),
                "priority_score": round(max(scores), 3) if scores else None,
                "score_lower_bound": round(min(lower_bounds), 3) if lower_bounds else None,
                "score_upper_bound": round(max(upper_bounds), 3) if upper_bounds else None,
                "uncertainty_width": (
                    round(max(upper_bounds) - min(lower_bounds), 3)
                    if lower_bounds and upper_bounds
                    else None
                ),
                "risk_level": representative.get("risk_level"),
                "evidence_coverage_ratio": _number(
                    representative.get("evidence_coverage_ratio")
                ),
                "integration_class": representative.get("integration_class"),
                "event_count": len(candidates),
                "event_types": ", ".join(
                    sorted({str(row.get("event_type")) for row in candidates})
                ),
                "risk_drivers": " | ".join(drivers),
                "quality_flags": " | ".join(flags) or "none",
                "weather_evidence_kind": representative.get("weather_evidence_kind"),
                "weather_valid_at": representative.get("weather_valid_at"),
                "gateway_inflow_status": representative.get("gateway_inflow_status"),
                "geometry_json": _json(geometry),
                "has_geometry": bool(geometry),
            }
        )
    return result


def _plan_routes(
    optimized: Mapping[str, Any],
    link_geometries: Mapping[str, list[list[list[float]]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alternative in optimized.get("alternatives", []):
        alternative_id = str(alternative.get("alternative_id"))
        for assignment in alternative.get("assignments", []):
            link_ids = [str(value) for value in assignment.get("route_link_ids", [])]
            rows.append(
                {
                    "alternative_id": alternative_id,
                    "objective": alternative.get("objective"),
                    "team_id": assignment.get("team_id"),
                    "sequence": assignment.get("sequence"),
                    "task_id": assignment.get("task_id"),
                    "link_id": assignment.get("link_id"),
                    "road_name": assignment.get("road_name"),
                    "priority_score": assignment.get("priority_score"),
                    "travel_minutes": assignment.get("travel_minutes"),
                    "service_minutes": assignment.get("service_minutes"),
                    "cumulative_minutes": assignment.get("cumulative_minutes"),
                    "route_link_count": len(link_ids),
                    "geometry_json": _json(
                        _geometry_for_links(link_ids, link_geometries)
                    ),
                }
            )
    return rows


def _plan_metrics(optimized: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alternative in optimized.get("alternatives", []):
        metrics = dict(alternative.get("metrics", {}))
        rows.append(
            {
                "alternative_id": alternative.get("alternative_id"),
                "objective": alternative.get("objective"),
                **metrics,
            }
        )
    return rows


def _replan_rows(
    optimized: Mapping[str, Any],
    replanning: Mapping[str, Any],
    link_geometries: Mapping[str, list[list[list[float]]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base_alternative_id = str(replanning.get("base_alternative_id") or "safety_first")
    base_alternative = next(
        (
            item
            for item in optimized.get("alternatives", [])
            if str(item.get("alternative_id")) == base_alternative_id
        ),
        {},
    )
    base_assignments = list(base_alternative.get("assignments", []))
    route_rows: list[dict[str, Any]] = []
    scenario_rows: list[dict[str, Any]] = []
    impact_rows: list[dict[str, Any]] = []

    for result in replanning.get("scenario_results", []):
        scenario = result.get("scenario", {})
        scenario_id = str(scenario.get("scenario_id"))
        affected_teams = {str(value) for value in result.get("affected_team_ids", [])}
        for stage, assignments in (
            ("before", base_assignments),
            ("after", result.get("replanned_plan", {}).get("assignments", [])),
        ):
            for assignment in assignments:
                team_id = str(assignment.get("team_id"))
                if team_id not in affected_teams:
                    continue
                link_ids = [str(value) for value in assignment.get("route_link_ids", [])]
                route_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "scenario_type": scenario.get("scenario_type"),
                        "plan_stage": stage,
                        "team_id": team_id,
                        "sequence": assignment.get("sequence"),
                        "task_id": assignment.get("task_id"),
                        "road_name": assignment.get("road_name"),
                        "travel_minutes": assignment.get("travel_minutes"),
                        "cumulative_minutes": assignment.get("cumulative_minutes"),
                        "replan_status": assignment.get("replan_status") or "base_plan",
                        "geometry_json": _json(
                            _geometry_for_links(link_ids, link_geometries)
                        ),
                    }
                )

        explanation = result.get("explanation", {})
        metric_delta = explanation.get("metric_delta", {})
        scenario_rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario.get("scenario_type"),
                "semantics": scenario.get("semantics"),
                "summary": explanation.get("summary"),
                "affected_team_ids": ", ".join(sorted(affected_teams)),
                "affected_team_count": len(affected_teams),
                "unchanged_team_ids": ", ".join(
                    str(value) for value in explanation.get("unchanged_team_ids", [])
                ),
                "change_reasons": " | ".join(
                    str(value) for value in explanation.get("change_reason_messages", [])
                ),
                "travel_minutes_delta": metric_delta.get(
                    "network_total_travel_minutes"
                ),
                "coverage_ratio_delta": metric_delta.get(
                    "risk_weighted_coverage_ratio"
                ),
                "violation_count_delta": metric_delta.get(
                    "constraint_violation_count"
                ),
                "manual_approval_required": bool(
                    result.get("manual_approval_required")
                ),
            }
        )
        for link_id in scenario.get("affected_link_ids", []):
            geometry = link_geometries.get(str(link_id), [])
            impact_rows.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_type": scenario.get("scenario_type"),
                    "link_id": str(link_id),
                    "semantics": scenario.get("semantics"),
                    "geometry_json": _json(geometry),
                    "has_geometry": bool(geometry),
                }
            )
    return route_rows, scenario_rows, impact_rows


def _governance_authority_rows(
    resources: Mapping[str, Any],
) -> list[dict[str, Any]]:
    governance = resources.get("governance", {})
    agencies = {
        str(row.get("agency_id")): row
        for row in governance.get("agencies", [])
        if row.get("agency_id")
    }
    sources = {
        str(row.get("source_id")): row
        for row in governance.get("source_records", [])
        if row.get("source_id")
    }
    approvers = {
        str(row.get("approver_id")): row
        for row in governance.get("approvers", [])
        if row.get("approver_id")
    }
    channels = {
        str(row.get("handoff_type")): row
        for row in governance.get("handoff_channels", [])
        if row.get("handoff_type")
    }
    default_approver_id = governance.get("defaults", {}).get(
        "dispatch_approver_id"
    )
    approver = approvers.get(str(default_approver_id), {})
    rows: list[dict[str, Any]] = []
    for authority in governance.get("authority_records", []):
        source_ids = [str(value) for value in authority.get("source_ids", [])]
        managing_agency = agencies.get(
            str(authority.get("managing_agency_id")), {}
        )
        city_agency = agencies.get(
            str(authority.get("administrative_city_agency_id")), {}
        )
        row = {
            **dict(authority),
            "managing_agency_name": managing_agency.get("agency_name"),
            "managing_department_name": managing_agency.get("department_name"),
            "administrative_city_agency_name": city_agency.get("agency_name"),
            "dispatch_approver_id": default_approver_id,
            "dispatch_approver_role": approver.get("role"),
            "dispatch_approver_display_name": approver.get("display_name"),
            "dispatch_approver_verification_status": approver.get(
                "verification_status"
            ),
            "source_titles": " | ".join(
                str(sources[source_id].get("title"))
                for source_id in source_ids
                if source_id in sources
            ),
            "source_urls": " | ".join(
                str(sources[source_id].get("url"))
                for source_id in source_ids
                if source_id in sources
            ),
        }
        for handoff_type in ("police", "fire"):
            channel = channels.get(handoff_type, {})
            target = agencies.get(str(channel.get("target_agency_id")), {})
            row[f"{handoff_type}_channel_id"] = channel.get("channel_id")
            row[f"{handoff_type}_agency_name"] = target.get("agency_name")
            row[f"{handoff_type}_channel_status"] = channel.get("status")
            row[f"{handoff_type}_contact_method"] = channel.get(
                "contact_method"
            )
            row[f"{handoff_type}_automation_status"] = channel.get(
                "automation_status"
            )
        rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("link_id")))


def build_map_snapshot(
    *,
    risk_rows: Iterable[Mapping[str, Any]],
    weather_rows: Iterable[Mapping[str, Any]],
    optimized: Mapping[str, Any],
    replanning: Mapping[str, Any],
    resources: Mapping[str, Any],
    allocation: Mapping[str, Any],
    travel_time: Mapping[str, Any] | None = None,
    accident_rows: Iterable[Mapping[str, Any]] = (),
    historical_similarity_rows: Iterable[Mapping[str, Any]] = (),
    crime_statistic_rows: Iterable[Mapping[str, Any]] = (),
    reverse_geocode_rows: Iterable[Mapping[str, Any]] = (),
    link_rows: Iterable[Mapping[str, Any]],
    generated_at: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Build map query rows and a deterministic quality report."""

    risk_rows = list(risk_rows)
    weather_rows = list(weather_rows)
    accident_hotspots = [dict(row) for row in accident_rows]
    historical_similarity = [dict(row) for row in historical_similarity_rows]
    crime_statistics = [dict(row) for row in crime_statistic_rows]
    location_by_link = {
        str(row.get("link_id")): dict(row)
        for row in reverse_geocode_rows
        if row.get("link_id")
    }
    required_link_ids = {
        str(row.get("effective_link_id"))
        for row in risk_rows
        if row.get("effective_link_id")
    }
    required_link_ids.update(_route_link_ids(optimized))
    required_link_ids.update(_replan_link_ids(replanning))

    link_geometries: dict[str, list[list[list[float]]]] = {}
    background_groups: dict[str, list[list[list[float]]]] = defaultdict(list)
    background_link_count = 0
    for row in link_rows:
        link_id = str(row.get("link_id") or "")
        road_name = str(row.get("road_name") or "").strip()
        needs_geometry = link_id in required_link_ids or road_name in MAJOR_ROAD_NAMES
        if not needs_geometry:
            continue
        geometry = _parts(row)
        if not geometry:
            continue
        if link_id in required_link_ids:
            link_geometries[link_id] = geometry
        if road_name in MAJOR_ROAD_NAMES:
            background_groups[road_name].extend(geometry)
            background_link_count += 1

    background_rows = [
        {
            "road_name": road_name,
            "link_count": len(parts),
            "geometry_json": _json(parts),
        }
        for road_name, parts in sorted(background_groups.items())
    ]
    risk_links = _aggregate_risks(risk_rows, link_geometries)
    weather_forecast = _weather_forecast_rows(weather_rows)
    plan_routes = _plan_routes(optimized, link_geometries)
    plan_metrics = _plan_metrics(optimized)
    replan_routes, scenario_summary, scenario_impacts = _replan_rows(
        optimized, replanning, link_geometries
    )

    field_tasks = [dict(item) for item in allocation.get("field_tasks", [])]
    governance = resources.get("governance", {})
    agencies = {
        str(row.get("agency_id")): row
        for row in governance.get("agencies", [])
        if row.get("agency_id")
    }
    governance_authorities = _governance_authority_rows(resources)
    for collection in (risk_links, field_tasks, governance_authorities):
        for row in collection:
            location = location_by_link.get(str(row.get("link_id")))
            if location:
                row.update(
                    {
                        key: location.get(key)
                        for key in (
                            "location_label",
                            "display_address",
                            "address_precision",
                            "lot_or_house_number",
                            "intersection_name",
                            "provider",
                        )
                    }
                )
    vehicles = {
        str(vehicle.get("vehicle_id")): vehicle
        for vehicle in resources.get("vehicles", [])
        if vehicle.get("vehicle_id")
    }
    planning = resources.get("planning", {})
    teams = [
        {
            "team_id": team.get("team_id"),
            "team_name": team.get("team_name"),
            "vehicle_id": team.get("vehicle_id"),
            "vehicle_type": vehicles.get(str(team.get("vehicle_id")), {}).get(
                "vehicle_type"
            ),
            "vehicle_status": vehicles.get(str(team.get("vehicle_id")), {}).get(
                "status"
            ),
            "vehicle_personnel_capacity": vehicles.get(
                str(team.get("vehicle_id")), {}
            ).get("personnel_capacity"),
            "vehicle_equipment": vehicles.get(
                str(team.get("vehicle_id")), {}
            ).get("equipment", []),
            "personnel_count": team.get("personnel_count"),
            "start_latitude": team.get("start_latitude"),
            "start_longitude": team.get("start_longitude"),
            "start_location_name": team.get("start_location_name"),
            "start_location_address": team.get("start_location_address"),
            "start_location_kind": team.get("start_location_kind"),
            "start_location_source_ids": team.get(
                "start_location_source_ids", []
            ),
            "start_coordinate_method": team.get("start_coordinate_method"),
            "start_coordinate_precision": team.get(
                "start_coordinate_precision"
            ),
            "shift_start_at": team.get("shift_start_at"),
            "shift_end_at": team.get("shift_end_at"),
            "skills": team.get("skills", []),
            "equipment": team.get("equipment", []),
            "max_tasks_per_team": planning.get("max_tasks_per_team"),
            "managing_agency_id": team.get("managing_agency_id"),
            "managing_agency_name": agencies.get(
                str(team.get("managing_agency_id")), {}
            ).get("agency_name"),
            "authorized_road_jurisdictions": team.get(
                "authorized_road_jurisdictions", []
            ),
        }
        for team in resources.get("teams", [])
    ]

    target_times = [
        datetime.fromisoformat(str(row["target_at"]).replace("Z", "+00:00"))
        for row in risk_rows
        if row.get("target_at")
    ]
    generated_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    latest_target = max(target_times) if target_times else None
    snapshot_age_minutes = (
        max(0.0, (generated_dt - latest_target).total_seconds() / 60)
        if latest_target and generated_dt.tzinfo and latest_target.tzinfo
        else None
    )
    travel_time = travel_time or {}
    travel_semantics = str(
        travel_time.get("route_semantics")
        or "free_flow_speed_limit_estimate_not_live_eta"
    )
    live_eta = travel_semantics == "its_live_speed_eta_with_speed_limit_fallback"
    traffic_profile = travel_time.get("parameters", {}).get("traffic_profile", {})
    availability = [
        {
            "data_layer": "its_live_eta",
            "display_name": "ITS 실시간 이동시간",
            "status": "available" if live_eta else "unavailable",
            "reason": (
                f"제주 ITS 최신 속도 {int(traffic_profile.get('fresh_speed_link_count') or 0):,}개 링크를 적용하고 미관측 링크는 제한속도로 보완"
                if live_eta
                else "신선한 ITS 속도를 확보하지 못해 제한속도 기반 이동시간을 사용"
            ),
            "score_contribution": None,
        },
        {
            "data_layer": "gateway_inflow_pressure",
            "display_name": "공항·항만 유입압력",
            "status": "unavailable",
            "reason": "승인된 API의 실제 운항·여객 실응답을 아직 확보하지 못해 점수와 지도에 반영하지 않음",
            "score_contribution": None,
        }
    ]
    metadata = [
        {
            "snapshot_version": MAP_SNAPSHOT_VERSION,
            "generated_at": generated_at,
            "latest_risk_target_at": latest_target.isoformat() if latest_target else None,
            "snapshot_age_minutes": (
                round(snapshot_age_minutes, 1) if snapshot_age_minutes is not None else None
            ),
            "freshness_status": (
                "stale_snapshot"
                if snapshot_age_minutes is None or snapshot_age_minutes > 120
                else "recent_snapshot"
            ),
            "risk_semantics": "operational_priority_scenario_not_accident_probability",
            "travel_semantics": travel_semantics,
            "live_eta_available": live_eta,
            "live_eta_speed_link_count": int(
                traffic_profile.get("fresh_speed_link_count") or 0
            ),
            "live_eta_fallback_note": (
                "ITS 미관측 링크는 제한속도 또는 기본속도를 사용"
                if live_eta
                else "전체 경로가 제한속도 또는 기본속도 추정"
            ),
            "scenario_semantics": "what_if_not_observed",
            "governance_effective_at": governance.get("effective_at"),
            "authority_semantics": (
                "official_road_class_and_admin_boundary_with_explicit_"
                "delegation_review_status"
            ),
        }
    ]

    missing_required = sorted(required_link_ids - set(link_geometries))
    missing_risk = sorted(
        row["link_id"] for row in risk_links if not row.get("has_geometry")
    )
    missing_impacts = sorted(
        row["link_id"] for row in scenario_impacts if not row.get("has_geometry")
    )
    route_rows_without_geometry = sum(
        1
        for row in plan_routes + replan_routes
        if row.get("geometry_json") == "[]"
    )
    status = (
        "pass"
        if not missing_required
        and not missing_risk
        and not missing_impacts
        and route_rows_without_geometry == 0
        else "degraded"
    )
    quality = {
        "schema_version": 1,
        "snapshot_version": MAP_SNAPSHOT_VERSION,
        "status": status,
        "generated_at": generated_at,
        "counts": {
            "background_road_groups": len(background_rows),
            "background_link_count": background_link_count,
            "risk_link_rows": len(risk_links),
            "plan_route_rows": len(plan_routes),
            "replan_route_rows": len(replan_routes),
            "scenario_count": len(scenario_summary),
            "team_count": len(teams),
            "task_count": len(field_tasks),
            "authority_record_count": len(governance_authorities),
            "weather_forecast_horizon_count": len(weather_forecast),
            "accident_hotspot_count": len(accident_hotspots),
            "historical_similarity_match_count": len(historical_similarity),
            "crime_statistic_city_count": len(crime_statistics),
            "reverse_geocoded_link_count": len(location_by_link),
        },
        "missing_required_link_ids": missing_required,
        "missing_risk_link_ids": missing_risk,
        "missing_scenario_impact_link_ids": missing_impacts,
        "route_rows_without_geometry": route_rows_without_geometry,
        "limitations": [
            "snapshot_not_live_feed",
            *(
                ["its_unobserved_links_use_speed_limit_fallback"]
                if live_eta
                else ["travel_time_is_free_flow_estimate_not_live_eta"]
            ),
            "replanning_layers_are_what_if_scenarios",
            "gateway_inflow_pressure_unavailable_not_scored",
            "manual_approval_required_before_field_dispatch",
            "named_approver_requires_operator_configuration",
            "dong_urban_area_delegation_requires_segment_review",
        ],
    }
    queries = {
        "map_metadata": metadata,
        "weather_forecast": weather_forecast,
        "accident_hotspots": accident_hotspots,
        "historical_similarity": historical_similarity,
        "crime_statistics": crime_statistics,
        "road_background": background_rows,
        "risk_links": risk_links,
        "field_tasks": field_tasks,
        "governance_authorities": governance_authorities,
        "teams": teams,
        "plan_routes": plan_routes,
        "plan_metrics": plan_metrics,
        "replan_routes": replan_routes,
        "scenario_summary": scenario_summary,
        "scenario_impacts": scenario_impacts,
        "data_availability": availability,
    }
    return queries, quality
