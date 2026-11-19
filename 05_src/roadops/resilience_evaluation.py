"""Evaluate RoadOps fail-safe recovery policies with deterministic fault injection.

실시간 API·신선도·도로 링크·최적화·설명 장애가 안전 상태로 전환되는지 평가합니다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence


EVALUATION_VERSION = "roadops-resilience-evaluation-v0.1"
FAULT_INJECTION_SEMANTICS = (
    "controlled_fault_injection_not_observed_production_incidents"
)
ACCEPTABLE_CACHE_QUALITY = {"pass", "pass_with_limitations"}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _base_decision(
    *,
    failure_type: str,
    safe_state: str,
    recovery_action: str,
    ranking_allowed: bool,
    allocation_allowed: bool,
) -> dict[str, Any]:
    return {
        "failure_type": failure_type,
        "safe_state": safe_state,
        "recovery_action": recovery_action,
        "ranking_allowed": ranking_allowed,
        "allocation_allowed": allocation_allowed,
        "automatic_dispatch_allowed": False,
        "manual_approval_required": True,
        "failed_value_imputed_as_zero": False,
        "decision_reason": None,
        "recovery_evidence": {},
    }


def build_deterministic_explanation(
    structured_result: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build a bounded explanation only from validated structured tool results."""

    final_response = structured_result.get("final_response")
    if not isinstance(final_response, Mapping):
        return None
    alternatives = final_response.get("alternatives")
    warnings = final_response.get("warnings")
    if not isinstance(alternatives, list) or not alternatives:
        return None
    if not isinstance(warnings, list):
        return None

    bounded_alternatives = []
    required_fields = (
        "alternative_id",
        "assigned_task_count",
        "unassigned_task_count",
        "risk_weighted_coverage_ratio",
        "network_total_travel_minutes",
        "constraint_violation_count",
    )
    for alternative in alternatives:
        if not isinstance(alternative, Mapping):
            return None
        if any(field not in alternative for field in required_fields):
            return None
        bounded_alternatives.append(
            {field: alternative[field] for field in required_fields}
        )

    return {
        "template_id": "validated_tool_result_fallback_v0_1",
        "summary": str(final_response.get("summary") or ""),
        "alternative_count": len(bounded_alternatives),
        "alternatives": bounded_alternatives,
        "warnings": [str(item) for item in warnings],
        "manual_approval_required": True,
        "generation_semantics": "deterministic_copy_from_validated_tool_results",
    }


def decide_failure_recovery(
    failure_type: str,
    payload: Mapping[str, Any],
    *,
    evaluated_at: datetime,
    cache_max_age_minutes: float = 120.0,
) -> dict[str, Any]:
    """Return the fail-safe state for one injected failure."""

    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    if cache_max_age_minutes <= 0:
        raise ValueError("cache_max_age_minutes must be positive")

    if failure_type == "live_api_failure":
        cached_at = _parse_timestamp(payload.get("cached_at"))
        cache_age_minutes = None
        if cached_at is not None:
            cache_age_minutes = (
                evaluated_at - cached_at.astimezone(evaluated_at.tzinfo)
            ).total_seconds() / 60.0
        cache_quality_status = str(payload.get("cache_quality_status") or "")
        critical_quality_failure = bool(payload.get("critical_quality_failure"))
        cache_usable = (
            bool(payload.get("cache_available"))
            and cached_at is not None
            and cache_age_minutes is not None
            and cache_age_minutes >= 0
            and cache_age_minutes <= cache_max_age_minutes
            and cache_quality_status in ACCEPTABLE_CACHE_QUALITY
            and not critical_quality_failure
        )
        if cache_usable:
            decision = _base_decision(
                failure_type=failure_type,
                safe_state="degraded",
                recovery_action="cache_replay",
                ranking_allowed=True,
                allocation_allowed=True,
            )
            decision["decision_reason"] = "live_failed_but_reviewed_cache_is_usable"
            decision["recovery_evidence"] = {
                "source_mode": "cache_replay",
                "cached_at": cached_at.isoformat(),
                "cache_age_minutes": round(cache_age_minutes, 3),
                "cache_max_age_minutes": cache_max_age_minutes,
                "cache_quality_status": cache_quality_status,
                "live_status_claim_allowed": False,
            }
            return decision

        decision = _base_decision(
            failure_type=failure_type,
            safe_state="hold",
            recovery_action="await_fresh_data",
            ranking_allowed=False,
            allocation_allowed=False,
        )
        decision["decision_reason"] = "live_failed_and_no_usable_cache"
        decision["recovery_evidence"] = {
            "source_mode": "unavailable",
            "cache_available": bool(payload.get("cache_available")),
            "cache_age_minutes": (
                round(cache_age_minutes, 3)
                if cache_age_minutes is not None
                else None
            ),
            "cache_max_age_minutes": cache_max_age_minutes,
            "cache_quality_status": cache_quality_status or None,
        }
        return decision

    if failure_type == "stale_data":
        observed_at = _parse_timestamp(payload.get("observed_at"))
        age_minutes = None
        if observed_at is not None:
            age_minutes = max(
                0.0,
                (evaluated_at - observed_at.astimezone(evaluated_at.tzinfo))
                .total_seconds()
                / 60.0,
            )
        maximum_age = float(payload.get("maximum_age_minutes", 0.0))
        is_stale = observed_at is None or maximum_age <= 0 or (
            age_minutes is not None and age_minutes > maximum_age
        )
        if not is_stale:
            raise ValueError("stale_data scenario must inject an expired timestamp")
        decision = _base_decision(
            failure_type=failure_type,
            safe_state="hold",
            recovery_action="refresh_or_manual_review",
            ranking_allowed=False,
            allocation_allowed=False,
        )
        decision["decision_reason"] = "data_freshness_threshold_exceeded"
        decision["recovery_evidence"] = {
            "observed_at": observed_at.isoformat() if observed_at else None,
            "age_minutes": round(age_minutes, 3) if age_minutes is not None else None,
            "maximum_age_minutes": maximum_age,
            "risk_score_available": False,
        }
        return decision

    if failure_type == "unknown_road_link":
        candidate_link_id = str(payload.get("candidate_link_id") or "")
        reference_link_ids = {
            str(item) for item in payload.get("reference_link_ids", []) if item
        }
        if candidate_link_id and candidate_link_id in reference_link_ids:
            raise ValueError("unknown_road_link scenario must use a non-reference link")
        decision = _base_decision(
            failure_type=failure_type,
            safe_state="excluded",
            recovery_action="preserve_for_link_review",
            ranking_allowed=False,
            allocation_allowed=False,
        )
        decision["decision_reason"] = "candidate_link_not_in_reference_network"
        decision["recovery_evidence"] = {
            "candidate_link_id": candidate_link_id or None,
            "reference_link_count": len(reference_link_ids),
            "integration_class": "excluded",
            "original_evidence_preserved": True,
            "risk_score_available": False,
        }
        return decision

    if failure_type == "optimizer_infeasible":
        failure_reason = str(
            payload.get("failure_reason") or "no_globally_feasible_plan"
        )
        decision = _base_decision(
            failure_type=failure_type,
            safe_state="hold",
            recovery_action="manual_intervention",
            ranking_allowed=True,
            allocation_allowed=False,
        )
        decision["decision_reason"] = failure_reason
        decision["recovery_evidence"] = {
            "plan_available": False,
            "hard_constraints_relaxed": False,
            "unassigned_reason_visible": True,
        }
        return decision

    if failure_type == "explanation_generation_failure":
        tool_results_valid = bool(payload.get("tool_results_valid"))
        structured_result = payload.get("structured_result")
        fallback = (
            build_deterministic_explanation(structured_result)
            if tool_results_valid and isinstance(structured_result, Mapping)
            else None
        )
        if fallback is None:
            decision = _base_decision(
                failure_type=failure_type,
                safe_state="hold",
                recovery_action="manual_explanation_review",
                ranking_allowed=False,
                allocation_allowed=False,
            )
            decision["decision_reason"] = "validated_tool_results_unavailable"
            decision["recovery_evidence"] = {
                "fallback_explanation_available": False,
            }
            return decision

        decision = _base_decision(
            failure_type=failure_type,
            safe_state="degraded",
            recovery_action="deterministic_explanation_fallback",
            ranking_allowed=True,
            allocation_allowed=True,
        )
        decision["decision_reason"] = "generator_failed_but_tool_results_are_valid"
        decision["recovery_evidence"] = {
            "fallback_explanation_available": True,
            "fallback_explanation": fallback,
        }
        return decision

    raise ValueError(f"Unsupported failure_type: {failure_type}")


def _evaluation_fingerprint(scenarios: Sequence[Mapping[str, Any]]) -> str:
    stable = [
        {
            "scenario_id": row.get("scenario_id"),
            "failure_type": row.get("failure_type"),
            "expected": row.get("expected"),
            "decision": row.get("decision"),
            "checks": row.get("checks"),
        }
        for row in scenarios
    ]
    encoded = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def evaluate_resilience(
    *,
    agent_result: Mapping[str, Any],
    travel_time_matrix: Mapping[str, Any],
    optimized_allocation: Mapping[str, Any],
    risk_rows: Sequence[Mapping[str, Any]],
    reference_link_ids: Sequence[str],
    evaluated_at: datetime,
    cache_max_age_minutes: float = 120.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inject six bounded failures and evaluate their recovery decisions."""

    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")

    final_response = agent_result.get("final_response")
    baseline_valid = (
        agent_result.get("status") in {"pass", "pass_with_limitations"}
        and isinstance(final_response, Mapping)
        and bool(final_response.get("manual_approval_required"))
        and travel_time_matrix.get("status") == "pass"
        and isinstance(travel_time_matrix.get("routes"), list)
        and bool(travel_time_matrix.get("routes"))
        and optimized_allocation.get("status") == "pass"
        and isinstance(optimized_allocation.get("alternatives"), list)
        and bool(optimized_allocation.get("alternatives"))
        and bool(risk_rows)
        and bool(reference_link_ids)
    )

    fresh_cached_at = evaluated_at - timedelta(minutes=30)
    stale_observed_at = evaluated_at - timedelta(
        minutes=cache_max_age_minutes + 1
    )
    injected_link_id = "9999999999"
    while injected_link_id in {str(item) for item in reference_link_ids}:
        injected_link_id = f"9{injected_link_id}"

    definitions = [
        {
            "scenario_id": "api_failure_with_usable_cache",
            "failure_type": "live_api_failure",
            "payload": {
                "cache_available": True,
                "cached_at": fresh_cached_at.isoformat(),
                "cache_quality_status": "pass",
                "critical_quality_failure": False,
            },
            "expected": {
                "safe_state": "degraded",
                "recovery_action": "cache_replay",
            },
        },
        {
            "scenario_id": "api_failure_without_cache",
            "failure_type": "live_api_failure",
            "payload": {
                "cache_available": False,
                "cache_quality_status": None,
            },
            "expected": {
                "safe_state": "hold",
                "recovery_action": "await_fresh_data",
            },
        },
        {
            "scenario_id": "stale_snapshot",
            "failure_type": "stale_data",
            "payload": {
                "observed_at": stale_observed_at.isoformat(),
                "maximum_age_minutes": cache_max_age_minutes,
            },
            "expected": {
                "safe_state": "hold",
                "recovery_action": "refresh_or_manual_review",
            },
        },
        {
            "scenario_id": "unknown_road_link",
            "failure_type": "unknown_road_link",
            "payload": {
                "candidate_link_id": injected_link_id,
                "reference_link_ids": list(reference_link_ids),
            },
            "expected": {
                "safe_state": "excluded",
                "recovery_action": "preserve_for_link_review",
            },
        },
        {
            "scenario_id": "optimizer_infeasible",
            "failure_type": "optimizer_infeasible",
            "payload": {"failure_reason": "no_globally_feasible_plan"},
            "expected": {
                "safe_state": "hold",
                "recovery_action": "manual_intervention",
            },
        },
        {
            "scenario_id": "explanation_generator_failure",
            "failure_type": "explanation_generation_failure",
            "payload": {
                "tool_results_valid": baseline_valid,
                "structured_result": agent_result,
            },
            "expected": {
                "safe_state": "degraded",
                "recovery_action": "deterministic_explanation_fallback",
            },
        },
    ]

    scenarios: list[dict[str, Any]] = []
    failed_checks: list[str] = []
    for definition in definitions:
        decision = decide_failure_recovery(
            definition["failure_type"],
            definition["payload"],
            evaluated_at=evaluated_at,
            cache_max_age_minutes=cache_max_age_minutes,
        )
        expected = definition["expected"]
        checks = {
            "expected_safe_state": decision["safe_state"]
            == expected["safe_state"],
            "expected_recovery_action": decision["recovery_action"]
            == expected["recovery_action"],
            "automatic_dispatch_blocked": not decision[
                "automatic_dispatch_allowed"
            ],
            "manual_approval_required": bool(
                decision["manual_approval_required"]
            ),
            "failed_value_not_imputed_as_zero": not decision[
                "failed_value_imputed_as_zero"
            ],
            "recovery_evidence_present": bool(decision["recovery_evidence"]),
        }
        evidence = decision["recovery_evidence"]
        scenario_id = definition["scenario_id"]
        if scenario_id == "api_failure_with_usable_cache":
            checks.update(
                {
                    "cache_provenance_disclosed": evidence.get("source_mode")
                    == "cache_replay",
                    "cache_age_within_limit": (
                        evidence.get("cache_age_minutes") is not None
                        and evidence["cache_age_minutes"]
                        <= evidence["cache_max_age_minutes"]
                    ),
                    "live_status_not_claimed": evidence.get(
                        "live_status_claim_allowed"
                    )
                    is False,
                }
            )
        elif scenario_id == "api_failure_without_cache":
            checks.update(
                {
                    "ranking_blocked_without_cache": not decision[
                        "ranking_allowed"
                    ],
                    "allocation_blocked_without_cache": not decision[
                        "allocation_allowed"
                    ],
                }
            )
        elif scenario_id == "stale_snapshot":
            checks.update(
                {
                    "stale_age_exceeds_limit": (
                        evidence.get("age_minutes") is not None
                        and evidence["age_minutes"]
                        > evidence["maximum_age_minutes"]
                    ),
                    "stale_risk_score_suppressed": evidence.get(
                        "risk_score_available"
                    )
                    is False,
                }
            )
        elif scenario_id == "unknown_road_link":
            checks.update(
                {
                    "unknown_link_excluded": evidence.get("integration_class")
                    == "excluded",
                    "original_evidence_preserved": evidence.get(
                        "original_evidence_preserved"
                    )
                    is True,
                    "unknown_link_score_suppressed": evidence.get(
                        "risk_score_available"
                    )
                    is False,
                }
            )
        elif scenario_id == "optimizer_infeasible":
            checks.update(
                {
                    "infeasible_plan_suppressed": evidence.get("plan_available")
                    is False,
                    "hard_constraints_not_relaxed": evidence.get(
                        "hard_constraints_relaxed"
                    )
                    is False,
                    "unassigned_reason_visible": evidence.get(
                        "unassigned_reason_visible"
                    )
                    is True,
                }
            )
        elif scenario_id == "explanation_generator_failure":
            fallback = evidence.get("fallback_explanation")
            checks.update(
                {
                    "fallback_explanation_available": evidence.get(
                        "fallback_explanation_available"
                    )
                    is True,
                    "fallback_uses_validated_tool_results": (
                        isinstance(fallback, Mapping)
                        and fallback.get("generation_semantics")
                        == "deterministic_copy_from_validated_tool_results"
                    ),
                    "fallback_still_requires_approval": (
                        isinstance(fallback, Mapping)
                        and fallback.get("manual_approval_required") is True
                    ),
                }
            )
        scenario_status = "pass" if all(checks.values()) else "fail"
        if scenario_status == "fail":
            failed_checks.extend(
                f"{definition['scenario_id']}:{check_name}"
                for check_name, passed in checks.items()
                if not passed
            )
        scenarios.append(
            {
                "scenario_id": definition["scenario_id"],
                "failure_type": definition["failure_type"],
                "status": scenario_status,
                "expected": expected,
                "decision": decision,
                "checks": checks,
            }
        )

    if not baseline_valid:
        failed_checks.append("baseline_artifacts_valid_for_fault_injection")
    status = "pass" if not failed_checks else "fail"
    result = {
        "schema_version": 1,
        "evaluation_version": EVALUATION_VERSION,
        "evaluated_at": evaluated_at.isoformat(),
        "status": status,
        "scenario_semantics": FAULT_INJECTION_SEMANTICS,
        "baseline_summary": {
            "valid_for_fault_injection": baseline_valid,
            "agent_status": agent_result.get("status"),
            "agent_manual_approval_required": (
                final_response.get("manual_approval_required")
                if isinstance(final_response, Mapping)
                else None
            ),
            "risk_row_count": len(risk_rows),
            "reference_link_count": len(set(map(str, reference_link_ids))),
            "travel_route_count": len(travel_time_matrix.get("routes", [])),
            "optimized_alternative_count": len(
                optimized_allocation.get("alternatives", [])
            ),
        },
        "policy_invariants": {
            "automatic_dispatch_requires_human_approval": True,
            "unknown_or_failed_values_are_not_zero": True,
            "cache_replay_must_disclose_provenance_and_age": True,
            "hard_constraints_are_not_silently_relaxed": True,
            "explanation_fallback_uses_validated_tool_results_only": True,
        },
        "scenarios": scenarios,
    }
    result["evaluation_fingerprint"] = _evaluation_fingerprint(scenarios)
    check_count = sum(len(row["checks"]) for row in scenarios) + 1
    passed_check_count = check_count - len(failed_checks)
    report = {
        "schema_version": 1,
        "evaluation_version": EVALUATION_VERSION,
        "status": status,
        "scenario_count": len(scenarios),
        "passed_scenario_count": sum(
            row["status"] == "pass" for row in scenarios
        ),
        "check_count": check_count,
        "passed_check_count": passed_check_count,
        "failed_checks": failed_checks,
        "evaluation_fingerprint": result["evaluation_fingerprint"],
    }
    return result, report
