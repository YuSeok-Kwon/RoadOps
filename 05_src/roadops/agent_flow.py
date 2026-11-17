"""Orchestrate one auditable RoadOps request across deterministic tools.

자연어 요청을 품질검사부터 설명까지 일곱 개 도구로 연결합니다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping

from roadops.allocation_baselines import build_field_tasks
from roadops.allocation_optimizer import build_constraint_allocation
from roadops.resources import validate_resource_plan


AGENT_VERSION = "roadops-agent-flow-v0.1"
SUCCESS_STATUSES = {"pass", "pass_with_limitations"}
REQUIRED_QUALITY_REPORTS = {
    "integrated_events",
    "risk_forecasts",
    "travel_time_matrix",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _first_integer(text: str, patterns: tuple[str, ...]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def parse_agent_request(request_text: str) -> dict[str, Any]:
    """Parse the constrained Korean request grammar used by the offline demo."""

    normalized = " ".join(str(request_text or "").split())
    if not normalized:
        raise ValueError("request_text must not be empty")
    team_count = _first_integer(
        normalized,
        (
            r"(?:순찰팀|팀)\s*(\d+)\s*개",
            r"(\d+)\s*개(?:의)?\s*(?:순찰팀|팀)",
        ),
    )
    vehicle_count = _first_integer(
        normalized,
        (
            r"차량\s*(\d+)\s*대",
            r"(\d+)\s*대(?:의)?\s*차량",
        ),
    )
    duration_hours = _first_integer(
        normalized,
        (
            r"(\d+)\s*시간\s*(?:안|이내)",
            r"근무시간\s*(\d+)\s*시간",
        ),
    )
    horizon_match = re.search(r"(\d+)\s*시간\s*(?:후|뒤)", normalized)
    if horizon_match:
        horizon_hours = int(horizon_match.group(1))
    elif "현재" in normalized or "지금" in normalized:
        horizon_hours = 0
    else:
        horizon_hours = 0

    requested_alternatives: list[str] = []
    if "안전" in normalized:
        requested_alternatives.append("safety_first")
    if "균형" in normalized:
        requested_alternatives.append("balanced_operations")
    if "비교" in normalized or not requested_alternatives:
        requested_alternatives = ["safety_first", "balanced_operations"]

    return {
        "normalized_request": normalized,
        "team_count": team_count,
        "vehicle_count": vehicle_count,
        "duration_hours": duration_hours,
        "horizon_hours": horizon_hours,
        "requested_alternative_ids": requested_alternatives,
        "manual_approval_required": True,
        "parser_semantics": "deterministic_korean_demo_grammar_not_general_llm",
    }


def _trace(
    sequence: int,
    tool_name: str,
    status: str,
    *,
    input_summary: Mapping[str, Any],
    output_summary: Mapping[str, Any],
    limitations: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "tool_name": tool_name,
        "status": status,
        "input_summary": dict(input_summary),
        "output_summary": dict(output_summary),
        "limitations": list(limitations),
    }


def _failure(
    request_text: str,
    parsed_request: Mapping[str, Any] | None,
    trace: list[dict[str, Any]],
    *,
    failure_reason: str,
    failure_details: Iterable[Any] = (),
    execution_mode: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = _digest(
        {
            "agent_version": AGENT_VERSION,
            "request": request_text,
            "execution_mode": execution_mode,
        }
    )
    details = list(failure_details)
    result = {
        "schema_version": 1,
        "agent_version": AGENT_VERSION,
        "run_id": run_id,
        "status": "fail",
        "execution_mode": execution_mode,
        "request_text": request_text,
        "parsed_request": dict(parsed_request or {}),
        "failure_reason": failure_reason,
        "failure_details": details,
        "tool_trace": trace,
        "final_response": {
            "summary": "실행 가능한 순찰계획을 생성하지 못했습니다.",
            "reason": failure_reason,
            "details": details,
            "manual_approval_required": True,
        },
    }
    report = {
        "schema_version": 1,
        "agent_version": AGENT_VERSION,
        "run_id": run_id,
        "status": "fail",
        "completed_tool_count": len(trace),
        "failed_tool": trace[-1]["tool_name"] if trace else None,
        "failed_checks": [failure_reason],
    }
    return result, report


def _available_minutes(resource_plan: Mapping[str, Any]) -> list[float]:
    planning_start = datetime.fromisoformat(
        str(resource_plan["planning"]["planning_start_at"])
    )
    values = []
    for team in resource_plan["teams"]:
        shift_start = datetime.fromisoformat(str(team["shift_start_at"]))
        shift_end = datetime.fromisoformat(str(team["shift_end_at"]))
        values.append(
            (shift_end - max(planning_start, shift_start)).total_seconds() / 60
        )
    return values


def _request_resource_errors(
    parsed: Mapping[str, Any], resource_plan: Mapping[str, Any]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    available_vehicles = [
        vehicle
        for vehicle in resource_plan["vehicles"]
        if vehicle["status"] == "available"
    ]
    checks = (
        ("team_count", parsed.get("team_count"), len(resource_plan["teams"])),
        ("vehicle_count", parsed.get("vehicle_count"), len(available_vehicles)),
        (
            "horizon_hours",
            parsed.get("horizon_hours"),
            resource_plan["planning"]["horizon_hours"],
        ),
    )
    for field, requested, available in checks:
        if requested is not None and requested != available:
            errors.append(
                {
                    "field": field,
                    "code": "request_resource_mismatch",
                    "requested": requested,
                    "available": available,
                }
            )
    requested_duration = parsed.get("duration_hours")
    if requested_duration is not None:
        insufficient = [
            round(minutes, 3)
            for minutes in _available_minutes(resource_plan)
            if minutes + 1e-9 < float(requested_duration) * 60
        ]
        if insufficient:
            errors.append(
                {
                    "field": "duration_hours",
                    "code": "insufficient_team_shift_time",
                    "requested": requested_duration,
                    "available_minutes_below_request": insufficient,
                }
            )
    return errors


def _quality_gate(
    quality_reports: Mapping[str, Mapping[str, Any]],
    resource_report: Mapping[str, Any],
    compatibility_errors: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "resources": {
            "status": resource_report.get("status"),
            "error_count": len(resource_report.get("errors", [])),
            "warning_count": len(resource_report.get("warnings", [])),
        }
    }
    if resource_report.get("status") != "pass":
        failures.append(
            {
                "dataset": "resources",
                "reason": "resource_validation_failed",
                "details": resource_report.get("errors", []),
            }
        )
    failures.extend(compatibility_errors)
    for dataset in sorted(REQUIRED_QUALITY_REPORTS - set(quality_reports)):
        failures.append(
            {
                "dataset": dataset,
                "reason": "required_quality_report_missing",
            }
        )
    for dataset, report in sorted(quality_reports.items()):
        status = str(report.get("status") or "missing")
        failed_checks = list(report.get("failed_checks", []))
        summary[dataset] = {"status": status, "failed_checks": failed_checks}
        if status not in SUCCESS_STATUSES or failed_checks:
            failures.append(
                {
                    "dataset": dataset,
                    "reason": "quality_gate_failed",
                    "status": status,
                    "failed_checks": failed_checks,
                }
            )
        elif status == "pass_with_limitations":
            limitations.append(
                {
                    "dataset": dataset,
                    "reason": "source_quality_passed_with_limitations",
                }
            )
    if failures:
        return "fail", failures, summary
    if limitations:
        return "pass_with_limitations", limitations, summary
    return "pass", [], summary


def _travel_matrix_errors(
    resource_plan: Mapping[str, Any],
    active_tasks: list[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if travel_matrix.get("status") not in SUCCESS_STATUSES:
        errors.append(
            {
                "code": "travel_matrix_not_usable",
                "status": travel_matrix.get("status"),
            }
        )
    scenario_id = travel_matrix.get("scenario_id")
    if scenario_id and scenario_id != resource_plan.get("scenario_id"):
        errors.append(
            {
                "code": "travel_matrix_scenario_mismatch",
                "resource_scenario_id": resource_plan.get("scenario_id"),
                "matrix_scenario_id": scenario_id,
            }
        )
    task_ids = {str(task["task_id"]) for task in active_tasks}
    team_ids = {str(team["team_id"]) for team in resource_plan["teams"]}
    required_origins = team_ids | task_ids
    available_pairs = {
        (str(row.get("origin_id")), str(row.get("destination_task_id")))
        for row in travel_matrix.get("routes", [])
    }
    missing_pairs = sorted(
        (origin, destination)
        for origin in required_origins
        for destination in task_ids
        if (origin, destination) not in available_pairs
    )
    if missing_pairs:
        errors.append(
            {
                "code": "travel_matrix_pairs_missing",
                "missing_pair_count": len(missing_pairs),
                "examples": missing_pairs[:10],
            }
        )
    unavailable_count = sum(
        row.get("travel_time_minutes") is None
        for row in travel_matrix.get("routes", [])
        if str(row.get("destination_task_id")) in task_ids
        and str(row.get("origin_id")) in required_origins
    )
    summary = {
        "route_semantics": travel_matrix.get("route_semantics"),
        "active_task_count": len(task_ids),
        "required_origin_count": len(required_origins),
        "required_pair_count": len(required_origins) * len(task_ids),
        "available_pair_count": len(required_origins) * len(task_ids)
        - len(missing_pairs),
        "unavailable_route_count": unavailable_count,
        "closed_link_count": len(travel_matrix.get("closed_link_ids", [])),
    }
    return errors, summary


def _validate_plans(
    allocation: Mapping[str, Any], requested_ids: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    plans = {
        str(plan["alternative_id"]): plan
        for plan in allocation.get("alternatives", [])
    }
    for alternative_id in requested_ids:
        plan = plans.get(alternative_id)
        if plan is None:
            failures.append(
                {
                    "alternative_id": alternative_id,
                    "code": "requested_alternative_missing",
                }
            )
            continue
        assignments = list(plan.get("assignments", []))
        task_ids = [str(row["task_id"]) for row in assignments]
        unique = len(task_ids) == len(set(task_ids))
        constraints_clear = not plan.get("constraint_violations")
        shifts_clear = all(
            float(team["elapsed_minutes"])
            <= float(team["available_minutes"]) + 1e-9
            for team in plan.get("team_summaries", [])
        )
        routes_clear = all(
            row.get("route_status") in {"ok", "cache_replay"}
            for row in assignments
        )
        check = {
            "alternative_id": alternative_id,
            "unique_task_assignments": unique,
            "hard_constraints_clear": constraints_clear,
            "team_shifts_clear": shifts_clear,
            "routes_available": routes_clear,
            "passed": unique and constraints_clear and shifts_clear and routes_clear,
        }
        checks.append(check)
        if not check["passed"]:
            failures.append(
                {"alternative_id": alternative_id, "code": "plan_validation_failed"}
            )
    return checks, failures


def _explain(
    parsed: Mapping[str, Any],
    allocation: Mapping[str, Any],
    *,
    execution_mode: str,
    quality_status: str,
    quality_limitations: list[dict[str, Any]],
    forecast_rows: list[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    requested = set(parsed["requested_alternative_ids"])
    alternatives = []
    for plan in allocation.get("alternatives", []):
        if plan["alternative_id"] not in requested:
            continue
        metrics = plan["metrics"]
        alternatives.append(
            {
                "alternative_id": plan["alternative_id"],
                "objective": plan["objective"],
                "assigned_task_count": metrics["assigned_task_count"],
                "unassigned_task_count": metrics["unassigned_task_count"],
                "risk_weighted_coverage_ratio": metrics[
                    "risk_weighted_coverage_ratio"
                ],
                "network_total_travel_minutes": metrics[
                    "network_total_travel_minutes"
                ],
                "maximum_team_elapsed_minutes": metrics[
                    "maximum_team_elapsed_minutes"
                ],
                "constraint_violation_count": metrics[
                    "constraint_violation_count"
                ],
                "pending_dispatch_approval_count": sum(
                    row.get("dispatch_approval_status") == "pending"
                    for row in plan["assignments"]
                ),
                "handoff_action_count": sum(
                    len(row.get("handoff_actions", []))
                    for row in plan["assignments"]
                ),
                "team_routes": [
                    {
                        "team_id": team["team_id"],
                        "task_ids": team["task_ids"],
                        "elapsed_minutes": team["elapsed_minutes"],
                        "remaining_minutes": team["remaining_minutes"],
                    }
                    for team in plan["team_summaries"]
                ],
            }
        )
    target_times = sorted(
        {
            str(row.get("target_at"))
            for row in forecast_rows
            if int(float(str(row.get("horizon_hours", -1))))
            == int(parsed["horizon_hours"])
            and row.get("target_at")
        }
    )
    warnings = [
        (
            "도로 이동시간은 제한속도 기반 자유흐름 추정치이며 "
            "실시간 ETA가 아닙니다."
        ),
        "결과는 담당자 승인 전에는 현장 지시로 사용하지 않습니다.",
    ]
    if execution_mode == "cached_demo":
        warnings.insert(
            0,
            "저장된 데모 스냅샷을 사용했으며 "
            "현재 실시간 상태가 아닙니다.",
        )
    if quality_status == "pass_with_limitations":
        warnings.append(
            "일부 데이터가 제한사항과 함께 통과해 "
            "품질 상태를 함께 표시합니다."
        )
    return {
        "summary": (
            f"{len(alternatives)}개의 실행 가능한 순찰 대안을 생성했습니다."
        ),
        "requested_horizon_hours": parsed["horizon_hours"],
        "data_reference": {
            "execution_mode": execution_mode,
            "forecast_target_times": target_times,
            "travel_time_semantics": travel_matrix.get("route_semantics"),
            "quality_status": quality_status,
        },
        "alternatives": alternatives,
        "external_handoff_queue": list(allocation.get("handoff_queue", [])),
        "suggested_review_order": [
            alternative_id
            for alternative_id in ("safety_first", "balanced_operations")
            if alternative_id in requested
        ],
        "quality_limitations": quality_limitations,
        "warnings": warnings,
        "manual_approval_required": True,
    }


def run_agent_flow(
    request_text: str,
    resource_payload: Mapping[str, Any],
    forecast_rows: Iterable[Mapping[str, Any]],
    integrated_event_rows: Iterable[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
    quality_reports: Mapping[str, Mapping[str, Any]],
    *,
    execution_mode: str = "cached_demo",
    balanced_min_safety_ratio: float = 0.95,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the seven-step RoadOps tool flow without manual intermediate edits."""

    forecasts = [dict(row) for row in forecast_rows]
    events = [dict(row) for row in integrated_event_rows]
    trace: list[dict[str, Any]] = []
    try:
        parsed = parse_agent_request(request_text)
    except ValueError as error:
        trace.append(
            _trace(
                1,
                "request_interpreter",
                "fail",
                input_summary={"request_text": request_text},
                output_summary={"error": str(error)},
            )
        )
        return _failure(
            request_text,
            None,
            trace,
            failure_reason="request_interpretation_failed",
            failure_details=[str(error)],
            execution_mode=execution_mode,
        )
    trace.append(
        _trace(
            1,
            "request_interpreter",
            "pass",
            input_summary={"request_text": request_text},
            output_summary=parsed,
            limitations=[parsed["parser_semantics"]],
        )
    )

    resource_plan, resource_report = validate_resource_plan(resource_payload)
    compatibility_errors = (
        _request_resource_errors(parsed, resource_plan)
        if resource_report.get("status") == "pass"
        else []
    )
    quality_status, quality_issues, quality_summary = _quality_gate(
        quality_reports, resource_report, compatibility_errors
    )
    trace.append(
        _trace(
            2,
            "data_quality_gate",
            quality_status,
            input_summary={
                "quality_report_ids": sorted(quality_reports),
                "execution_mode": execution_mode,
            },
            output_summary={
                "datasets": quality_summary,
                "issue_count": len(quality_issues),
            },
            limitations=[str(issue) for issue in quality_issues]
            if quality_status == "pass_with_limitations"
            else (),
        )
    )
    if quality_status == "fail":
        return _failure(
            request_text,
            parsed,
            trace,
            failure_reason="data_quality_gate_failed",
            failure_details=quality_issues,
            execution_mode=execution_mode,
        )

    tasks, task_report = build_field_tasks(
        forecasts,
        events,
        horizon_hours=int(parsed["horizon_hours"]),
        resource_plan=resource_plan,
    )
    active_tasks = [
        task
        for task in tasks
        if not task["excluded"] and task.get("road_team_dispatch_eligible", True)
    ]
    handoff_only_tasks = [
        task
        for task in tasks
        if not task["excluded"] and not task.get("road_team_dispatch_eligible", True)
    ]
    task_status = "pass" if active_tasks else "fail"
    trace.append(
        _trace(
            3,
            "risk_task_builder",
            task_status,
            input_summary={
                "forecast_row_count": len(forecasts),
                "integrated_event_row_count": len(events),
                "horizon_hours": parsed["horizon_hours"],
            },
            output_summary={
                **task_report,
                "active_task_count": len(active_tasks),
                "excluded_task_count": sum(task["excluded"] for task in tasks),
                "handoff_only_task_count": len(handoff_only_tasks),
            },
        )
    )
    if not active_tasks:
        return _failure(
            request_text,
            parsed,
            trace,
            failure_reason="no_active_risk_tasks",
            failure_details=[task_report],
            execution_mode=execution_mode,
        )

    travel_errors, travel_summary = _travel_matrix_errors(
        resource_plan, active_tasks, travel_matrix
    )
    trace.append(
        _trace(
            4,
            "travel_time_gate",
            "fail" if travel_errors else "pass",
            input_summary={
                "matrix_status": travel_matrix.get("status"),
                "route_count": len(travel_matrix.get("routes", [])),
            },
            output_summary=travel_summary,
            limitations=[str(error) for error in travel_errors],
        )
    )
    if travel_errors:
        return _failure(
            request_text,
            parsed,
            trace,
            failure_reason="travel_time_gate_failed",
            failure_details=travel_errors,
            execution_mode=execution_mode,
        )

    allocation, allocation_report = build_constraint_allocation(
        resource_plan,
        tasks,
        travel_matrix,
        balanced_min_safety_ratio=balanced_min_safety_ratio,
    )
    trace.append(
        _trace(
            5,
            "allocation_optimizer",
            str(allocation_report.get("status")),
            input_summary={
                "active_task_count": len(active_tasks),
                "team_count": len(resource_plan["teams"]),
                "balanced_min_safety_ratio": balanced_min_safety_ratio,
            },
            output_summary={
                "alternative_ids": [
                    plan["alternative_id"]
                    for plan in allocation.get("alternatives", [])
                ],
                "candidate_combination_count": allocation.get("solver", {}).get(
                    "candidate_combination_count"
                ),
                "failed_checks": allocation_report.get("failed_checks", []),
            },
        )
    )
    if allocation_report.get("status") != "pass":
        return _failure(
            request_text,
            parsed,
            trace,
            failure_reason=str(
                allocation.get("failure_reason") or "allocation_optimization_failed"
            ),
            failure_details=allocation_report.get("failed_checks", []),
            execution_mode=execution_mode,
        )

    validation_checks, validation_failures = _validate_plans(
        allocation, list(parsed["requested_alternative_ids"])
    )
    trace.append(
        _trace(
            6,
            "plan_validator",
            "fail" if validation_failures else "pass",
            input_summary={
                "requested_alternative_ids": parsed["requested_alternative_ids"]
            },
            output_summary={
                "checks": validation_checks,
                "failure_count": len(validation_failures),
            },
        )
    )
    if validation_failures:
        return _failure(
            request_text,
            parsed,
            trace,
            failure_reason="optimized_plan_validation_failed",
            failure_details=validation_failures,
            execution_mode=execution_mode,
        )

    final_response = _explain(
        parsed,
        allocation,
        execution_mode=execution_mode,
        quality_status=quality_status,
        quality_limitations=quality_issues,
        forecast_rows=forecasts,
        travel_matrix=travel_matrix,
    )
    trace.append(
        _trace(
            7,
            "result_explainer",
            "pass",
            input_summary={
                "alternative_count": len(allocation["alternatives"]),
                "quality_status": quality_status,
            },
            output_summary={
                "explained_alternative_count": len(final_response["alternatives"]),
                "manual_approval_required": True,
                "warning_count": len(final_response["warnings"]),
            },
            limitations=["template_explanation_not_general_llm"],
        )
    )

    run_id = _digest(
        {
            "agent_version": AGENT_VERSION,
            "request": parsed,
            "scenario_id": resource_plan["scenario_id"],
            "execution_mode": execution_mode,
        }
    )
    status = (
        "pass_with_limitations"
        if quality_status == "pass_with_limitations"
        else "pass"
    )
    result = {
        "schema_version": 1,
        "agent_version": AGENT_VERSION,
        "run_id": run_id,
        "status": status,
        "execution_mode": execution_mode,
        "request_text": request_text,
        "parsed_request": parsed,
        "scenario_id": resource_plan["scenario_id"],
        "field_tasks": tasks,
        "allocation": allocation,
        "validation_checks": validation_checks,
        "tool_trace": trace,
        "final_response": final_response,
    }
    report = {
        "schema_version": 1,
        "agent_version": AGENT_VERSION,
        "run_id": run_id,
        "status": status,
        "completed_tool_count": len(trace),
        "tool_statuses": {
            row["tool_name"]: row["status"] for row in trace
        },
        "failed_checks": [],
        "quality_status": quality_status,
        "quality_issues": quality_issues,
    }
    return result, report
