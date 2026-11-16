from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from roadops.resilience_evaluation import (
    build_deterministic_explanation,
    decide_failure_recovery,
    evaluate_resilience,
)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _alternative(alternative_id: str) -> dict:
    return {
        "alternative_id": alternative_id,
        "assigned_task_count": 2,
        "unassigned_task_count": 0,
        "risk_weighted_coverage_ratio": 1.0,
        "network_total_travel_minutes": 20.5,
        "constraint_violation_count": 0,
    }


def _agent_result() -> dict:
    return {
        "status": "pass_with_limitations",
        "final_response": {
            "summary": "2개의 대안을 생성했습니다.",
            "alternatives": [
                _alternative("safety_first"),
                _alternative("balanced_operations"),
            ],
            "warnings": ["실시간 ETA가 아닙니다."],
            "manual_approval_required": True,
        },
    }


def _evaluation_inputs() -> dict:
    return {
        "agent_result": _agent_result(),
        "travel_time_matrix": {"status": "pass", "routes": [{"id": "r1"}]},
        "optimized_allocation": {
            "status": "pass",
            "alternatives": [{"alternative_id": "safety_first"}],
        },
        "risk_rows": [{"event_id": "e1", "risk_score": "50"}],
        "reference_link_ids": ["4050000001", "4050000002"],
        "evaluated_at": NOW,
    }


def test_live_failure_uses_only_fresh_reviewed_cache():
    decision = decide_failure_recovery(
        "live_api_failure",
        {
            "cache_available": True,
            "cached_at": (NOW - timedelta(minutes=30)).isoformat(),
            "cache_quality_status": "pass_with_limitations",
            "critical_quality_failure": False,
        },
        evaluated_at=NOW,
        cache_max_age_minutes=120,
    )

    assert decision["safe_state"] == "degraded"
    assert decision["recovery_action"] == "cache_replay"
    assert decision["recovery_evidence"]["cache_age_minutes"] == 30
    assert decision["recovery_evidence"]["live_status_claim_allowed"] is False
    assert decision["automatic_dispatch_allowed"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"cache_available": False},
        {
            "cache_available": True,
            "cached_at": (NOW - timedelta(minutes=121)).isoformat(),
            "cache_quality_status": "pass",
        },
        {
            "cache_available": True,
            "cached_at": (NOW - timedelta(minutes=30)).isoformat(),
            "cache_quality_status": "fail",
        },
        {
            "cache_available": True,
            "cached_at": (NOW - timedelta(minutes=30)).isoformat(),
            "cache_quality_status": "pass",
            "critical_quality_failure": True,
        },
        {
            "cache_available": True,
            "cached_at": (NOW + timedelta(minutes=1)).isoformat(),
            "cache_quality_status": "pass",
        },
    ],
)
def test_live_failure_without_usable_cache_holds(payload):
    decision = decide_failure_recovery(
        "live_api_failure",
        payload,
        evaluated_at=NOW,
        cache_max_age_minutes=120,
    )

    assert decision["safe_state"] == "hold"
    assert decision["ranking_allowed"] is False
    assert decision["allocation_allowed"] is False
    assert decision["failed_value_imputed_as_zero"] is False


def test_stale_unknown_link_and_optimizer_failure_use_distinct_safe_states():
    stale = decide_failure_recovery(
        "stale_data",
        {
            "observed_at": (NOW - timedelta(minutes=121)).isoformat(),
            "maximum_age_minutes": 120,
        },
        evaluated_at=NOW,
    )
    unknown_link = decide_failure_recovery(
        "unknown_road_link",
        {
            "candidate_link_id": "9999999999",
            "reference_link_ids": ["4050000001"],
        },
        evaluated_at=NOW,
    )
    infeasible = decide_failure_recovery(
        "optimizer_infeasible",
        {"failure_reason": "no_globally_feasible_plan"},
        evaluated_at=NOW,
    )

    assert stale["safe_state"] == "hold"
    assert stale["recovery_evidence"]["risk_score_available"] is False
    assert unknown_link["safe_state"] == "excluded"
    assert unknown_link["recovery_evidence"]["original_evidence_preserved"] is True
    assert infeasible["safe_state"] == "hold"
    assert infeasible["recovery_evidence"]["hard_constraints_relaxed"] is False


def test_explanation_fallback_copies_only_structured_result_fields():
    agent_result = _agent_result()
    fallback = build_deterministic_explanation(agent_result)

    assert fallback is not None
    assert fallback["summary"] == agent_result["final_response"]["summary"]
    assert fallback["alternative_count"] == 2
    assert fallback["alternatives"][0] == _alternative("safety_first")
    assert fallback["manual_approval_required"] is True
    assert fallback["generation_semantics"] == (
        "deterministic_copy_from_validated_tool_results"
    )


def test_explanation_failure_holds_when_tool_results_are_invalid():
    decision = decide_failure_recovery(
        "explanation_generation_failure",
        {"tool_results_valid": False, "structured_result": {}},
        evaluated_at=NOW,
    )

    assert decision["safe_state"] == "hold"
    assert decision["recovery_action"] == "manual_explanation_review"
    assert decision["recovery_evidence"]["fallback_explanation_available"] is False


def test_resilience_evaluation_passes_six_scenarios_deterministically():
    first, first_report = evaluate_resilience(**_evaluation_inputs())
    second, second_report = evaluate_resilience(**_evaluation_inputs())

    assert first_report["status"] == "pass"
    assert first_report["scenario_count"] == 6
    assert first_report["passed_scenario_count"] == 6
    assert first_report["check_count"] == 53
    assert first_report["failed_checks"] == []
    assert all(row["status"] == "pass" for row in first["scenarios"])
    assert first["evaluation_fingerprint"] == second["evaluation_fingerprint"]
    assert first_report["evaluation_fingerprint"] == second_report[
        "evaluation_fingerprint"
    ]


def test_resilience_evaluation_fails_closed_on_invalid_baseline():
    inputs = _evaluation_inputs()
    invalid_agent = deepcopy(inputs["agent_result"])
    invalid_agent["final_response"]["manual_approval_required"] = False
    inputs["agent_result"] = invalid_agent

    result, report = evaluate_resilience(**inputs)

    assert report["status"] == "fail"
    assert "baseline_artifacts_valid_for_fault_injection" in report["failed_checks"]
    explanation_case = next(
        row
        for row in result["scenarios"]
        if row["scenario_id"] == "explanation_generator_failure"
    )
    assert explanation_case["decision"]["safe_state"] == "hold"
    assert explanation_case["status"] == "fail"


def test_stale_scenario_rejects_fresh_timestamp():
    with pytest.raises(ValueError, match="expired timestamp"):
        decide_failure_recovery(
            "stale_data",
            {
                "observed_at": (NOW - timedelta(minutes=30)).isoformat(),
                "maximum_age_minutes": 120,
            },
            evaluated_at=NOW,
        )
