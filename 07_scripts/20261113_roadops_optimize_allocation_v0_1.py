#!/usr/bin/env python3
"""Build two constraint-feasible RoadOps allocation alternatives.

자원·현장·도로망 이동시간을 결합해 안전 우선·업무 균형 배분안을 생성합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.allocation_optimizer import build_constraint_allocation  # noqa: E402
from roadops.cits_snapshot import write_json_atomic  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resources",
        type=Path,
        default=(
            PROJECT_ROOT
            / "config/resource_scenarios/demo_three_teams_v0_1.json"
        ),
    )
    parser.add_argument(
        "--allocation-baselines",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/allocation_baselines_v0_1/allocation_baselines.json"
        ),
    )
    parser.add_argument(
        "--travel-time-matrix",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/travel_time_matrix_v0_1/travel_time_matrix.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/optimized_allocation_v0_1",
    )
    parser.add_argument("--balanced-min-safety-ratio", type=float, default=0.95)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _generated_at(value: str | None) -> str:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul")).isoformat()


def _read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    args = parse_args()
    for path in (
        args.resources,
        args.allocation_baselines,
        args.travel_time_matrix,
    ):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {_relative(path)}")

    resources = _read_json(args.resources)
    baselines = _read_json(args.allocation_baselines)
    travel_matrix = _read_json(args.travel_time_matrix)
    result, report = build_constraint_allocation(
        resources,
        baselines.get("field_tasks", []),
        travel_matrix,
        balanced_min_safety_ratio=args.balanced_min_safety_ratio,
    )
    result["generated_at"] = _generated_at(args.as_of)
    result["baseline_network_recheck"] = travel_matrix.get(
        "allocation_baseline_recheck", []
    )
    report["inputs"] = {
        "resources": _relative(args.resources),
        "allocation_baselines": _relative(args.allocation_baselines),
        "travel_time_matrix": _relative(args.travel_time_matrix),
    }
    result_path = args.output_dir / "optimized_allocation.json"
    report_path = args.output_dir / "quality_report.json"
    report["outputs"] = {
        "optimized_allocation": _relative(result_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "scenario_id": result.get("scenario_id"),
        "solver": result.get("solver"),
        "route_option_counts": report.get("route_option_counts"),
        "alternatives": [
            {
                "alternative_id": plan["alternative_id"],
                **plan["metrics"],
            }
            for plan in result.get("alternatives", [])
        ],
        "baseline_network_recheck": result.get("baseline_network_recheck", []),
        "failed_checks": report.get("failed_checks", []),
        "output": _relative(result_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
