#!/usr/bin/env python3
"""Run the seven-step RoadOps Agent flow from one Korean request.

한 문장으로 품질검사부터 설명까지 실행하고 로그를 남깁니다.
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
DEFAULT_DEMO_DIR = PROJECT_ROOT / "demo/cached_inputs_v0_1"

from roadops.agent_flow import run_agent_flow  # noqa: E402
from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import load_records  # noqa: E402


DEFAULT_REQUEST = (
    "팀 3개와 차량 3대로 2시간 안에 현재 위험 기준 순찰계획을 만들어줘. "
    "안전 우선과 업무 균형을 비교해줘."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument(
        "--resources",
        type=Path,
        default=PROJECT_ROOT / "config/resource_scenarios/demo_three_teams_v0_1.json",
    )
    parser.add_argument(
        "--risk-forecasts",
        type=Path,
        default=DEFAULT_DEMO_DIR / "risk_forecasts.csv",
    )
    parser.add_argument(
        "--integrated-events",
        type=Path,
        default=DEFAULT_DEMO_DIR / "integrated_field_events.csv",
    )
    parser.add_argument(
        "--risk-quality",
        type=Path,
        default=DEFAULT_DEMO_DIR / "risk_quality_report.json",
    )
    parser.add_argument(
        "--event-quality",
        type=Path,
        default=DEFAULT_DEMO_DIR / "event_quality_report.json",
    )
    parser.add_argument(
        "--travel-time-matrix",
        type=Path,
        default=DEFAULT_DEMO_DIR / "travel_time_matrix.json",
    )
    parser.add_argument(
        "--travel-quality",
        type=Path,
        default=DEFAULT_DEMO_DIR / "travel_quality_report.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/agent_flow_v0_1",
    )
    parser.add_argument(
        "--execution-mode",
        choices=("cached_demo", "prepared_inputs"),
        default="cached_demo",
    )
    parser.add_argument("--as-of", default=None)
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


def _generated_at(raw: str | None) -> str:
    if raw is None:
        return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul")).isoformat()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    resources = _read(args.resources)
    forecasts = load_records(args.risk_forecasts)
    events = load_records(args.integrated_events)
    travel_matrix = _read(args.travel_time_matrix)
    quality_reports = {
        "integrated_events": _read(args.event_quality),
        "risk_forecasts": _read(args.risk_quality),
        "travel_time_matrix": _read(args.travel_quality),
    }
    result, report = run_agent_flow(
        args.request,
        resources,
        forecasts,
        events,
        travel_matrix,
        quality_reports,
        execution_mode=args.execution_mode,
    )
    generated_at = _generated_at(args.as_of)
    result["generated_at"] = generated_at
    report["generated_at"] = generated_at
    result_path = args.output_dir / "agent_result.json"
    report_path = args.output_dir / "quality_report.json"
    trace_path = args.output_dir / "tool_trace.jsonl"
    report["inputs"] = {
        "resources": _relative(args.resources),
        "risk_forecasts": _relative(args.risk_forecasts),
        "integrated_events": _relative(args.integrated_events),
        "travel_time_matrix": _relative(args.travel_time_matrix),
        "risk_quality": _relative(args.risk_quality),
        "event_quality": _relative(args.event_quality),
        "travel_quality": _relative(args.travel_quality),
    }
    report["outputs"] = {
        "agent_result": _relative(result_path),
        "quality_report": _relative(report_path),
        "tool_trace": _relative(trace_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)
    _write_jsonl(trace_path, list(result.get("tool_trace", [])))

    print(
        json.dumps(
            {
                "status": result["status"],
                "run_id": result["run_id"],
                "request": result["request_text"],
                "completed_tool_count": report["completed_tool_count"],
                "tool_statuses": report.get("tool_statuses", {}),
                "final_response": result["final_response"],
                "failed_checks": report.get("failed_checks", []),
                "output": _relative(result_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
