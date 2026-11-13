"""Build deterministic constraint-based RoadOps allocation alternatives.

도로망 이동시간과 운영 제약을 만족하는 안전 우선·업무 균형 배분안을 탐색합니다.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import pvariance
from typing import Any, Iterable, Iterator, Mapping

from roadops.resources import validate_resource_plan


OPTIMIZER_VERSION = "roadops-constraint-allocation-v0.1"
MAX_EXACT_TASKS = 10
HIGH_PRIORITY_SCORE = 50.0


@dataclass(frozen=True)
class RouteOption:
    team_id: str
    task_indices: tuple[int, ...]
    task_mask: int
    travel_minutes: float
    service_minutes: float
    elapsed_minutes: float
    legs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PlanCandidate:
    route_options: tuple[RouteOption, ...]
    task_mask: int
    priority_sum: float
    assigned_count: int
    total_travel_minutes: float
    total_service_minutes: float
    maximum_team_elapsed_minutes: float
    elapsed_variance: float
    workload_variance: float
    fingerprint: str


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _task_capable(team: Mapping[str, Any], task: Mapping[str, Any]) -> bool:
    return set(task.get("required_skills", [])).issubset(team.get("skills", [])) and set(
        task.get("required_equipment", [])
    ).issubset(team.get("equipment", []))


def _available_minutes(resource_plan: Mapping[str, Any]) -> dict[str, float]:
    planning_start = datetime.fromisoformat(
        str(resource_plan["planning"]["planning_start_at"])
    )
    result: dict[str, float] = {}
    for team in resource_plan["teams"]:
        shift_start = datetime.fromisoformat(str(team["shift_start_at"]))
        shift_end = datetime.fromisoformat(str(team["shift_end_at"]))
        result[str(team["team_id"])] = (
            shift_end - max(planning_start, shift_start)
        ).total_seconds() / 60
    return result


def _route_index(travel_matrix: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row["origin_id"]), str(row["destination_task_id"])): dict(row)
        for row in travel_matrix.get("routes", [])
    }


def _option_for_sequence(
    team_id: str,
    sequence: tuple[int, ...],
    tasks: list[dict[str, Any]],
    routes: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    available_minutes: float,
) -> RouteOption | None:
    origin_id = team_id
    travel_minutes = 0.0
    service_minutes = 0.0
    elapsed = 0.0
    legs: list[dict[str, Any]] = []
    for task_index in sequence:
        task = tasks[task_index]
        route = routes.get((origin_id, str(task["task_id"])))
        if route is None or route.get("travel_time_minutes") is None:
            return None
        leg_minutes = float(route["travel_time_minutes"])
        service = float(task["service_minutes"])
        travel_minutes += leg_minutes
        service_minutes += service
        elapsed += leg_minutes + service
        if elapsed > available_minutes + 1e-9:
            return None
        legs.append(
            {
                "origin_id": origin_id,
                "destination_task_id": task["task_id"],
                "route_id": route["route_id"],
                "route_status": route["status"],
                "travel_minutes": round(leg_minutes, 3),
                "distance_km": route.get("distance_km"),
                "service_minutes": round(service, 3),
                "cumulative_minutes": round(elapsed, 3),
                "route_link_ids": route.get("route_link_ids", []),
            }
        )
        origin_id = str(task["task_id"])
    mask = sum(1 << index for index in sequence)
    return RouteOption(
        team_id=team_id,
        task_indices=sequence,
        task_mask=mask,
        travel_minutes=round(travel_minutes, 6),
        service_minutes=round(service_minutes, 6),
        elapsed_minutes=round(elapsed, 6),
        legs=tuple(legs),
    )


def _team_route_options(
    team: Mapping[str, Any],
    tasks: list[dict[str, Any]],
    routes: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    available_minutes: float,
    max_tasks: int,
    fixed_task_indices: set[int],
    forbidden_task_indices: set[int],
) -> list[RouteOption]:
    team_id = str(team["team_id"])
    eligible = [
        index
        for index, task in enumerate(tasks)
        if index not in forbidden_task_indices and _task_capable(team, task)
    ]
    options_by_mask: dict[int, RouteOption] = {}
    minimum_size = len(fixed_task_indices)
    maximum_size = min(max_tasks, len(eligible))
    for size in range(minimum_size, maximum_size + 1):
        for sequence in itertools.permutations(eligible, size):
            if not fixed_task_indices.issubset(sequence):
                continue
            option = _option_for_sequence(
                team_id,
                sequence,
                tasks,
                routes,
                available_minutes=available_minutes,
            )
            if option is None:
                continue
            known = options_by_mask.get(option.task_mask)
            if known is None or (
                option.travel_minutes,
                option.elapsed_minutes,
                option.task_indices,
            ) < (
                known.travel_minutes,
                known.elapsed_minutes,
                known.task_indices,
            ):
                options_by_mask[option.task_mask] = option
    return sorted(
        options_by_mask.values(),
        key=lambda option: (
            option.task_mask,
            option.travel_minutes,
            option.task_indices,
        ),
    )


def _fingerprint(options: Iterable[RouteOption]) -> str:
    payload = [
        {"team_id": option.team_id, "task_indices": option.task_indices}
        for option in options
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _candidate(
    options: tuple[RouteOption, ...],
    tasks: list[dict[str, Any]],
) -> PlanCandidate:
    mask = 0
    for option in options:
        mask |= option.task_mask
    assigned_indices = [
        index for index in range(len(tasks)) if mask & (1 << index)
    ]
    elapsed = [option.elapsed_minutes for option in options]
    workloads = [len(option.task_indices) for option in options]
    return PlanCandidate(
        route_options=options,
        task_mask=mask,
        priority_sum=round(
            sum(float(tasks[index]["priority_score"]) for index in assigned_indices),
            6,
        ),
        assigned_count=len(assigned_indices),
        total_travel_minutes=round(
            sum(option.travel_minutes for option in options), 6
        ),
        total_service_minutes=round(
            sum(option.service_minutes for option in options), 6
        ),
        maximum_team_elapsed_minutes=round(max(elapsed, default=0.0), 6),
        elapsed_variance=round(pvariance(elapsed), 6) if elapsed else 0.0,
        workload_variance=round(pvariance(workloads), 6) if workloads else 0.0,
        fingerprint=_fingerprint(options),
    )


def _candidate_combinations(
    team_ids: list[str],
    options_by_team: Mapping[str, list[RouteOption]],
    tasks: list[dict[str, Any]],
    *,
    mandatory_mask: int,
) -> Iterator[PlanCandidate]:
    def visit(
        team_index: int,
        used_mask: int,
        selected: list[RouteOption],
    ) -> Iterator[PlanCandidate]:
        if team_index == len(team_ids):
            if used_mask & mandatory_mask == mandatory_mask:
                yield _candidate(tuple(selected), tasks)
            return
        team_id = team_ids[team_index]
        for option in options_by_team[team_id]:
            if option.task_mask & used_mask:
                continue
            selected.append(option)
            yield from visit(
                team_index + 1,
                used_mask | option.task_mask,
                selected,
            )
            selected.pop()

    yield from visit(0, 0, [])


def _safety_key(candidate: PlanCandidate) -> tuple[Any, ...]:
    return (
        -candidate.priority_sum,
        -candidate.assigned_count,
        candidate.total_travel_minutes,
        candidate.maximum_team_elapsed_minutes,
        candidate.elapsed_variance,
        candidate.fingerprint,
    )


def _balanced_key(candidate: PlanCandidate) -> tuple[Any, ...]:
    return (
        candidate.maximum_team_elapsed_minutes,
        candidate.elapsed_variance,
        candidate.workload_variance,
        candidate.total_travel_minutes,
        -candidate.priority_sum,
        -candidate.assigned_count,
        candidate.fingerprint,
    )


def _task_unassigned_reason(
    task_index: int,
    tasks: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    routes: Mapping[tuple[str, str], Mapping[str, Any]],
) -> str:
    task = tasks[task_index]
    capable = [team for team in teams if _task_capable(team, task)]
    if not capable:
        return "no_team_with_required_capability"
    reachable = [
        team
        for team in capable
        if (route := routes.get((str(team["team_id"]), str(task["task_id"]))))
        is not None
        and route.get("travel_time_minutes") is not None
    ]
    if not reachable:
        return "no_team_with_available_road_route"
    return "not_selected_under_shift_and_objective_tradeoff"


def _constraint_violations(
    candidate: PlanCandidate,
    tasks: list[dict[str, Any]],
    resource_plan: Mapping[str, Any],
    *,
    mandatory_indices: set[int],
    fixed_by_task: Mapping[int, str],
    available_by_team: Mapping[str, float],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    seen: dict[int, str] = {}
    max_tasks = int(resource_plan["planning"]["max_tasks_per_team"])
    team_index = {
        str(team["team_id"]): team for team in resource_plan["teams"]
    }
    for option in candidate.route_options:
        if len(option.task_indices) > max_tasks:
            violations.append(
                {"code": "team_task_limit_exceeded", "team_id": option.team_id}
            )
        if option.elapsed_minutes > available_by_team[option.team_id] + 1e-9:
            violations.append(
                {"code": "team_shift_exceeded", "team_id": option.team_id}
            )
        for task_index in option.task_indices:
            if task_index in seen:
                violations.append(
                    {
                        "code": "duplicate_task_assignment",
                        "task_id": tasks[task_index]["task_id"],
                    }
                )
            seen[task_index] = option.team_id
            if tasks[task_index].get("excluded"):
                violations.append(
                    {
                        "code": "excluded_task_assigned",
                        "task_id": tasks[task_index]["task_id"],
                    }
                )
            if not _task_capable(team_index[option.team_id], tasks[task_index]):
                violations.append(
                    {
                        "code": "task_capability_violation",
                        "task_id": tasks[task_index]["task_id"],
                        "team_id": option.team_id,
                    }
                )
    for task_index in mandatory_indices:
        if task_index not in seen:
            violations.append(
                {
                    "code": "mandatory_task_unassigned",
                    "task_id": tasks[task_index]["task_id"],
                }
            )
    for task_index, team_id in fixed_by_task.items():
        if seen.get(task_index) != team_id:
            violations.append(
                {
                    "code": "fixed_assignment_unfulfilled",
                    "task_id": tasks[task_index]["task_id"],
                    "team_id": team_id,
                }
            )
    return violations


def _serialize_plan(
    candidate: PlanCandidate,
    *,
    alternative_id: str,
    objective: str,
    tasks: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    routes: Mapping[tuple[str, str], Mapping[str, Any]],
    resource_plan: Mapping[str, Any],
    mandatory_indices: set[int],
    fixed_by_task: Mapping[int, str],
    available_by_team: Mapping[str, float],
    total_priority: float,
) -> dict[str, Any]:
    assigned_indices = {
        index
        for option in candidate.route_options
        for index in option.task_indices
    }
    assignments: list[dict[str, Any]] = []
    team_summaries: list[dict[str, Any]] = []
    for option in candidate.route_options:
        for sequence, (task_index, leg) in enumerate(
            zip(option.task_indices, option.legs), start=1
        ):
            task = tasks[task_index]
            assignments.append(
                {
                    "team_id": option.team_id,
                    "sequence": sequence,
                    "task_id": task["task_id"],
                    "link_id": task["link_id"],
                    "road_name": task.get("road_name"),
                    "priority_score": task["priority_score"],
                    "mandatory": task_index in mandatory_indices,
                    "fixed_assignment": fixed_by_task.get(task_index)
                    == option.team_id,
                    **leg,
                }
            )
        team_summaries.append(
            {
                "team_id": option.team_id,
                "assignment_count": len(option.task_indices),
                "task_ids": [tasks[index]["task_id"] for index in option.task_indices],
                "travel_minutes": round(option.travel_minutes, 3),
                "service_minutes": round(option.service_minutes, 3),
                "elapsed_minutes": round(option.elapsed_minutes, 3),
                "available_minutes": round(available_by_team[option.team_id], 3),
                "remaining_minutes": round(
                    available_by_team[option.team_id] - option.elapsed_minutes, 3
                ),
            }
        )
    unassigned = [
        {
            "task_id": task["task_id"],
            "link_id": task["link_id"],
            "priority_score": task["priority_score"],
            "mandatory": index in mandatory_indices,
            "reason": _task_unassigned_reason(index, tasks, teams, routes),
        }
        for index, task in enumerate(tasks)
        if index not in assigned_indices
    ]
    violations = _constraint_violations(
        candidate,
        tasks,
        resource_plan,
        mandatory_indices=mandatory_indices,
        fixed_by_task=fixed_by_task,
        available_by_team=available_by_team,
    )
    workload_counts = [len(option.task_indices) for option in candidate.route_options]
    high_unassigned = [
        row
        for row in unassigned
        if float(row["priority_score"]) >= HIGH_PRIORITY_SCORE
    ]
    return {
        "alternative_id": alternative_id,
        "objective": objective,
        "plan_fingerprint": candidate.fingerprint,
        "assignments": assignments,
        "team_summaries": team_summaries,
        "unassigned_tasks": unassigned,
        "constraint_violations": violations,
        "metrics": {
            "candidate_task_count": len(tasks),
            "assigned_task_count": candidate.assigned_count,
            "unassigned_task_count": len(tasks) - candidate.assigned_count,
            "assigned_priority_sum": round(candidate.priority_sum, 3),
            "candidate_priority_sum": round(total_priority, 3),
            "risk_weighted_coverage_ratio": (
                round(candidate.priority_sum / total_priority, 6)
                if total_priority
                else None
            ),
            "high_priority_unassigned_count": len(high_unassigned),
            "network_total_travel_minutes": round(
                candidate.total_travel_minutes, 3
            ),
            "total_service_minutes": round(candidate.total_service_minutes, 3),
            "maximum_team_elapsed_minutes": round(
                candidate.maximum_team_elapsed_minutes, 3
            ),
            "workload_task_counts": {
                option.team_id: len(option.task_indices)
                for option in candidate.route_options
            },
            "workload_count_range": (
                max(workload_counts) - min(workload_counts)
                if workload_counts
                else 0
            ),
            "workload_count_variance": round(candidate.workload_variance, 6),
            "elapsed_minutes_variance": round(candidate.elapsed_variance, 6),
            "constraint_violation_count": len(violations),
        },
    }


def build_constraint_allocation(
    resource_payload: Mapping[str, Any],
    field_tasks: Iterable[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
    *,
    balanced_min_safety_ratio: float = 0.95,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Find two feasible deterministic plans from exact small-instance search."""

    resource_plan, resource_report = validate_resource_plan(resource_payload)
    if resource_report["status"] == "fail":
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "resource_input_validation_failed",
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "failed_checks": ["resource_input_validation"],
            },
        )
    if not 0 < balanced_min_safety_ratio <= 1:
        raise ValueError("balanced_min_safety_ratio must be in (0, 1]")
    if travel_matrix.get("status") not in {"pass", "pass_with_limitations"}:
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "travel_matrix_not_usable",
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "failed_checks": ["travel_matrix_not_usable"],
            },
        )

    tasks = [dict(task) for task in field_tasks if not bool(task.get("excluded"))]
    tasks.sort(key=lambda task: str(task["task_id"]))
    if len(tasks) > MAX_EXACT_TASKS:
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "exact_solver_task_limit_exceeded",
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "task_count": len(tasks),
                "failed_checks": ["exact_solver_task_limit_exceeded"],
            },
        )
    task_by_link = {str(task["link_id"]): index for index, task in enumerate(tasks)}
    missing_required_links = sorted(
        (
            set(resource_plan["constraints"]["mandatory_link_ids"])
            | {
                str(row["link_id"])
                for row in resource_plan["constraints"]["fixed_assignments"]
            }
        )
        - set(task_by_link)
    )
    if missing_required_links:
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "required_tasks_missing",
                "missing_required_link_ids": missing_required_links,
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "failed_checks": ["required_tasks_missing"],
            },
        )

    mandatory_indices = {
        task_by_link[link_id]
        for link_id in resource_plan["constraints"]["mandatory_link_ids"]
    }
    fixed_by_task = {
        task_by_link[str(row["link_id"])]: str(row["team_id"])
        for row in resource_plan["constraints"]["fixed_assignments"]
    }
    mandatory_mask = sum(1 << index for index in mandatory_indices)
    routes = _route_index(travel_matrix)
    available_by_team = _available_minutes(resource_plan)
    max_tasks = int(resource_plan["planning"]["max_tasks_per_team"])
    teams = [dict(team) for team in resource_plan["teams"]]
    team_ids = [str(team["team_id"]) for team in teams]
    options_by_team: dict[str, list[RouteOption]] = {}
    for team in teams:
        team_id = str(team["team_id"])
        fixed_for_team = {
            task_index
            for task_index, fixed_team_id in fixed_by_task.items()
            if fixed_team_id == team_id
        }
        fixed_for_other = set(fixed_by_task) - fixed_for_team
        options_by_team[team_id] = _team_route_options(
            team,
            tasks,
            routes,
            available_minutes=available_by_team[team_id],
            max_tasks=max_tasks,
            fixed_task_indices=fixed_for_team,
            forbidden_task_indices=fixed_for_other,
        )
    teams_without_options = [
        team_id for team_id, options in options_by_team.items() if not options
    ]
    if teams_without_options:
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "team_has_no_feasible_route_option",
                "team_ids": teams_without_options,
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "failed_checks": ["team_route_option_feasibility"],
            },
        )

    safety: PlanCandidate | None = None
    candidate_count = 0
    for candidate in _candidate_combinations(
        team_ids,
        options_by_team,
        tasks,
        mandatory_mask=mandatory_mask,
    ):
        candidate_count += 1
        if safety is None or _safety_key(candidate) < _safety_key(safety):
            safety = candidate
    if safety is None:
        return (
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "status": "fail",
                "failure_reason": "no_globally_feasible_plan",
                "alternatives": [],
            },
            {
                "schema_version": 1,
                "status": "fail",
                "resource_validation": resource_report,
                "route_option_counts": {
                    key: len(value) for key, value in options_by_team.items()
                },
                "failed_checks": ["global_plan_feasibility"],
            },
        )

    minimum_balanced_priority = safety.priority_sum * balanced_min_safety_ratio
    balanced: PlanCandidate | None = None
    collapsed_alternative: PlanCandidate | None = None
    for candidate in _candidate_combinations(
        team_ids,
        options_by_team,
        tasks,
        mandatory_mask=mandatory_mask,
    ):
        if candidate.priority_sum + 1e-9 < minimum_balanced_priority:
            continue
        if collapsed_alternative is None or _balanced_key(candidate) < _balanced_key(
            collapsed_alternative
        ):
            collapsed_alternative = candidate
        if candidate.fingerprint == safety.fingerprint:
            continue
        if balanced is None or _balanced_key(candidate) < _balanced_key(balanced):
            balanced = candidate
    if balanced is None:
        balanced = collapsed_alternative or safety

    total_priority = sum(float(task["priority_score"]) for task in tasks)
    alternatives = [
        _serialize_plan(
            safety,
            alternative_id="safety_first",
            objective=(
                "maximize_risk_coverage_then_minimize_network_travel_time"
            ),
            tasks=tasks,
            teams=teams,
            routes=routes,
            resource_plan=resource_plan,
            mandatory_indices=mandatory_indices,
            fixed_by_task=fixed_by_task,
            available_by_team=available_by_team,
            total_priority=total_priority,
        ),
        _serialize_plan(
            balanced,
            alternative_id="balanced_operations",
            objective=(
                f"retain_at_least_{balanced_min_safety_ratio:.3f}_of_safety_priority_"
                "then_minimize_maximum_team_elapsed_time"
            ),
            tasks=tasks,
            teams=teams,
            routes=routes,
            resource_plan=resource_plan,
            mandatory_indices=mandatory_indices,
            fixed_by_task=fixed_by_task,
            available_by_team=available_by_team,
            total_priority=total_priority,
        ),
    ]
    hard_violations = [
        {"alternative_id": plan["alternative_id"], **violation}
        for plan in alternatives
        for violation in plan["constraint_violations"]
    ]
    failed_checks = ["optimized_plan_constraint_integrity"] if hard_violations else []
    status = "fail" if failed_checks else "pass"
    result = {
        "schema_version": 1,
        "optimizer_version": OPTIMIZER_VERSION,
        "scenario_id": resource_plan["scenario_id"],
        "status": status,
        "solver": {
            "method": "deterministic_exact_route_enumeration_and_set_packing",
            "maximum_supported_task_count": MAX_EXACT_TASKS,
            "candidate_combination_count": candidate_count,
            "balanced_min_safety_ratio": balanced_min_safety_ratio,
            "alternative_collapsed": safety.fingerprint == balanced.fingerprint,
        },
        "hard_constraints": [
            "one_team_per_task",
            "mandatory_tasks_assigned",
            "fixed_team_assignments_honored",
            "team_skill_and_equipment_requirements",
            "maximum_tasks_per_team",
            "shift_time_with_network_travel_and_service",
            "unavailable_or_closed_routes_not_used",
        ],
        "alternatives": alternatives,
        "comparison": {
            plan["alternative_id"]: plan["metrics"] for plan in alternatives
        },
    }
    report = {
        "schema_version": 1,
        "status": status,
        "optimizer_version": OPTIMIZER_VERSION,
        "resource_validation": resource_report,
        "task_count": len(tasks),
        "team_count": len(teams),
        "route_option_counts": {
            key: len(value) for key, value in sorted(options_by_team.items())
        },
        "candidate_combination_count": candidate_count,
        "alternative_count": len(alternatives),
        "hard_violations": hard_violations,
        "failed_checks": failed_checks,
    }
    return result, report
