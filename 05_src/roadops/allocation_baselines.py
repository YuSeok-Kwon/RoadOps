"""Build deterministic risk-first and nearest RoadOps allocation baselines.

동일 링크 이벤트를 한 작업으로 묶고 자원·근무·장비 제약 아래 두 기준선을 비교합니다.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from statistics import pvariance
from typing import Any, Iterable, Mapping

from roadops.resources import institutional_eligibility, validate_resource_plan
from roadops.spatial import normalize_link_id


ALLOCATION_VERSION = "roadops-allocation-baselines-v0.1"
HIGH_PRIORITY_SCORE = 50.0


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _override_or_default(
    override: Mapping[str, Any], defaults: Mapping[str, Any], field: str
) -> Any:
    value = override.get(field)
    return defaults.get(field) if value is None else value


def _datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("allocation datetimes must include a UTC offset")
    return parsed


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance, used only as a transparent baseline proxy."""

    earth_radius_km = 6371.0088
    lat_a = radians(latitude_a)
    lat_b = radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = radians(longitude_b - longitude_a)
    haversine = sin(delta_lat / 2) ** 2 + (
        cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(haversine))


def _event_coordinate_index(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[float, float]]:
    index: dict[str, tuple[float, float]] = {}
    for row in rows:
        event_id = _text(row.get("event_id"))
        latitude = _number(row.get("event_latitude"))
        longitude = _number(row.get("event_longitude"))
        if event_id and latitude is not None and longitude is not None:
            index[event_id] = (latitude, longitude)
    return index


def build_field_tasks(
    forecast_rows: Iterable[Mapping[str, Any]],
    integrated_event_rows: Iterable[Mapping[str, Any]],
    *,
    horizon_hours: int,
    resource_plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse eligible forecast events into one field task per effective link."""

    coordinates = _event_coordinate_index(integrated_event_rows)
    eligible: list[dict[str, Any]] = []
    horizon_row_count = 0
    for source in forecast_rows:
        if _integer(source.get("horizon_hours")) != horizon_hours:
            continue
        horizon_row_count += 1
        link_id = normalize_link_id(source.get("effective_link_id"))
        score = _number(source.get("forecast_priority_score"))
        if not (
            link_id
            and score is not None
            and _truthy(source.get("score_available"))
            and _truthy(source.get("ranking_eligible"))
        ):
            continue
        row = dict(source)
        row["effective_link_id"] = link_id
        row["forecast_priority_score"] = score
        eligible.append(row)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        grouped.setdefault(str(row["effective_link_id"]), []).append(row)

    override_index = {
        str(row["link_id"]): row
        for row in resource_plan["constraints"]["task_overrides"]
    }
    mandatory_links = set(resource_plan["constraints"]["mandatory_link_ids"])
    excluded_links = set(resource_plan["constraints"]["excluded_link_ids"])
    fixed_index = {
        str(row["link_id"]): str(row["team_id"])
        for row in resource_plan["constraints"]["fixed_assignments"]
    }
    default_service = float(
        resource_plan["planning"]["default_service_minutes"]
    )
    governance_defaults = resource_plan.get("governance", {}).get("defaults", {})
    channel_index = {
        str(row["channel_id"]): row
        for row in resource_plan.get("governance", {}).get(
            "handoff_channels", []
        )
        if row.get("channel_id")
    }
    tasks: list[dict[str, Any]] = []
    for link_id, members in grouped.items():
        ranked = sorted(
            members,
            key=lambda row: (
                -float(row["forecast_priority_score"]),
                str(row.get("event_id") or ""),
            ),
        )
        representative = ranked[0]
        event_ids = sorted(
            {
                str(row["event_id"])
                for row in members
                if _text(row.get("event_id"))
            }
        )
        member_coordinates = [
            coordinates[event_id]
            for event_id in event_ids
            if event_id in coordinates
        ]
        latitude = (
            sum(point[0] for point in member_coordinates) / len(member_coordinates)
            if member_coordinates
            else None
        )
        longitude = (
            sum(point[1] for point in member_coordinates) / len(member_coordinates)
            if member_coordinates
            else None
        )
        override = override_index.get(link_id, {})
        service_minutes = override.get("service_minutes") or default_service
        handoff_actions: list[dict[str, Any]] = []
        handoff_levels: dict[str, str] = {}
        for handoff_type in ("police", "fire"):
            level = str(
                _override_or_default(
                    override,
                    governance_defaults,
                    f"{handoff_type}_handoff_level",
                )
                or "none"
            )
            channel_id = _override_or_default(
                override,
                governance_defaults,
                f"{handoff_type}_handoff_channel_id",
            )
            handoff_levels[handoff_type] = level
            if level != "none":
                channel = channel_index.get(str(channel_id), {})
                handoff_actions.append(
                    {
                        "handoff_type": handoff_type,
                        "level": level,
                        "channel_id": channel_id,
                        "target_agency_id": channel.get("target_agency_id"),
                        "status": "pending",
                    }
                )
        if "transfer" in handoff_levels.values():
            response_mode = "external_handoff"
        elif "coordinate" in handoff_levels.values():
            response_mode = "joint_response"
        else:
            response_mode = "road_team_dispatch"
        approval_required = bool(
            _override_or_default(
                override,
                governance_defaults,
                "dispatch_approval_required",
            )
        )
        tasks.append(
            {
                "task_id": f"link:{link_id}:h{horizon_hours}",
                "link_id": link_id,
                "horizon_hours": horizon_hours,
                "road_name": _text(representative.get("road_name")),
                "priority_score": round(
                    float(representative["forecast_priority_score"]), 3
                ),
                "score_lower_bound": _number(
                    representative.get("forecast_score_lower_bound")
                ),
                "score_upper_bound": _number(
                    representative.get("forecast_score_upper_bound")
                ),
                "risk_level": _text(representative.get("risk_level")),
                "latitude": round(latitude, 7) if latitude is not None else None,
                "longitude": round(longitude, 7) if longitude is not None else None,
                "event_count": len(event_ids),
                "event_ids": event_ids,
                "source_ids": sorted(
                    {
                        str(row["source_id"])
                        for row in members
                        if _text(row.get("source_id"))
                    }
                ),
                "event_types": sorted(
                    {
                        str(row["event_type"])
                        for row in members
                        if _text(row.get("event_type"))
                    }
                ),
                "mandatory": link_id in mandatory_links,
                "excluded": link_id in excluded_links,
                "fixed_team_id": fixed_index.get(link_id),
                "service_minutes": round(float(service_minutes), 3),
                "required_skills": list(override.get("required_skills", [])),
                "required_equipment": list(
                    override.get("required_equipment", [])
                ),
                "managing_agency_id": _override_or_default(
                    override, governance_defaults, "managing_agency_id"
                ),
                "road_jurisdiction": _override_or_default(
                    override, governance_defaults, "road_jurisdiction"
                ),
                "jurisdiction_basis": _override_or_default(
                    override, governance_defaults, "jurisdiction_basis"
                ),
                "dispatch_approval_required": approval_required,
                "dispatch_approver_id": _override_or_default(
                    override, governance_defaults, "dispatch_approver_id"
                ),
                "dispatch_approval_status": (
                    "pending" if approval_required else "not_required"
                ),
                "response_mode": response_mode,
                "road_team_dispatch_eligible": response_mode != "external_handoff",
                "handoff_actions": handoff_actions,
            }
        )

    tasks.sort(key=lambda row: (-row["priority_score"], row["link_id"]))
    report = {
        "horizon_hours": horizon_hours,
        "horizon_forecast_row_count": horizon_row_count,
        "eligible_forecast_row_count": len(eligible),
        "field_task_count": len(tasks),
        "collapsed_duplicate_event_count": len(eligible) - len(tasks),
        "missing_coordinate_task_count": sum(
            task["latitude"] is None or task["longitude"] is None for task in tasks
        ),
        "mandatory_links_missing_from_tasks": sorted(
            mandatory_links - set(grouped)
        ),
        "fixed_links_missing_from_tasks": sorted(set(fixed_index) - set(grouped)),
        "institution_scoped_task_count": sum(
            bool(task.get("managing_agency_id") and task.get("road_jurisdiction"))
            for task in tasks
        ),
        "approval_required_task_count": sum(
            bool(task.get("dispatch_approval_required")) for task in tasks
        ),
        "handoff_action_count": sum(
            len(task.get("handoff_actions", [])) for task in tasks
        ),
        "external_handoff_task_count": sum(
            task.get("response_mode") == "external_handoff" for task in tasks
        ),
    }
    return tasks, report


def _initial_team_states(resource_plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    planning_start = _datetime(resource_plan["planning"]["planning_start_at"])
    states: dict[str, dict[str, Any]] = {}
    for team in resource_plan["teams"]:
        team_id = str(team["team_id"])
        shift_start = _datetime(team["shift_start_at"])
        shift_end = _datetime(team["shift_end_at"])
        operational_start = max(planning_start, shift_start)
        states[team_id] = {
            "team": team,
            "latitude": float(team["start_latitude"]),
            "longitude": float(team["start_longitude"]),
            "available_minutes": (shift_end - operational_start).total_seconds()
            / 60,
            "elapsed_minutes": 0.0,
            "travel_minutes": 0.0,
            "service_minutes": 0.0,
            "distance_km": 0.0,
            "assignment_count": 0,
        }
    return states


def _feasibility(
    state: Mapping[str, Any],
    task: Mapping[str, Any],
    *,
    speed_kph: float,
    max_tasks: int,
) -> dict[str, Any]:
    if task["latitude"] is None or task["longitude"] is None:
        return {"feasible": False, "reason": "task_coordinates_missing"}
    team = state["team"]
    missing_skills = sorted(set(task["required_skills"]) - set(team["skills"]))
    missing_equipment = sorted(
        set(task["required_equipment"]) - set(team["equipment"])
    )
    if missing_skills or missing_equipment:
        return {
            "feasible": False,
            "reason": "team_capability_missing",
            "missing_skills": missing_skills,
            "missing_equipment": missing_equipment,
        }
    institutional = institutional_eligibility(team, task)
    if not institutional["eligible"]:
        return {
            "feasible": False,
            "reason": "institutional_authority_mismatch",
            "institutional_reasons": institutional["reasons"],
        }
    if int(state["assignment_count"]) >= max_tasks:
        return {"feasible": False, "reason": "team_task_limit_reached"}
    distance = _haversine_km(
        float(state["latitude"]),
        float(state["longitude"]),
        float(task["latitude"]),
        float(task["longitude"]),
    )
    travel_minutes = distance / speed_kph * 60
    incremental = travel_minutes + float(task["service_minutes"])
    if float(state["elapsed_minutes"]) + incremental > float(
        state["available_minutes"]
    ) + 1e-9:
        return {
            "feasible": False,
            "reason": "insufficient_shift_time",
            "straight_line_distance_km": distance,
            "travel_minutes": travel_minutes,
            "incremental_minutes": incremental,
        }
    return {
        "feasible": True,
        "reason": None,
        "straight_line_distance_km": distance,
        "travel_minutes": travel_minutes,
        "incremental_minutes": incremental,
    }


def _assign(
    *,
    strategy: str,
    state: dict[str, Any],
    task: Mapping[str, Any],
    feasibility: Mapping[str, Any],
    fixed: bool,
    allocation_order: int,
) -> dict[str, Any]:
    distance = float(feasibility["straight_line_distance_km"])
    travel_minutes = float(feasibility["travel_minutes"])
    service_minutes = float(task["service_minutes"])
    state["elapsed_minutes"] += travel_minutes + service_minutes
    state["travel_minutes"] += travel_minutes
    state["service_minutes"] += service_minutes
    state["distance_km"] += distance
    state["assignment_count"] += 1
    state["latitude"] = float(task["latitude"])
    state["longitude"] = float(task["longitude"])
    return {
        "team_id": state["team"]["team_id"],
        "vehicle_id": state["team"]["vehicle_id"],
        "allocation_order": allocation_order,
        "sequence": state["assignment_count"],
        "task_id": task["task_id"],
        "link_id": task["link_id"],
        "road_name": task["road_name"],
        "priority_score": task["priority_score"],
        "event_count": task["event_count"],
        "event_ids": task["event_ids"],
        "mandatory": task["mandatory"],
        "fixed_assignment": fixed,
        "straight_line_distance_km": round(distance, 3),
        "estimated_travel_minutes": round(travel_minutes, 3),
        "service_minutes": round(service_minutes, 3),
        "cumulative_minutes": round(state["elapsed_minutes"], 3),
        "task_latitude": task["latitude"],
        "task_longitude": task["longitude"],
        "managing_agency_id": task.get("managing_agency_id"),
        "road_jurisdiction": task.get("road_jurisdiction"),
        "jurisdiction_basis": task.get("jurisdiction_basis"),
        "dispatch_approval_required": task.get("dispatch_approval_required"),
        "dispatch_approver_id": task.get("dispatch_approver_id"),
        "dispatch_approval_status": task.get("dispatch_approval_status"),
        "response_mode": task.get("response_mode"),
        "handoff_actions": list(task.get("handoff_actions", [])),
        "selection_reason": (
            "operator_fixed_assignment"
            if fixed
            else (
                "highest_priority_remaining_then_nearest_feasible_team"
                if strategy == "risk_first"
                else "nearest_feasible_team_task_pair"
            )
        ),
    }


def _unassigned_reason(
    task: Mapping[str, Any],
    states: Mapping[str, Mapping[str, Any]],
    *,
    speed_kph: float,
    max_tasks: int,
) -> tuple[str, dict[str, int]]:
    reasons = Counter(
        _feasibility(
            state,
            task,
            speed_kph=speed_kph,
            max_tasks=max_tasks,
        )["reason"]
        for state in states.values()
    )
    if task["latitude"] is None or task["longitude"] is None:
        reason = "task_coordinates_missing"
    elif reasons.get("team_capability_missing") == len(states):
        reason = "no_capable_team"
    elif reasons.get("institutional_authority_mismatch") == len(states):
        reason = "no_team_with_institutional_authority"
    elif reasons.get("team_task_limit_reached") == len(states):
        reason = "all_teams_at_task_limit"
    else:
        reason = "no_feasible_team_within_shift"
    return reason, dict(sorted(reasons.items()))


def _constraint_violations(
    assignments: list[Mapping[str, Any]],
    unassigned: list[Mapping[str, Any]],
    tasks: list[Mapping[str, Any]],
    task_report: Mapping[str, Any],
    resource_plan: Mapping[str, Any],
    states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    assigned_links = [str(row["link_id"]) for row in assignments]
    duplicates = sorted(
        link_id for link_id, count in Counter(assigned_links).items() if count > 1
    )
    if duplicates:
        violations.append(
            {"code": "duplicate_link_assignment", "link_ids": duplicates}
        )
    excluded = set(resource_plan["constraints"]["excluded_link_ids"])
    wrongly_assigned = sorted(set(assigned_links) & excluded)
    if wrongly_assigned:
        violations.append(
            {"code": "excluded_link_assigned", "link_ids": wrongly_assigned}
        )
    for missing in task_report["mandatory_links_missing_from_tasks"]:
        violations.append(
            {"code": "mandatory_link_missing_from_tasks", "link_id": missing}
        )
    for missing in task_report["fixed_links_missing_from_tasks"]:
        violations.append(
            {"code": "fixed_link_missing_from_tasks", "link_id": missing}
        )
    for row in unassigned:
        if row.get("mandatory"):
            violations.append(
                {
                    "code": "mandatory_task_unassigned",
                    "link_id": row["link_id"],
                    "reason": row["reason"],
                }
            )
        if row.get("fixed_team_id"):
            violations.append(
                {
                    "code": "fixed_assignment_unfulfilled",
                    "link_id": row["link_id"],
                    "team_id": row["fixed_team_id"],
                    "reason": row["reason"],
                }
            )
    max_tasks = int(resource_plan["planning"]["max_tasks_per_team"])
    for team_id, state in states.items():
        if int(state["assignment_count"]) > max_tasks:
            violations.append(
                {"code": "team_task_limit_exceeded", "team_id": team_id}
            )
        if float(state["elapsed_minutes"]) > float(state["available_minutes"]) + 1e-9:
            violations.append(
                {"code": "team_shift_exceeded", "team_id": team_id}
            )
    task_index = {str(task["link_id"]): task for task in tasks}
    team_index = {
        str(team["team_id"]): team for team in resource_plan["teams"]
    }
    for row in assignments:
        task = task_index[str(row["link_id"])]
        team = team_index[str(row["team_id"])]
        if not set(task["required_skills"]).issubset(team["skills"]):
            violations.append(
                {"code": "required_skill_missing", "link_id": row["link_id"]}
            )
        if not set(task["required_equipment"]).issubset(team["equipment"]):
            violations.append(
                {
                    "code": "required_equipment_missing",
                    "link_id": row["link_id"],
                }
            )
        institutional = institutional_eligibility(team, task)
        if not institutional["eligible"]:
            violations.append(
                {
                    "code": "institutional_authority_violation",
                    "link_id": row["link_id"],
                    "team_id": row["team_id"],
                    "reasons": institutional["reasons"],
                }
            )
    return violations


def _plan_metrics(
    tasks: list[Mapping[str, Any]],
    assignments: list[Mapping[str, Any]],
    unassigned: list[Mapping[str, Any]],
    states: Mapping[str, Mapping[str, Any]],
    violations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    candidates = [
        task
        for task in tasks
        if not task["excluded"] and task.get("road_team_dispatch_eligible", True)
    ]
    total_priority = sum(float(task["priority_score"]) for task in candidates)
    assigned_priority = sum(float(row["priority_score"]) for row in assignments)
    workloads = [int(state["assignment_count"]) for state in states.values()]
    high_unassigned = [
        row
        for row in unassigned
        if not row.get("excluded")
        and row.get("reason") != "external_handoff_required"
        and float(row.get("priority_score") or 0) >= HIGH_PRIORITY_SCORE
    ]
    return {
        "candidate_task_count": len(candidates),
        "assigned_task_count": len(assignments),
        "unassigned_candidate_task_count": sum(
            not row.get("excluded")
            and row.get("reason") != "external_handoff_required"
            for row in unassigned
        ),
        "excluded_task_count": sum(task["excluded"] for task in tasks),
        "high_priority_unassigned_count": len(high_unassigned),
        "high_priority_unassigned_link_ids": sorted(
            str(row["link_id"]) for row in high_unassigned
        ),
        "assigned_priority_sum": round(assigned_priority, 3),
        "candidate_priority_sum": round(total_priority, 3),
        "risk_weighted_coverage_ratio": (
            round(assigned_priority / total_priority, 6)
            if total_priority
            else None
        ),
        "total_straight_line_distance_km": round(
            sum(float(row["straight_line_distance_km"]) for row in assignments),
            3,
        ),
        "total_estimated_travel_minutes": round(
            sum(float(row["estimated_travel_minutes"]) for row in assignments),
            3,
        ),
        "total_service_minutes": round(
            sum(float(row["service_minutes"]) for row in assignments), 3
        ),
        "maximum_team_elapsed_minutes": round(
            max((float(state["elapsed_minutes"]) for state in states.values()), default=0),
            3,
        ),
        "workload_task_counts": {
            team_id: int(state["assignment_count"])
            for team_id, state in sorted(states.items())
        },
        "workload_count_range": max(workloads) - min(workloads) if workloads else 0,
        "workload_count_variance": round(pvariance(workloads), 6)
        if workloads
        else None,
        "constraint_violation_count": len(violations),
    }


def _build_plan(
    strategy: str,
    tasks: list[dict[str, Any]],
    task_report: Mapping[str, Any],
    resource_plan: Mapping[str, Any],
) -> dict[str, Any]:
    states = _initial_team_states(resource_plan)
    speed = float(resource_plan["planning"]["baseline_speed_kph"])
    max_tasks = int(resource_plan["planning"]["max_tasks_per_team"])
    remaining = {
        str(task["link_id"]): task
        for task in tasks
        if not task["excluded"] and task.get("road_team_dispatch_eligible", True)
    }
    assignments: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = [
        {
            "task_id": task["task_id"],
            "link_id": task["link_id"],
            "priority_score": task["priority_score"],
            "mandatory": task["mandatory"],
            "excluded": True,
            "fixed_team_id": task["fixed_team_id"],
            "reason": "excluded_by_operator",
            "team_feasibility_reasons": {},
        }
        for task in tasks
        if task["excluded"]
    ]
    unassigned.extend(
        {
            "task_id": task["task_id"],
            "link_id": task["link_id"],
            "priority_score": task["priority_score"],
            "mandatory": task["mandatory"],
            "excluded": False,
            "fixed_team_id": task["fixed_team_id"],
            "reason": "external_handoff_required",
            "team_feasibility_reasons": {},
            "handoff_actions": list(task.get("handoff_actions", [])),
        }
        for task in tasks
        if not task["excluded"]
        and not task.get("road_team_dispatch_eligible", True)
    )

    for fixed in resource_plan["constraints"]["fixed_assignments"]:
        link_id = str(fixed["link_id"])
        task = remaining.pop(link_id, None)
        if task is None:
            continue
        team_id = str(fixed["team_id"])
        state = states[team_id]
        feasibility = _feasibility(
            state, task, speed_kph=speed, max_tasks=max_tasks
        )
        if feasibility["feasible"]:
            assignments.append(
                _assign(
                    strategy=strategy,
                    state=state,
                    task=task,
                    feasibility=feasibility,
                    fixed=True,
                    allocation_order=len(assignments) + 1,
                )
            )
        else:
            unassigned.append(
                {
                    "task_id": task["task_id"],
                    "link_id": link_id,
                    "priority_score": task["priority_score"],
                    "mandatory": task["mandatory"],
                    "excluded": False,
                    "fixed_team_id": team_id,
                    "reason": "fixed_team_infeasible",
                    "team_feasibility_reasons": {
                        team_id: str(feasibility["reason"])
                    },
                }
            )

    while remaining:
        mandatory_remaining = [
            task for task in remaining.values() if task["mandatory"]
        ]
        pool = mandatory_remaining or list(remaining.values())
        selected: tuple[dict[str, Any], str, dict[str, Any]] | None = None
        if strategy == "risk_first":
            task = sorted(
                pool, key=lambda row: (-row["priority_score"], row["link_id"])
            )[0]
            candidates = []
            for team_id, state in states.items():
                feasibility = _feasibility(
                    state, task, speed_kph=speed, max_tasks=max_tasks
                )
                if feasibility["feasible"]:
                    candidates.append(
                        (
                            float(feasibility["straight_line_distance_km"]),
                            int(state["assignment_count"]),
                            float(state["elapsed_minutes"]),
                            team_id,
                            feasibility,
                        )
                    )
            if candidates:
                _, _, _, team_id, feasibility = min(candidates)
                selected = (task, team_id, feasibility)
            else:
                remaining.pop(str(task["link_id"]))
                reason, reason_counts = _unassigned_reason(
                    task, states, speed_kph=speed, max_tasks=max_tasks
                )
                unassigned.append(
                    {
                        "task_id": task["task_id"],
                        "link_id": task["link_id"],
                        "priority_score": task["priority_score"],
                        "mandatory": task["mandatory"],
                        "excluded": False,
                        "fixed_team_id": task["fixed_team_id"],
                        "reason": reason,
                        "team_feasibility_reasons": reason_counts,
                    }
                )
                continue
        else:
            candidates = []
            for task in pool:
                for team_id, state in states.items():
                    feasibility = _feasibility(
                        state, task, speed_kph=speed, max_tasks=max_tasks
                    )
                    if feasibility["feasible"]:
                        candidates.append(
                            (
                                float(feasibility["straight_line_distance_km"]),
                                -float(task["priority_score"]),
                                str(task["link_id"]),
                                team_id,
                                task,
                                feasibility,
                            )
                        )
            if candidates:
                _, _, _, team_id, task, feasibility = min(candidates)
                selected = (task, team_id, feasibility)
            else:
                for task in sorted(pool, key=lambda row: row["link_id"]):
                    remaining.pop(str(task["link_id"]))
                    reason, reason_counts = _unassigned_reason(
                        task, states, speed_kph=speed, max_tasks=max_tasks
                    )
                    unassigned.append(
                        {
                            "task_id": task["task_id"],
                            "link_id": task["link_id"],
                            "priority_score": task["priority_score"],
                            "mandatory": task["mandatory"],
                            "excluded": False,
                            "fixed_team_id": task["fixed_team_id"],
                            "reason": reason,
                            "team_feasibility_reasons": reason_counts,
                        }
                    )
                continue

        if selected:
            task, team_id, feasibility = selected
            remaining.pop(str(task["link_id"]))
            assignments.append(
                _assign(
                    strategy=strategy,
                    state=states[team_id],
                    task=task,
                    feasibility=feasibility,
                    fixed=False,
                    allocation_order=len(assignments) + 1,
                )
            )

    assignments.sort(key=lambda row: (str(row["team_id"]), int(row["sequence"])))
    unassigned.sort(key=lambda row: (-float(row["priority_score"]), row["link_id"]))
    violations = _constraint_violations(
        assignments,
        unassigned,
        tasks,
        task_report,
        resource_plan,
        states,
    )
    return {
        "strategy": strategy,
        "strategy_semantics": (
            "mandatory_then_descending_risk_with_nearest_feasible_team"
            if strategy == "risk_first"
            else "mandatory_then_globally_nearest_feasible_team_task_pair"
        ),
        "assignments": assignments,
        "unassigned_tasks": unassigned,
        "team_summaries": [
            {
                "team_id": team_id,
                "vehicle_id": state["team"]["vehicle_id"],
                "assignment_count": state["assignment_count"],
                "available_minutes": round(state["available_minutes"], 3),
                "elapsed_minutes": round(state["elapsed_minutes"], 3),
                "travel_minutes": round(state["travel_minutes"], 3),
                "service_minutes": round(state["service_minutes"], 3),
                "straight_line_distance_km": round(state["distance_km"], 3),
            }
            for team_id, state in sorted(states.items())
        ],
        "constraint_violations": violations,
        "metrics": _plan_metrics(
            tasks, assignments, unassigned, states, violations
        ),
    }


def build_allocation_baselines(
    resource_payload: Mapping[str, Any],
    forecast_rows: Iterable[Mapping[str, Any]],
    integrated_event_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate inputs and build two reproducible allocation baselines."""

    resource_plan, resource_report = validate_resource_plan(resource_payload)
    if resource_report["status"] == "fail":
        result = {
            "schema_version": 1,
            "allocation_version": ALLOCATION_VERSION,
            "scenario_id": resource_plan.get("scenario_id"),
            "status": "fail",
            "failure_reason": "resource_input_validation_failed",
            "plans": [],
        }
        return result, {
            "schema_version": 1,
            "status": "fail",
            "resource_validation": resource_report,
            "failed_checks": ["resource_input_validation"],
        }

    forecast_list = [dict(row) for row in forecast_rows]
    event_list = [dict(row) for row in integrated_event_rows]
    horizon = int(resource_plan["planning"]["horizon_hours"])
    tasks, task_report = build_field_tasks(
        forecast_list,
        event_list,
        horizon_hours=horizon,
        resource_plan=resource_plan,
    )
    plans = [
        _build_plan(strategy, tasks, task_report, resource_plan)
        for strategy in ("risk_first", "nearest")
    ]
    hard_codes = {
        "duplicate_link_assignment",
        "excluded_link_assigned",
        "team_task_limit_exceeded",
        "team_shift_exceeded",
        "required_skill_missing",
        "required_equipment_missing",
        "institutional_authority_violation",
    }
    hard_violations = [
        {"strategy": plan["strategy"], **violation}
        for plan in plans
        for violation in plan["constraint_violations"]
        if violation["code"] in hard_codes
    ]
    limitation_count = sum(
        sum(not row["excluded"] for row in plan["unassigned_tasks"])
        + len(plan["constraint_violations"])
        for plan in plans
    )
    status = (
        "fail"
        if hard_violations
        else ("pass_with_limitations" if limitation_count else "pass")
    )
    result = {
        "schema_version": 1,
        "allocation_version": ALLOCATION_VERSION,
        "scenario_id": resource_plan["scenario_id"],
        "status": status,
        "planning": resource_plan["planning"],
        "baseline_limitations": [
            "straight_line_distance_is_not_route_distance_or_eta",
            "constant_speed_ignores_live_congestion_and_turn_restrictions",
            "greedy_baselines_do_not_claim_global_optimality",
        ],
        "field_tasks": tasks,
        "plans": plans,
        "comparison": {
            plan["strategy"]: plan["metrics"] for plan in plans
        },
    }
    report = {
        "schema_version": 1,
        "status": status,
        "resource_validation": resource_report,
        "task_build": task_report,
        "plan_checks": {
            plan["strategy"]: {
                "constraint_violation_count": len(
                    plan["constraint_violations"]
                ),
                "unassigned_task_count": len(plan["unassigned_tasks"]),
            }
            for plan in plans
        },
        "hard_violations": hard_violations,
        "failed_checks": ["allocation_constraint_integrity"]
        if hard_violations
        else [],
    }
    return result, report
