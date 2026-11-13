from __future__ import annotations

from roadops.allocation_evaluation import (
    benchmark_allocation,
    evaluate_allocations,
)


def _baseline(strategy, travel=10.0):
    return {
        "strategy": strategy,
        "metrics": {
            "assigned_task_count": 2,
            "unassigned_candidate_task_count": 0,
            "risk_weighted_coverage_ratio": 1.0,
            "high_priority_unassigned_count": 0,
            "total_estimated_travel_minutes": travel,
        },
    }


def _network(strategy, travel, elapsed, exceeded):
    return {
        "strategy": strategy,
        "network_total_travel_minutes": travel,
        "maximum_team_elapsed_minutes": elapsed,
        "shift_exceeded_team_count": exceeded,
        "unavailable_route_leg_count": 0,
    }


def _alternative(alternative_id, travel, elapsed, violations=0):
    return {
        "alternative_id": alternative_id,
        "plan_fingerprint": alternative_id,
        "metrics": {
            "assigned_task_count": 2,
            "unassigned_task_count": 0,
            "risk_weighted_coverage_ratio": 1.0,
            "high_priority_unassigned_count": 0,
            "network_total_travel_minutes": travel,
            "maximum_team_elapsed_minutes": elapsed,
            "constraint_violation_count": violations,
        },
    }


def _inputs():
    baselines = {
        "plans": [_baseline("risk_first"), _baseline("nearest")]
    }
    matrix = {
        "route_semantics": "test_network_time",
        "allocation_baseline_recheck": [
            _network("risk_first", 120, 130, 1),
            _network("nearest", 100, 125, 1),
        ],
    }
    optimized = {
        "scenario_id": "test",
        "alternatives": [
            _alternative("safety_first", 75, 90),
            _alternative("balanced_operations", 80, 85),
        ],
    }
    return baselines, matrix, optimized


def test_evaluation_compares_all_methods_on_network_metrics():
    result, report = evaluate_allocations(*_inputs())

    assert report["status"] == "pass"
    assert [row["method_id"] for row in result["comparison"]] == [
        "risk_first",
        "nearest",
        "safety_first",
        "balanced_operations",
    ]
    safety = result["improvements_vs_nearest"]["safety_first"]
    assert safety["network_travel_minutes_reduced"] == 25
    assert safety["network_travel_reduction_percent"] == 25.0
    assert safety["network_constraint_violations_reduced"] == 1


def test_evaluation_fails_when_required_method_is_missing():
    baselines, matrix, optimized = _inputs()
    optimized["alternatives"] = optimized["alternatives"][:1]

    result, report = evaluate_allocations(baselines, matrix, optimized)

    assert result["failure_reason"] == "required_evaluation_inputs_missing"
    assert report["status"] == "fail"
    assert "optimized:balanced_operations" in result["missing_inputs"]


def test_benchmark_reports_repeat_determinism():
    result = {
        "alternatives": [
            _alternative("safety_first", 75, 90),
            _alternative("balanced_operations", 80, 85),
        ]
    }

    benchmark = benchmark_allocation(
        lambda: (result, {"status": "pass"}), repeats=3
    )

    assert benchmark["repeat_count"] == 3
    assert benchmark["successful_run_count"] == 3
    assert benchmark["deterministic_outputs"] is True
    assert benchmark["unique_plan_fingerprint_count"] == 1
