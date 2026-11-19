#!/usr/bin/env python3
"""Build RoadOps risk-first and nearest patrol-allocation baselines.

자원 시나리오와 위험 작업을 결합해 위험순·최근접 기준선 배분을 생성합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.allocation_baselines import build_allocation_baselines  # noqa: E402
from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import load_records  # noqa: E402


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
        "--risk-forecasts",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/risk_forecasts_v0_1/risk_forecasts.csv"
        ),
    )
    parser.add_argument(
        "--integrated-events",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/integrated_field_events_v0_1/integrated_field_events.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/allocation_baselines_v0_1",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def main() -> int:
    args = parse_args()
    for path in (args.resources, args.risk_forecasts, args.integrated_events):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {_relative(path)}")

    with args.resources.open(encoding="utf-8") as handle:
        resource_payload = json.load(handle)
    forecasts = load_records(args.risk_forecasts)
    events = load_records(args.integrated_events)
    result, report = build_allocation_baselines(
        resource_payload,
        forecasts,
        events,
    )

    result_path = args.output_dir / "allocation_baselines.json"
    report_path = args.output_dir / "quality_report.json"
    report["inputs"] = {
        "resources": _relative(args.resources),
        "risk_forecasts": _relative(args.risk_forecasts),
        "integrated_events": _relative(args.integrated_events),
    }
    report["outputs"] = {
        "allocation_baselines": _relative(result_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "scenario_id": result.get("scenario_id"),
        "horizon_hours": result.get("planning", {}).get("horizon_hours"),
        "task_build": report.get("task_build"),
        "comparison": result.get("comparison", {}),
        "failed_checks": report.get("failed_checks", []),
        "output": _relative(result_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
