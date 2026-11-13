"""Build safe partial replans after a closure or heavy-rain scenario.

완료·고정·비영향 업무를 보존하고 영향팀의 남은 업무만 재계획합니다.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta
from statistics import pvariance
from typing import Any, Iterable, Mapping

from roadops.allocation_optimizer import build_constraint_allocation
from roadops.resources import validate_resource_plan
from roadops.spatial import normalize_link_id


REPLANNING_VERSION = "roadops-partial-replanning-v0.1"
HIGH_PRIORITY_SCORE = 50.0


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _route_fingerprint(assignment: Mapping[str, Any]) -> str:
    return _digest(
        {
            "route_link_ids": assignment.get("route_link_ids", []),
            "travel_minutes": assignment.get("travel_minutes"),
            "distance_km": assignment.get("distance_km"),
        }
    )


def _trace(
    sequence: int,
    tool_name: str,
    status: str,
    *,
    output_summary: Mapping[str, Any],
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "tool_name": tool_name,
        "status": status,
        "output_summary": dict(output_summary),
        "limitations": list(limitations),
    }


def apply_heavy_rain_scenario(
    field_tasks: Iterable[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
    *,
    affected_link_ids: Iterable[str],
    priority_delta: float = 15.0,
    service_minutes_delta: float = 10.0,
    travel_time_multiplier: float = 1.25,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Create an explicit heavy-rain what-if without claiming an observation."""

    if priority_delta < 0 or service_minutes_delta < 0:
        raise ValueError("heavy-rain deltas must be non-negative")
    if travel_time_multiplier < 1:
        raise ValueError("travel_time_multiplier must be at least 1")
    affected = {
        link_id
        for value in affected_link_ids
        if (link_id := normalize_link_id(value)) is not None
    }
    if not affected:
        raise ValueError("at least one valid affected link is required")

    tasks = [copy.deepcopy(dict(task)) for task in field_tasks]
    task_link_by_id = {
        str(task["task_id"]): str(task["link_id"]) for task in tasks
    }
    changed_task_ids: list[str] = []
    for task in tasks:
        if str(task["link_id"]) not in affected:
            continue
        task["priority_score_before_scenario"] = task["priority_score"]
        task["priority_score"] = round(
            min(100.0, float(task["priority_score"]) + priority_delta), 3
        )
        task["service_minutes_before_scenario"] = task["service_minutes"]
        task["service_minutes"] = round(
            float(task["service_minutes"]) + service_minutes_delta, 3
        )
        task["scenario_flags"] = sorted(
            set(task.get("scenario_flags", [])) | {"heavy_rain_what_if"}
        )
        changed_task_ids.append(str(task["task_id"]))

    matrix = copy.deepcopy(dict(travel_matrix))
    changed_route_count = 0
    for route in matrix.get("routes", []):
        route_links = {str(value) for value in route.get("route_link_ids", [])}
        origin_link = task_link_by_id.get(str(route.get("origin_id")))
        destination_link = task_link_by_id.get(
            str(route.get("destination_task_id"))
        )
        exposed = bool(route_links & affected) or origin_link in affected or (
            destination_link in affected
        )
        if not exposed or route.get("travel_time_minutes") is None:
            continue
        route["travel_time_minutes_before_scenario"] = route[
            "travel_time_minutes"
        ]
        route["travel_time_minutes"] = round(
            float(route["travel_time_minutes"]) * travel_time_multiplier, 3
        )
        if route.get("network_travel_minutes") is not None:
            route["network_travel_minutes"] = round(
                float(route["network_travel_minutes"])
                * travel_time_multiplier,
                3,
            )
        route["source_mode"] = "heavy_rain_what_if_adjustment"
        route["scenario_flags"] = ["heavy_rain_what_if"]
        changed_route_count += 1
    matrix["scenario"] = {
        "scenario_type": "heavy_rain",
        "semantics": "what_if_not_observed_weather",
        "affected_link_ids": sorted(affected),
        "travel_time_multiplier": travel_time_multiplier,
    }
    metadata = {
        "scenario_type": "heavy_rain",
        "reason_code": "heavy_rain_what_if_injected",
        "semantics": "what_if_not_observed_weather",
        "affected_link_ids": sorted(affected),
        "priority_delta": priority_delta,
        "service_minutes_delta": service_minutes_delta,
        "travel_time_multiplier": travel_time_multiplier,
        "changed_task_ids": sorted(changed_task_ids),
        "changed_route_count": changed_route_count,
    }
    return tasks, matrix, metadata


def _base_plan(
    base_allocation: Mapping[str, Any], alternative_id: str
) -> dict[str, Any] | None:
    return next(
        (
            copy.deepcopy(dict(plan))
            for plan in base_allocation.get("alternatives", [])
            if plan.get("alternative_id") == alternative_id
        ),
        None,
    )


def _completed_prefix_errors(
    assignments: list[dict[str, Any]], completed_task_ids: set[str]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    known = {str(row["task_id"]) for row in assignments}
    for task_id in sorted(completed_task_ids - known):
        errors.append({"code": "completed_task_not_in_base_plan", "task_id": task_id})
    by_team: dict[str, list[dict[str, Any]]] = {}
    for row in assignments:
        by_team.setdefault(str(row["team_id"]), []).append(row)
    for team_id, rows in by_team.items():
        ordered = sorted(rows, key=lambda row: int(row["sequence"]))
        completed_sequences = [
            int(row["sequence"])
            for row in ordered
            if str(row["task_id"]) in completed_task_ids
        ]
        if completed_sequences and completed_sequences != list(
            range(1, max(completed_sequences) + 1)
        ):
            errors.append(
                {
                    "code": "completed_tasks_must_be_team_route_prefix",
                    "team_id": team_id,
                    "completed_sequences": completed_sequences,
                }
            )
    return errors


def _affected_teams(
    assignments: list[dict[str, Any]],
    completed_task_ids: set[str],
    scenario: Mapping[str, Any],
) -> tuple[list[str], dict[str, list[str]]]:
    affected_links = set(scenario.get("affected_link_ids", []))
    reasons: dict[str, list[str]] = {}
    for row in assignments:
        if str(row["task_id"]) in completed_task_ids:
            continue
        route_hit = bool(set(row.get("route_link_ids", [])) & affected_links)
        task_hit = str(row.get("link_id")) in affected_links
        if scenario.get("scenario_type") == "road_closure" and route_hit:
            closed_link = sorted(
                set(row.get("route_link_ids", [])) & affected_links
            )[0]
            reasons.setdefault(str(row["team_id"]), []).append(
                f"route_uses_closed_link:{closed_link}"
            )
        if scenario.get("scenario_type") == "heavy_rain" and (
            route_hit or task_hit
        ):
            reason = (
                f"assigned_task_in_heavy_rain_area:{row['link_id']}"
                if task_hit
                else "route_crosses_heavy_rain_area"
            )
            reasons.setdefault(str(row["team_id"]), []).append(reason)
    return sorted(reasons), {
        team_id: sorted(set(values)) for team_id, values in reasons.items()
    }


def _failure(
    scenario: Mapping[str, Any],
    trace: list[dict[str, Any]],
    reason: str,
    details: Iterable[Any] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = {
        "schema_version": 1,
        "replanning_version": REPLANNING_VERSION,
        "status": "fail",
        "scenario": dict(scenario),
        "failure_reason": reason,
        "failure_details": list(details),
        "tool_trace": trace,
        "manual_approval_required": True,
    }
    report = {
        "schema_version": 1,
        "replanning_version": REPLANNING_VERSION,
        "status": "fail",
        "failed_checks": [reason],
        "completed_tool_count": len(trace),
        "failed_tool": trace[-1]["tool_name"] if trace else None,
    }
    return result, report


def _subproblem(
    resource_plan: Mapping[str, Any],
    tasks: list[dict[str, Any]],
    scenario_matrix: Mapping[str, Any],
    base_plan: Mapping[str, Any],
    *,
    affected_team_ids: list[str],
    completed_task_ids: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, float]]:
    assignments = list(base_plan["assignments"])
    affected_set = set(affected_team_ids)
    remaining_task_ids = {
        str(row["task_id"])
        for row in assignments
        if str(row["team_id"]) in affected_set
        and str(row["task_id"]) not in completed_task_ids
    }
    remaining_tasks = [
        copy.deepcopy(task)
        for task in tasks
        if str(task["task_id"]) in remaining_task_ids
    ]
    remaining_links = {str(task["link_id"]) for task in remaining_tasks}
    team_index = {
        str(team["team_id"]): copy.deepcopy(team)
        for team in resource_plan["teams"]
    }
    vehicle_index = {
        str(vehicle["vehicle_id"]): copy.deepcopy(vehicle)
        for vehicle in resource_plan["vehicles"]
    }
    base_summary = {
        str(row["team_id"]): row for row in base_plan["team_summaries"]
    }
    consumed_by_team: dict[str, float] = {}
    last_completed_by_team: dict[str, str] = {}
    completed_count_by_team: dict[str, int] = {}
    for team_id in affected_team_ids:
        completed = sorted(
            (
                row
                for row in assignments
                if str(row["team_id"]) == team_id
                and str(row["task_id"]) in completed_task_ids
            ),
            key=lambda row: int(row["sequence"]),
        )
        consumed_by_team[team_id] = (
            float(completed[-1]["cumulative_minutes"]) if completed else 0.0
        )
        completed_count_by_team[team_id] = len(completed)
        if completed:
            last_completed_by_team[team_id] = str(completed[-1]["task_id"])

    planning_start = datetime.fromisoformat(
        str(resource_plan["planning"]["planning_start_at"])
    )
    teams = []
    for team_id in affected_team_ids:
        team = team_index[team_id]
        available = float(base_summary[team_id]["available_minutes"])
        remaining_available = available - consumed_by_team[team_id]
        team["shift_end_at"] = (
            planning_start + timedelta(minutes=remaining_available)
        ).isoformat()
        teams.append(team)
    vehicles = [vehicle_index[str(team["vehicle_id"])] for team in teams]
    remaining_caps = [
        int(resource_plan["planning"]["max_tasks_per_team"])
        - completed_count_by_team[team_id]
        for team_id in affected_team_ids
    ]
    planning = dict(resource_plan["planning"])
    planning["max_tasks_per_team"] = min(remaining_caps)
    subresources = {
        "schema_version": 1,
        "scenario_id": f"{resource_plan['scenario_id']}:partial-replan",
        "planning": planning,
        "vehicles": vehicles,
        "teams": teams,
        "constraints": {
            "mandatory_link_ids": [
                link_id
                for link_id in resource_plan["constraints"]["mandatory_link_ids"]
                if link_id in remaining_links
            ],
            "excluded_link_ids": [],
            "fixed_assignments": [
                dict(row)
                for row in resource_plan["constraints"]["fixed_assignments"]
                if str(row["link_id"]) in remaining_links
            ],
            "task_overrides": [
                dict(row)
                for row in resource_plan["constraints"]["task_overrides"]
                if str(row["link_id"]) in remaining_links
            ],
        },
    }

    route_index = {
        (str(row["origin_id"]), str(row["destination_task_id"])): row
        for row in scenario_matrix.get("routes", [])
    }
    subroutes: list[dict[str, Any]] = []
    for team_id in affected_team_ids:
        source_origin = last_completed_by_team.get(team_id, team_id)
        for task_id in sorted(remaining_task_ids):
            source = route_index.get((source_origin, task_id))
            if source is None:
                continue
            row = copy.deepcopy(dict(source))
            row["origin_id"] = team_id
            row["origin_type"] = (
                "team_position_after_completed_task"
                if source_origin != team_id
                else "team_start"
            )
            row["route_id"] = _digest(
                {
                    "team_id": team_id,
                    "source_origin": source_origin,
                    "destination": task_id,
                    "scenario": scenario_matrix.get("scenario"),
                    "route_links": row.get("route_link_ids", []),
                }
            )
            subroutes.append(row)
    for origin_id in sorted(remaining_task_ids):
        for destination_id in sorted(remaining_task_ids):
            source = route_index.get((origin_id, destination_id))
            if source is not None:
                subroutes.append(copy.deepcopy(dict(source)))
    submatrix = {
        "schema_version": 1,
        "scenario_id": subresources["scenario_id"],
        "status": (
            "pass_with_limitations"
            if any(row.get("travel_time_minutes") is None for row in subroutes)
            else "pass"
        ),
        "route_semantics": scenario_matrix.get("route_semantics"),
        "closed_link_ids": list(scenario_matrix.get("closed_link_ids", [])),
        "routes": subroutes,
    }
    return subresources, remaining_tasks, submatrix, consumed_by_team


def _combine_plan(
    resource_plan: Mapping[str, Any],
    all_tasks: list[dict[str, Any]],
    base_plan: Mapping[str, Any],
    subplan: Mapping[str, Any],
    *,
    affected_team_ids: list[str],
    completed_task_ids: set[str],
    consumed_by_team: Mapping[str, float],
) -> dict[str, Any]:
    affected = set(affected_team_ids)
    assignments: list[dict[str, Any]] = []
    base_assignments = list(base_plan["assignments"])
    for row in base_assignments:
        team_id = str(row["team_id"])
        task_id = str(row["task_id"])
        if team_id not in affected or task_id in completed_task_ids:
            preserved = copy.deepcopy(dict(row))
            preserved["replan_status"] = (
                "completed_preserved"
                if task_id in completed_task_ids
                else "unaffected_preserved"
            )
            assignments.append(preserved)

    completed_count = {
        team_id: sum(
            str(row["team_id"]) == team_id
            and str(row["task_id"]) in completed_task_ids
            for row in base_assignments
        )
        for team_id in affected_team_ids
    }
    for row in subplan["assignments"]:
        team_id = str(row["team_id"])
        replanned = copy.deepcopy(dict(row))
        replanned["sequence"] = int(row["sequence"]) + completed_count[team_id]
        replanned["cumulative_minutes"] = round(
            float(row["cumulative_minutes"]) + consumed_by_team[team_id], 3
        )
        replanned["replan_status"] = "replanned"
        assignments.append(replanned)

    team_order = {
        str(team["team_id"]): index
        for index, team in enumerate(resource_plan["teams"])
    }
    assignments.sort(
        key=lambda row: (team_order[str(row["team_id"])], int(row["sequence"]))
    )
    base_summary = {
        str(row["team_id"]): copy.deepcopy(dict(row))
        for row in base_plan["team_summaries"]
    }
    subsummary = {
        str(row["team_id"]): row for row in subplan["team_summaries"]
    }
    team_summaries: list[dict[str, Any]] = []
    for team in resource_plan["teams"]:
        team_id = str(team["team_id"])
        if team_id not in affected:
            summary = base_summary[team_id]
            summary["replan_status"] = "unaffected_preserved"
            team_summaries.append(summary)
            continue
        completed_rows = [
            row
            for row in base_assignments
            if str(row["team_id"]) == team_id
            and str(row["task_id"]) in completed_task_ids
        ]
        sub = subsummary[team_id]
        travel = sum(float(row["travel_minutes"]) for row in completed_rows) + float(
            sub["travel_minutes"]
        )
        service = sum(float(row["service_minutes"]) for row in completed_rows) + float(
            sub["service_minutes"]
        )
        elapsed = consumed_by_team[team_id] + float(sub["elapsed_minutes"])
        available = float(base_summary[team_id]["available_minutes"])
        team_rows = [
            row for row in assignments if str(row["team_id"]) == team_id
        ]
        team_summaries.append(
            {
                "team_id": team_id,
                "assignment_count": len(team_rows),
                "task_ids": [str(row["task_id"]) for row in team_rows],
                "travel_minutes": round(travel, 3),
                "service_minutes": round(service, 3),
                "elapsed_minutes": round(elapsed, 3),
                "available_minutes": round(available, 3),
                "remaining_minutes": round(available - elapsed, 3),
                "replan_status": "affected_replanned",
            }
        )

    unassigned = [copy.deepcopy(dict(row)) for row in subplan["unassigned_tasks"]]
    assigned_task_ids = {str(row["task_id"]) for row in assignments}
    task_index = {str(task["task_id"]): task for task in all_tasks}
    candidate_tasks = [task for task in all_tasks if not bool(task.get("excluded"))]
    candidate_priority = sum(float(task["priority_score"]) for task in candidate_tasks)
    assigned_priority = sum(
        float(task_index[task_id]["priority_score"])
        for task_id in assigned_task_ids
        if task_id in task_index
    )
    elapsed_values = [float(row["elapsed_minutes"]) for row in team_summaries]
    workload_counts = [int(row["assignment_count"]) for row in team_summaries]
    metrics = {
        "candidate_task_count": len(candidate_tasks),
        "assigned_task_count": len(assignments),
        "unassigned_task_count": len(unassigned),
        "assigned_priority_sum": round(assigned_priority, 3),
        "candidate_priority_sum": round(candidate_priority, 3),
        "risk_weighted_coverage_ratio": (
            round(assigned_priority / candidate_priority, 6)
            if candidate_priority
            else None
        ),
        "high_priority_unassigned_count": sum(
            float(row["priority_score"]) >= HIGH_PRIORITY_SCORE
            for row in unassigned
        ),
        "network_total_travel_minutes": round(
            sum(float(row["travel_minutes"]) for row in team_summaries), 3
        ),
        "total_service_minutes": round(
            sum(float(row["service_minutes"]) for row in team_summaries), 3
        ),
        "maximum_team_elapsed_minutes": round(max(elapsed_values), 3),
        "workload_task_counts": {
            str(row["team_id"]): int(row["assignment_count"])
            for row in team_summaries
        },
        "workload_count_range": max(workload_counts) - min(workload_counts),
        "workload_count_variance": round(pvariance(workload_counts), 6),
        "elapsed_minutes_variance": round(pvariance(elapsed_values), 6),
        "constraint_violation_count": 0,
    }
    return {
        "alternative_id": f"{base_plan['alternative_id']}:partial_replan",
        "base_alternative_id": base_plan["alternative_id"],
        "objective": "preserve_completed_fixed_and_unaffected_then_reoptimize_affected",
        "assignments": assignments,
        "team_summaries": team_summaries,
        "unassigned_tasks": unassigned,
        "constraint_violations": [],
        "metrics": metrics,
    }


def _combined_violations(
    resource_plan: Mapping[str, Any],
    base_plan: Mapping[str, Any],
    replanned: Mapping[str, Any],
    *,
    affected_team_ids: list[str],
    completed_task_ids: set[str],
    scenario: Mapping[str, Any],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    assignments = list(replanned["assignments"])
    task_ids = [str(row["task_id"]) for row in assignments]
    if len(task_ids) != len(set(task_ids)):
        violations.append({"code": "duplicate_task_assignment"})
    assigned_by_task = {str(row["task_id"]): row for row in assignments}
    base_by_task = {
        str(row["task_id"]): row for row in base_plan["assignments"]
    }
    for task_id in sorted(completed_task_ids):
        base = base_by_task.get(task_id)
        current = assigned_by_task.get(task_id)
        if base is None or current is None or (
            str(base["team_id"]), int(base["sequence"]), _route_fingerprint(base)
        ) != (
            str(current["team_id"]),
            int(current["sequence"]),
            _route_fingerprint(current),
        ):
            violations.append(
                {"code": "completed_task_not_preserved", "task_id": task_id}
            )
    affected = set(affected_team_ids)
    for team in resource_plan["teams"]:
        team_id = str(team["team_id"])
        if team_id in affected:
            continue
        base_rows = [
            row for row in base_plan["assignments"] if str(row["team_id"]) == team_id
        ]
        current_rows = [
            row for row in assignments if str(row["team_id"]) == team_id
        ]
        base_signature = [
            (str(row["task_id"]), int(row["sequence"]), _route_fingerprint(row))
            for row in base_rows
        ]
        current_signature = [
            (str(row["task_id"]), int(row["sequence"]), _route_fingerprint(row))
            for row in current_rows
        ]
        if base_signature != current_signature:
            violations.append(
                {"code": "unaffected_team_route_changed", "team_id": team_id}
            )
    fixed_by_link = {
        str(row["link_id"]): str(row["team_id"])
        for row in resource_plan["constraints"]["fixed_assignments"]
    }
    assigned_by_link = {str(row["link_id"]): row for row in assignments}
    for link_id, expected in fixed_by_link.items():
        row = assigned_by_link.get(link_id)
        if row is None or str(row["team_id"]) != expected:
            violations.append(
                {
                    "code": "fixed_assignment_changed",
                    "link_id": link_id,
                    "expected_team_id": expected,
                }
            )
    for link_id in resource_plan["constraints"]["mandatory_link_ids"]:
        if link_id not in assigned_by_link:
            violations.append(
                {"code": "mandatory_task_unassigned", "link_id": link_id}
            )
    for row in assignments:
        if str(row["task_id"]) in completed_task_ids:
            continue
        route_status = str(row.get("route_status") or "")
        if not (route_status.startswith("ok") or route_status == "cache_replay"):
            violations.append(
                {
                    "code": "unavailable_route_used_after_replan",
                    "task_id": row["task_id"],
                    "route_status": route_status,
                }
            )
    max_tasks = int(resource_plan["planning"]["max_tasks_per_team"])
    for summary in replanned["team_summaries"]:
        if int(summary["assignment_count"]) > max_tasks:
            violations.append(
                {"code": "team_task_limit_exceeded", "team_id": summary["team_id"]}
            )
        if float(summary["elapsed_minutes"]) > float(
            summary["available_minutes"]
        ) + 1e-9:
            violations.append(
                {"code": "team_shift_exceeded", "team_id": summary["team_id"]}
            )
    if scenario.get("scenario_type") == "road_closure":
        closed = set(scenario.get("affected_link_ids", []))
        for row in assignments:
            if str(row["task_id"]) in completed_task_ids:
                continue
            if set(row.get("route_link_ids", [])) & closed:
                violations.append(
                    {
                        "code": "closed_link_used_after_replan",
                        "task_id": row["task_id"],
                    }
                )
    return violations


def _plan_diff(
    base_plan: Mapping[str, Any],
    replanned: Mapping[str, Any],
    *,
    affected_team_ids: list[str],
    completed_task_ids: set[str],
    fixed_link_ids: set[str],
    team_reasons: Mapping[str, list[str]],
) -> dict[str, Any]:
    base_summaries = {
        str(row["team_id"]): row for row in base_plan["team_summaries"]
    }
    new_summaries = {
        str(row["team_id"]): row for row in replanned["team_summaries"]
    }
    base_assignments = list(base_plan["assignments"])
    new_assignments = list(replanned["assignments"])
    team_ids = list(base_summaries)
    team_changes = []
    for team_id in team_ids:
        before = sorted(
            (row for row in base_assignments if str(row["team_id"]) == team_id),
            key=lambda row: int(row["sequence"]),
        )
        after = sorted(
            (row for row in new_assignments if str(row["team_id"]) == team_id),
            key=lambda row: int(row["sequence"]),
        )
        before_tasks = [str(row["task_id"]) for row in before]
        after_tasks = [str(row["task_id"]) for row in after]
        route_changed = [
            str(old["task_id"])
            for old, new in zip(before, after)
            if str(old["task_id"]) == str(new["task_id"])
            and _route_fingerprint(old) != _route_fingerprint(new)
        ]
        team_changes.append(
            {
                "team_id": team_id,
                "change_status": (
                    "affected_replanned"
                    if team_id in affected_team_ids
                    else "unaffected_preserved"
                ),
                "before_task_ids": before_tasks,
                "after_task_ids": after_tasks,
                "task_sequence_changed": before_tasks != after_tasks,
                "route_changed_task_ids": route_changed,
                "travel_minutes_delta": round(
                    float(new_summaries[team_id]["travel_minutes"])
                    - float(base_summaries[team_id]["travel_minutes"]),
                    3,
                ),
                "elapsed_minutes_delta": round(
                    float(new_summaries[team_id]["elapsed_minutes"])
                    - float(base_summaries[team_id]["elapsed_minutes"]),
                    3,
                ),
                "change_reasons": list(team_reasons.get(team_id, [])),
            }
        )
    base_metrics = base_plan["metrics"]
    new_metrics = replanned["metrics"]
    metric_fields = (
        "risk_weighted_coverage_ratio",
        "network_total_travel_minutes",
        "maximum_team_elapsed_minutes",
        "unassigned_task_count",
        "constraint_violation_count",
    )
    metric_delta = {
        field: round(float(new_metrics[field]) - float(base_metrics[field]), 6)
        for field in metric_fields
    }
    fixed_preserved = sorted(
        str(row["task_id"])
        for row in new_assignments
        if str(row["link_id"]) in fixed_link_ids
    )
    return {
        "affected_team_ids": affected_team_ids,
        "unchanged_team_ids": [
            team_id for team_id in team_ids if team_id not in affected_team_ids
        ],
        "preserved_completed_task_ids": sorted(completed_task_ids),
        "preserved_fixed_task_ids": fixed_preserved,
        "before_metrics": {field: base_metrics[field] for field in metric_fields},
        "after_metrics": {field: new_metrics[field] for field in metric_fields},
        "metric_delta": metric_delta,
        "team_changes": team_changes,
    }


def _reason_messages(
    scenario: Mapping[str, Any],
    team_reasons: Mapping[str, list[str]],
) -> list[str]:
    messages: list[str] = []
    if scenario.get("scenario_type") == "road_closure":
        links = ", ".join(scenario.get("affected_link_ids", []))
        for team_id in sorted(team_reasons):
            messages.append(
                f"{team_id}의 남은 경로가 통제 링크 {links}를 사용해 "
                "통제 링크를 제외한 경로로 다시 계산했습니다."
            )
    if scenario.get("scenario_type") == "heavy_rain":
        links = ", ".join(scenario.get("affected_link_ids", []))
        messages.append(
            f"폭우 What-if 영향 링크 {links}의 위험 우선순위와 점검시간, "
            "이동시간을 보수적으로 조정했습니다."
        )
        messages.append(
            "영향팀의 남은 업무만 다시 비교하고 비영향팀 경로는 "
            "고정했습니다."
        )
    return messages


def build_partial_replan(
    resource_payload: Mapping[str, Any],
    field_tasks: Iterable[Mapping[str, Any]],
    base_allocation: Mapping[str, Any],
    scenario_matrix: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    base_alternative_id: str = "safety_first",
    completed_task_ids: Iterable[str] = (),
    balanced_min_safety_ratio: float = 0.95,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replan only affected teams while preserving completed and locked work."""

    tasks = [copy.deepcopy(dict(task)) for task in field_tasks]
    completed = {str(value) for value in completed_task_ids}
    trace: list[dict[str, Any]] = []
    resource_plan, resource_report = validate_resource_plan(resource_payload)
    base = _base_plan(base_allocation, base_alternative_id)
    scenario_type = str(scenario.get("scenario_type"))
    scenario_links = {
        link_id
        for value in scenario.get("affected_link_ids", [])
        if (link_id := normalize_link_id(value)) is not None
    }
    scenario_payload = {**dict(scenario), "affected_link_ids": sorted(scenario_links)}
    scenario_errors = []
    if resource_report.get("status") != "pass":
        scenario_errors.append("resource_validation_failed")
    if base is None:
        scenario_errors.append("base_alternative_missing")
    if scenario_type not in {"road_closure", "heavy_rain"}:
        scenario_errors.append("unsupported_scenario_type")
    if not scenario_links:
        scenario_errors.append("affected_link_ids_missing")
    trace.append(
        _trace(
            1,
            "scenario_validator",
            "fail" if scenario_errors else "pass",
            output_summary={
                "scenario_type": scenario_type,
                "affected_link_ids": sorted(scenario_links),
                "base_alternative_id": base_alternative_id,
                "errors": scenario_errors,
            },
        )
    )
    if scenario_errors:
        return _failure(
            scenario_payload,
            trace,
            "scenario_validation_failed",
            scenario_errors,
        )

    assignments = list(base["assignments"])
    prefix_errors = _completed_prefix_errors(assignments, completed)
    affected_team_ids, team_reasons = _affected_teams(
        assignments, completed, scenario_payload
    )
    trace.append(
        _trace(
            2,
            "preservation_planner",
            "fail" if prefix_errors else "pass",
            output_summary={
                "completed_task_ids": sorted(completed),
                "affected_team_ids": affected_team_ids,
                "unaffected_team_ids": sorted(
                    {
                        str(row["team_id"]) for row in assignments
                    }
                    - set(affected_team_ids)
                ),
                "team_reasons": team_reasons,
                "errors": prefix_errors,
            },
        )
    )
    if prefix_errors:
        return _failure(
            scenario_payload,
            trace,
            "completed_task_preservation_failed",
            prefix_errors,
        )
    if not affected_team_ids:
        return _failure(
            scenario_payload,
            trace,
            "scenario_does_not_affect_remaining_plan",
            [],
        )

    subresources, remaining_tasks, submatrix, consumed_by_team = _subproblem(
        resource_plan,
        tasks,
        scenario_matrix,
        base,
        affected_team_ids=affected_team_ids,
        completed_task_ids=completed,
    )
    trace.append(
        _trace(
            3,
            "partial_problem_builder",
            "pass" if remaining_tasks else "fail",
            output_summary={
                "affected_team_count": len(affected_team_ids),
                "remaining_task_count": len(remaining_tasks),
                "submatrix_route_count": len(submatrix["routes"]),
                "consumed_minutes_by_team": consumed_by_team,
            },
            limitations=[
                "tasks_cannot_move_to_unaffected_teams_in_partial_replan_v0.1"
            ],
        )
    )
    if not remaining_tasks:
        return _failure(
            scenario_payload,
            trace,
            "no_remaining_affected_tasks",
            [],
        )

    optimized, optimized_report = build_constraint_allocation(
        subresources,
        remaining_tasks,
        submatrix,
        balanced_min_safety_ratio=balanced_min_safety_ratio,
    )
    trace.append(
        _trace(
            4,
            "affected_team_optimizer",
            str(optimized_report.get("status")),
            output_summary={
                "candidate_combination_count": optimized.get("solver", {}).get(
                    "candidate_combination_count"
                ),
                "alternative_count": len(optimized.get("alternatives", [])),
                "failed_checks": optimized_report.get("failed_checks", []),
            },
        )
    )
    if optimized_report.get("status") != "pass":
        return _failure(
            scenario_payload,
            trace,
            str(optimized.get("failure_reason") or "partial_optimizer_failed"),
            optimized_report.get("failed_checks", []),
        )
    selected_id = (
        "balanced_operations"
        if base_alternative_id == "balanced_operations"
        else "safety_first"
    )
    selected = next(
        plan
        for plan in optimized["alternatives"]
        if plan["alternative_id"] == selected_id
    )
    combined = _combine_plan(
        resource_plan,
        tasks,
        base,
        selected,
        affected_team_ids=affected_team_ids,
        completed_task_ids=completed,
        consumed_by_team=consumed_by_team,
    )
    violations = _combined_violations(
        resource_plan,
        base,
        combined,
        affected_team_ids=affected_team_ids,
        completed_task_ids=completed,
        scenario=scenario_payload,
    )
    combined["constraint_violations"] = violations
    combined["metrics"]["constraint_violation_count"] = len(violations)
    trace.append(
        _trace(
            5,
            "replan_validator",
            "fail" if violations else "pass",
            output_summary={
                "completed_preserved_count": len(completed),
                "fixed_assignment_count": len(
                    resource_plan["constraints"]["fixed_assignments"]
                ),
                "unaffected_team_count": len(resource_plan["teams"])
                - len(affected_team_ids),
                "violation_count": len(violations),
                "violations": violations,
            },
        )
    )
    if violations:
        return _failure(
            scenario_payload,
            trace,
            "combined_replan_validation_failed",
            violations,
        )

    fixed_link_ids = {
        str(row["link_id"])
        for row in resource_plan["constraints"]["fixed_assignments"]
    }
    diff = _plan_diff(
        base,
        combined,
        affected_team_ids=affected_team_ids,
        completed_task_ids=completed,
        fixed_link_ids=fixed_link_ids,
        team_reasons=team_reasons,
    )
    explanation = {
        "summary": (
            f"{scenario_type} 시나리오로 {len(affected_team_ids)}개 팀의 "
            "남은 경로만 재계획했습니다."
        ),
        "affected_team_ids": affected_team_ids,
        "unchanged_team_ids": diff["unchanged_team_ids"],
        "preserved_completed_task_ids": diff["preserved_completed_task_ids"],
        "preserved_fixed_task_ids": diff["preserved_fixed_task_ids"],
        "metric_delta": diff["metric_delta"],
        "team_change_reasons": team_reasons,
        "change_reason_messages": _reason_messages(
            scenario_payload, team_reasons
        ),
        "warnings": [
            (
                "시나리오 결과이며 실제 통제 또는 관측된 폭우로 "
                "단정하지 않습니다."
            ),
            (
                "도로시간은 제한속도 기반 자유흐름 추정치이며 "
                "실시간 ETA가 아닙니다."
            ),
            "담당자 승인 전에는 현장 지시로 사용하지 않습니다.",
        ],
        "manual_approval_required": True,
    }
    trace.append(
        _trace(
            6,
            "change_explainer",
            "pass",
            output_summary={
                "affected_team_ids": affected_team_ids,
                "unchanged_team_ids": diff["unchanged_team_ids"],
                "metric_delta": diff["metric_delta"],
                "manual_approval_required": True,
            },
        )
    )
    result = {
        "schema_version": 1,
        "replanning_version": REPLANNING_VERSION,
        "status": "pass",
        "scenario": scenario_payload,
        "base_alternative_id": base_alternative_id,
        "completed_task_ids": sorted(completed),
        "affected_team_ids": affected_team_ids,
        "selected_subplan": selected_id,
        "replanned_plan": combined,
        "change_diff": diff,
        "explanation": explanation,
        "tool_trace": trace,
        "manual_approval_required": True,
    }
    report = {
        "schema_version": 1,
        "replanning_version": REPLANNING_VERSION,
        "status": "pass",
        "completed_tool_count": len(trace),
        "tool_statuses": {
            row["tool_name"]: row["status"] for row in trace
        },
        "failed_checks": [],
        "affected_team_count": len(affected_team_ids),
        "unchanged_team_count": len(resource_plan["teams"])
        - len(affected_team_ids),
    }
    return result, report
