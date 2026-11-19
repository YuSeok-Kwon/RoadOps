#!/usr/bin/env python3
"""Compare RoadOps baselines and optimized allocation alternatives.

위험순·최근접·안전 우선·업무 균형 배분을 같은 도로망 지표로 평가합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.allocation_evaluation import (  # noqa: E402
    benchmark_allocation,
    evaluate_allocations,
)
from roadops.allocation_optimizer import build_constraint_allocation  # noqa: E402
from roadops.cits_snapshot import write_json_atomic  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resources",
        type=Path,
        default=PROJECT_ROOT / "config/resource_scenarios/demo_three_teams_v0_1.json",
    )
    parser.add_argument(
        "--allocation-baselines",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/allocation_baselines_v0_1/allocation_baselines.json",
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
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/allocation_evaluation_v0_1",
    )
    parser.add_argument("--benchmark-repeats", type=int, default=10)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read(path: Path):
    if not path.exists():
        raise SystemExit(f"Required input is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def main() -> int:
    args = parse_args()
    resources = _read(args.resources)
    baselines = _read(args.allocation_baselines)
    travel_matrix = _read(args.travel_time_matrix)
    optimized = _read(args.optimized_allocation)

    benchmark = benchmark_allocation(
        lambda: build_constraint_allocation(
            resources,
            baselines.get("field_tasks", []),
            travel_matrix,
        ),
        repeats=args.benchmark_repeats,
    )
    result, report = evaluate_allocations(
        baselines,
        travel_matrix,
        optimized,
        benchmark=benchmark,
    )
    result_path = args.output_dir / "allocation_evaluation.json"
    report_path = args.output_dir / "quality_report.json"
    report["inputs"] = {
        "resources": _relative(args.resources),
        "allocation_baselines": _relative(args.allocation_baselines),
        "travel_time_matrix": _relative(args.travel_time_matrix),
        "optimized_allocation": _relative(args.optimized_allocation),
    }
    report["outputs"] = {
        "allocation_evaluation": _relative(result_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "comparison": result.get("comparison", []),
                "improvements_vs_nearest": result.get(
                    "improvements_vs_nearest", {}
                ),
                "optimizer_benchmark": result.get("optimizer_benchmark", {}),
                "failed_checks": report.get("failed_checks", []),
                "output": _relative(result_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
