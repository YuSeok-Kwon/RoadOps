"""Evaluate RoadOps allocation plans on one comparable metric schema.

위험순·최근접 기준선과 최적화 대안을 같은 도로망 지표로 비교합니다.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from typing import Any, Callable, Mapping


EVALUATION_VERSION = "roadops-allocation-evaluation-v0.1"


def _plan_index(rows: list[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {str(row[key]): row for row in rows if row.get(key)}


def _round(value: float) -> float:
    return round(float(value), 3)


def _percent_reduction(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return round((before - after) / before * 100, 1)


def _result_fingerprint(result: Mapping[str, Any]) -> str:
    plans = [
        {
            "alternative_id": plan.get("alternative_id"),
            "plan_fingerprint": plan.get("plan_fingerprint"),
            "metrics": plan.get("metrics"),
        }
        for plan in result.get("alternatives", [])
    ]
    encoded = json.dumps(
        plans, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def benchmark_allocation(
    run_once: Callable[[], tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    repeats: int = 10,
) -> dict[str, Any]:
    """Measure repeated optimizer runs and verify stable plan outputs."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    durations: list[float] = []
    fingerprints: list[str] = []
    statuses: list[str] = []
    for _ in range(repeats):
        started = time.perf_counter()
        result, report = run_once()
        durations.append((time.perf_counter() - started) * 1000)
        fingerprints.append(_result_fingerprint(result))
        statuses.append(str(report.get("status")))

    ordered = sorted(durations)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    unique_fingerprints = sorted(set(fingerprints))
    return {
        "repeat_count": repeats,
        "duration_milliseconds": {
            "minimum": _round(min(durations)),
            "mean": _round(statistics.fmean(durations)),
            "median": _round(statistics.median(durations)),
            "p95_nearest_rank": _round(ordered[p95_index]),
            "maximum": _round(max(durations)),
        },
        "successful_run_count": sum(status == "pass" for status in statuses),
        "unique_plan_fingerprint_count": len(unique_fingerprints),
        "deterministic_outputs": len(unique_fingerprints) == 1,
        "plan_fingerprint": (
            unique_fingerprints[0] if len(unique_fingerprints) == 1 else None
        ),
    }


def evaluate_allocations(
    allocation_baselines: Mapping[str, Any],
    travel_time_matrix: Mapping[str, Any],
    optimized_allocation: Mapping[str, Any],
    *,
    benchmark: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one comparison table for all four allocation methods."""

    baseline_plans = _plan_index(
        list(allocation_baselines.get("plans", [])), "strategy"
    )
    baseline_network = _plan_index(
        list(travel_time_matrix.get("allocation_baseline_recheck", [])),
        "strategy",
    )
    alternatives = _plan_index(
        list(optimized_allocation.get("alternatives", [])), "alternative_id"
    )
    required = {
        "baseline:risk_first": baseline_plans.get("risk_first"),
        "baseline:nearest": baseline_plans.get("nearest"),
        "network:risk_first": baseline_network.get("risk_first"),
        "network:nearest": baseline_network.get("nearest"),
        "optimized:safety_first": alternatives.get("safety_first"),
        "optimized:balanced_operations": alternatives.get("balanced_operations"),
    }
    missing_inputs = sorted(key for key, value in required.items() if value is None)
    if missing_inputs:
        result = {
            "schema_version": 1,
            "evaluation_version": EVALUATION_VERSION,
            "status": "fail",
            "failure_reason": "required_evaluation_inputs_missing",
            "missing_inputs": missing_inputs,
            "comparison": [],
        }
        return result, {
            "schema_version": 1,
            "status": "fail",
            "failed_checks": ["required_evaluation_inputs"],
            "missing_inputs": missing_inputs,
        }

    comparison: list[dict[str, Any]] = []
    for method_id in ("risk_first", "nearest"):
        plan = baseline_plans[method_id]
        network = baseline_network[method_id]
        metrics = plan["metrics"]
        network_violation_count = int(network["shift_exceeded_team_count"]) + int(
            network["unavailable_route_leg_count"]
        )
        comparison.append(
            {
                "method_id": method_id,
                "method_group": "baseline",
                "assigned_task_count": int(metrics["assigned_task_count"]),
                "unassigned_task_count": int(
                    metrics["unassigned_candidate_task_count"]
                ),
                "risk_weighted_coverage_ratio": float(
                    metrics["risk_weighted_coverage_ratio"]
                ),
                "high_priority_unassigned_count": int(
                    metrics["high_priority_unassigned_count"]
                ),
                "network_total_travel_minutes": float(
                    network["network_total_travel_minutes"]
                ),
                "maximum_team_elapsed_minutes": float(
                    network["maximum_team_elapsed_minutes"]
                ),
                "shift_exceeded_team_count": int(
                    network["shift_exceeded_team_count"]
                ),
                "unavailable_route_leg_count": int(
                    network["unavailable_route_leg_count"]
                ),
                "network_constraint_violation_count": network_violation_count,
            }
        )
    for method_id in ("safety_first", "balanced_operations"):
        metrics = alternatives[method_id]["metrics"]
        comparison.append(
            {
                "method_id": method_id,
                "method_group": "optimized",
                "assigned_task_count": int(metrics["assigned_task_count"]),
                "unassigned_task_count": int(metrics["unassigned_task_count"]),
                "risk_weighted_coverage_ratio": float(
                    metrics["risk_weighted_coverage_ratio"]
                ),
                "high_priority_unassigned_count": int(
                    metrics["high_priority_unassigned_count"]
                ),
                "network_total_travel_minutes": float(
                    metrics["network_total_travel_minutes"]
                ),
                "maximum_team_elapsed_minutes": float(
                    metrics["maximum_team_elapsed_minutes"]
                ),
                "shift_exceeded_team_count": 0,
                "unavailable_route_leg_count": 0,
                "network_constraint_violation_count": int(
                    metrics["constraint_violation_count"]
                ),
            }
        )

    by_method = {row["method_id"]: row for row in comparison}
    nearest = by_method["nearest"]
    improvements = {}
    for method_id in ("safety_first", "balanced_operations"):
        row = by_method[method_id]
        improvements[method_id] = {
            "comparison_method_id": "nearest",
            "network_travel_minutes_reduced": _round(
                nearest["network_total_travel_minutes"]
                - row["network_total_travel_minutes"]
            ),
            "network_travel_reduction_percent": _percent_reduction(
                nearest["network_total_travel_minutes"],
                row["network_total_travel_minutes"],
            ),
            "maximum_team_elapsed_minutes_reduced": _round(
                nearest["maximum_team_elapsed_minutes"]
                - row["maximum_team_elapsed_minutes"]
            ),
            "maximum_team_elapsed_reduction_percent": _percent_reduction(
                nearest["maximum_team_elapsed_minutes"],
                row["maximum_team_elapsed_minutes"],
            ),
            "network_constraint_violations_reduced": int(
                nearest["network_constraint_violation_count"]
                - row["network_constraint_violation_count"]
            ),
        }

    benchmark_payload = dict(benchmark or {})
    failed_checks: list[str] = []
    if any(
        by_method[method_id]["network_constraint_violation_count"] != 0
        for method_id in ("safety_first", "balanced_operations")
    ):
        failed_checks.append("optimized_plan_constraint_integrity")
    if benchmark_payload and not benchmark_payload.get("deterministic_outputs"):
        failed_checks.append("optimizer_repeat_determinism")
    successful_runs = benchmark_payload.get("successful_run_count")
    repeat_count = benchmark_payload.get("repeat_count")
    if benchmark_payload and successful_runs != repeat_count:
        failed_checks.append("optimizer_repeat_success")

    status = "fail" if failed_checks else "pass"
    result = {
        "schema_version": 1,
        "evaluation_version": EVALUATION_VERSION,
        "scenario_id": optimized_allocation.get("scenario_id"),
        "status": status,
        "metric_semantics": {
            "travel_time": travel_time_matrix.get("route_semantics"),
            "constraint_violation": (
                "shift_exceeded_team_count plus unavailable_route_leg_count for "
                "baselines; optimizer hard-constraint violations for alternatives"
            ),
        },
        "comparison": comparison,
        "improvements_vs_nearest": improvements,
        "optimizer_benchmark": benchmark_payload,
    }
    report = {
        "schema_version": 1,
        "evaluation_version": EVALUATION_VERSION,
        "status": status,
        "method_count": len(comparison),
        "optimized_method_count": 2,
        "failed_checks": failed_checks,
    }
    return result, report
