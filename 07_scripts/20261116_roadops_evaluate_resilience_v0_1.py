#!/usr/bin/env python3
"""Run RoadOps v0.1 fail-safe recovery fault-injection evaluation.

RoadOps v0.1의 장애·복구 안전 정책을 통제된 장애 주입으로 평가합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.resilience_evaluation import evaluate_resilience  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent-result",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/agent_flow_v0_1/agent_result.json",
    )
    parser.add_argument(
        "--travel-time-matrix",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/travel_time_matrix_v0_1/travel_time_matrix.json",
    )
    parser.add_argument(
        "--optimized-allocation",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/optimized_allocation_v0_1/optimized_allocation.json",
    )
    parser.add_argument(
        "--risk-scores",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_scores_v0_1/risk_scores.csv",
    )
    parser.add_argument(
        "--road-reference",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/taas_coverage_audit_v0_1/road_risk_features_v0_1.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/resilience_evaluation_v0_1",
    )
    parser.add_argument(
        "--evaluated-at",
        help="Timezone-aware ISO 8601 timestamp; defaults to the current local time.",
    )
    parser.add_argument("--cache-max-age-minutes", type=float, default=120.0)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read_json(path: Path):
    if not path.exists():
        raise SystemExit(f"Required input is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Required input is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_evaluated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now().astimezone()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid --evaluated-at value: {value}") from exc
    if parsed.tzinfo is None:
        raise SystemExit("--evaluated-at must include a timezone offset")
    return parsed


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def main() -> int:
    args = parse_args()
    agent_result = _read_json(args.agent_result)
    travel_time_matrix = _read_json(args.travel_time_matrix)
    optimized_allocation = _read_json(args.optimized_allocation)
    risk_rows = _read_csv(args.risk_scores)
    road_rows = _read_csv(args.road_reference)
    reference_link_ids = sorted(
        {
            str(row.get("link_id") or "").strip()
            for row in road_rows
            if str(row.get("link_id") or "").strip()
        }
    )
    result, report = evaluate_resilience(
        agent_result=agent_result,
        travel_time_matrix=travel_time_matrix,
        optimized_allocation=optimized_allocation,
        risk_rows=risk_rows,
        reference_link_ids=reference_link_ids,
        evaluated_at=_parse_evaluated_at(args.evaluated_at),
        cache_max_age_minutes=args.cache_max_age_minutes,
    )

    result_path = args.output_dir / "resilience_evaluation.json"
    report_path = args.output_dir / "quality_report.json"
    report["inputs"] = {
        "agent_result": _relative(args.agent_result),
        "travel_time_matrix": _relative(args.travel_time_matrix),
        "optimized_allocation": _relative(args.optimized_allocation),
        "risk_scores": _relative(args.risk_scores),
        "road_reference": _relative(args.road_reference),
    }
    report["outputs"] = {
        "resilience_evaluation": _relative(result_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)

    print(
        json.dumps(
            {
                "status": report["status"],
                "scenario_count": report["scenario_count"],
                "passed_scenario_count": report["passed_scenario_count"],
                "check_count": report["check_count"],
                "passed_check_count": report["passed_check_count"],
                "failed_checks": report["failed_checks"],
                "evaluation_fingerprint": report["evaluation_fingerprint"],
                "output": _relative(result_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
