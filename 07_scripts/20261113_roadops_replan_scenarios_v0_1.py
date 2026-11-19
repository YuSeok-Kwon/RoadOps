#!/usr/bin/env python3
"""Run RoadOps closure and heavy-rain partial replanning scenarios.

통제·폭우에서 완료·고정·비영향 업무를 보존하고 부분 재계획합니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import load_records  # noqa: E402
from roadops.replanning import (  # noqa: E402
    apply_heavy_rain_scenario,
    build_partial_replan,
)
from roadops.travel_time import (  # noqa: E402
    build_travel_time_matrix,
    current_traffic_speeds_by_link,
)


DEFAULT_COMPLETED_TASK = "link:4060438807:h0"
DEFAULT_CLOSED_LINK = "4050005521"
DEFAULT_RAIN_LINKS = ("4050484600", "4050456800")


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
        "--base-allocation",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/optimized_allocation_v0_1/optimized_allocation.json",
    )
    parser.add_argument(
        "--base-travel-matrix",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/travel_time_matrix_v0_1/travel_time_matrix.json",
    )
    parser.add_argument(
        "--nodes",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_nodes.csv",
    )
    parser.add_argument(
        "--links",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv",
    )
    parser.add_argument(
        "--traffic",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/integrated_field_events_v0_1/enrichments/jeju_its_realtime_traffic.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/partial_replanning_v0_1",
    )
    parser.add_argument("--completed-task-id", action="append", default=[])
    parser.add_argument("--closed-link-id", default=DEFAULT_CLOSED_LINK)
    parser.add_argument("--rain-link-id", action="append", default=[])
    parser.add_argument("--rain-priority-delta", type=float, default=15.0)
    parser.add_argument("--rain-service-minutes-delta", type=float, default=10.0)
    parser.add_argument("--rain-travel-time-multiplier", type=float, default=1.25)
    parser.add_argument("--benchmark-repeats", type=int, default=10)
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


def _generated_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def _write_jsonl(path: Path, scenario_results: list[dict]) -> None:
    rows = []
    for scenario_result in scenario_results:
        scenario_type = scenario_result["scenario"]["scenario_type"]
        rows.extend(
            {"scenario_type": scenario_type, **row}
            for row in scenario_result.get("tool_trace", [])
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _benchmark(run_once, repeats: int):
    if repeats < 1:
        raise SystemExit("--benchmark-repeats must be at least 1")
    durations = []
    fingerprints = []
    result = report = None
    for _ in range(repeats):
        started = time.perf_counter()
        result, report = run_once()
        durations.append(time.perf_counter() - started)
        fingerprints.append(
            hashlib.sha256(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
        )
    ordered = sorted(durations)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    benchmark = {
        "repeat_count": repeats,
        "minimum_seconds": round(min(durations), 6),
        "mean_seconds": round(statistics.fmean(durations), 6),
        "median_seconds": round(statistics.median(durations), 6),
        "p95_nearest_rank_seconds": round(ordered[p95_index], 6),
        "maximum_seconds": round(max(durations), 6),
        "unique_result_fingerprint_count": len(set(fingerprints)),
        "deterministic_outputs": len(set(fingerprints)) == 1,
    }
    return result, report, benchmark


def main() -> int:
    args = parse_args()
    resources = _read(args.resources)
    baselines = _read(args.allocation_baselines)
    field_tasks = list(baselines.get("field_tasks", []))
    base_allocation = _read(args.base_allocation)
    base_matrix = _read(args.base_travel_matrix)
    nodes = load_records(args.nodes)
    links = load_records(args.links)
    safety_alternative = next(
        (
            alternative
            for alternative in base_allocation.get("alternatives", [])
            if alternative.get("alternative_id") == "safety_first"
        ),
        {},
    )
    first_assignment = min(
        safety_alternative.get("assignments", []),
        key=lambda row: (int(row.get("sequence") or 0), str(row.get("team_id") or "")),
        default={},
    )
    completed = args.completed_task_id or [
        str(first_assignment.get("task_id") or DEFAULT_COMPLETED_TASK)
    ]
    rain_links = args.rain_link_id or list(DEFAULT_RAIN_LINKS)
    generated_at = _generated_at(args.as_of)
    traffic_speeds: dict[str, float] = {}
    traffic_profile: dict = {"status": "missing_input"}
    if args.traffic.exists():
        traffic_payload = _read(args.traffic)
        traffic_speeds, traffic_profile = current_traffic_speeds_by_link(
            traffic_payload.get("records", []),
            as_of=generated_at,
            freshness_max_minutes=30,
        )
        traffic_profile["status"] = (
            "available" if traffic_speeds else "unavailable_no_fresh_positive_speed"
        )

    closure_started = time.perf_counter()
    closure_matrix, closure_matrix_report = build_travel_time_matrix(
        resources,
        field_tasks,
        nodes,
        links,
        closed_link_ids=[args.closed_link_id],
        observed_speed_by_link=traffic_speeds,
        traffic_profile=traffic_profile,
        generated_at=generated_at,
    )
    closure_matrix_seconds = time.perf_counter() - closure_started
    closure_scenario = {
        "scenario_id": "demo-road-closure-v0.1",
        "scenario_type": "road_closure",
        "reason_code": "road_closure_what_if_injected",
        "semantics": "what_if_not_observed_road_closure",
        "affected_link_ids": [args.closed_link_id],
        "travel_matrix_status": closure_matrix_report["status"],
    }
    closure_result, closure_report, closure_benchmark = _benchmark(
        lambda: build_partial_replan(
            resources,
            field_tasks,
            base_allocation,
            closure_matrix,
            closure_scenario,
            completed_task_ids=completed,
        ),
        args.benchmark_repeats,
    )

    rain_tasks, rain_matrix, rain_scenario = apply_heavy_rain_scenario(
        field_tasks,
        base_matrix,
        affected_link_ids=rain_links,
        priority_delta=args.rain_priority_delta,
        service_minutes_delta=args.rain_service_minutes_delta,
        travel_time_multiplier=args.rain_travel_time_multiplier,
    )
    rain_scenario["scenario_id"] = "demo-heavy-rain-v0.1"
    rain_result, rain_report, rain_benchmark = _benchmark(
        lambda: build_partial_replan(
            resources,
            rain_tasks,
            base_allocation,
            rain_matrix,
            rain_scenario,
            completed_task_ids=completed,
        ),
        args.benchmark_repeats,
    )

    scenario_results = [closure_result, rain_result]
    scenario_reports = [closure_report, rain_report]
    status = (
        "pass"
        if all(report["status"] == "pass" for report in scenario_reports)
        and closure_benchmark["deterministic_outputs"]
        and rain_benchmark["deterministic_outputs"]
        else "fail"
    )
    result = {
        "schema_version": 1,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "base_alternative_id": "safety_first",
        "completed_task_ids": completed,
        "scenario_results": scenario_results,
        "runtime": {
            "road_closure_matrix_build_seconds": round(
                closure_matrix_seconds, 6
            ),
            "road_closure_partial_replan": closure_benchmark,
            "heavy_rain_partial_replan": rain_benchmark,
        },
    }
    report = {
        "schema_version": 1,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "scenario_reports": {
            result["scenario"]["scenario_type"]: scenario_report
            for result, scenario_report in zip(
                scenario_results, scenario_reports
            )
        },
        "failed_checks": [
            result.get("failure_reason")
            for result in scenario_results
            if result.get("status") == "fail"
        ]
        + (
            []
            if closure_benchmark["deterministic_outputs"]
            else ["road_closure_replan_determinism"]
        )
        + (
            []
            if rain_benchmark["deterministic_outputs"]
            else ["heavy_rain_replan_determinism"]
        ),
        "inputs": {
            "resources": _relative(args.resources),
            "allocation_baselines": _relative(args.allocation_baselines),
            "base_allocation": _relative(args.base_allocation),
            "base_travel_matrix": _relative(args.base_travel_matrix),
            "nodes": _relative(args.nodes),
            "links": _relative(args.links),
        },
    }
    result_path = args.output_dir / "replanning_scenarios.json"
    report_path = args.output_dir / "quality_report.json"
    trace_path = args.output_dir / "tool_trace.jsonl"
    report["outputs"] = {
        "replanning_scenarios": _relative(result_path),
        "quality_report": _relative(report_path),
        "tool_trace": _relative(trace_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)
    _write_jsonl(trace_path, scenario_results)

    receipt = {
        "status": status,
        "completed_task_ids": completed,
        "runtime": result["runtime"],
        "scenarios": [
            {
                "scenario_type": scenario_result["scenario"]["scenario_type"],
                "status": scenario_result["status"],
                "affected_team_ids": scenario_result.get("affected_team_ids", []),
                "change_diff": scenario_result.get("change_diff", {}),
                "explanation": scenario_result.get("explanation", {}),
                "failure_reason": scenario_result.get("failure_reason"),
            }
            for scenario_result in scenario_results
        ],
        "failed_checks": report["failed_checks"],
        "output": _relative(result_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
