#!/usr/bin/env python3
"""Build or replay a RoadOps road-network travel-time matrix.

제주 노드·링크망과 통제 링크로 팀·현장 간 이동시간 행렬을 생성하거나 캐시 재생합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import file_sha256, load_records  # noqa: E402
from roadops.resources import validate_resource_plan  # noqa: E402
from roadops.spatial import normalize_link_id  # noqa: E402
from roadops.travel_time import (  # noqa: E402
    build_travel_time_matrix,
    current_traffic_speeds_by_link,
    recheck_allocation_plans,
    replay_cached_travel_matrix,
    travel_matrix_cache_key,
)


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
        "--allocation",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/allocation_baselines_v0_1/allocation_baselines.json"
        ),
    )
    parser.add_argument(
        "--nodes",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_nodes.csv"
        ),
    )
    parser.add_argument(
        "--links",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv"
        ),
    )
    parser.add_argument(
        "--closure-state",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/cits_snapshot_monitor_v0_1/state/jeju_cits_road_close.json"
        ),
    )
    parser.add_argument(
        "--traffic",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/integrated_field_events_v0_1/enrichments/jeju_its_realtime_traffic.json"
        ),
    )
    parser.add_argument(
        "--closed-link-id",
        action="append",
        default=[],
        help="Additional ten-digit link to remove; may be repeated.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/travel_time_matrix_v0_1",
    )
    parser.add_argument("--include-excluded-tasks", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--default-speed-kph", type=float, default=30.0)
    parser.add_argument("--connector-speed-kph", type=float, default=20.0)
    parser.add_argument("--max-snap-distance-meters", type=float, default=2_000.0)
    parser.add_argument("--traffic-freshness-minutes", type=float, default=30.0)
    parser.add_argument("--disable-live-traffic", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _generated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def _active_closure_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    active = payload.get("active_records", {})
    if isinstance(active, Mapping):
        records = active.values()
    elif isinstance(active, list):
        records = active
    else:
        return []
    links: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        link_id = normalize_link_id(record.get("link_id"))
        if link_id:
            links.add(link_id)
    return sorted(links)


def main() -> int:
    args = parse_args()
    for path in (args.resources, args.allocation, args.nodes, args.links):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {_relative(path)}")

    with args.resources.open(encoding="utf-8") as handle:
        resource_payload = json.load(handle)
    with args.allocation.open(encoding="utf-8") as handle:
        allocation = json.load(handle)
    field_tasks = list(allocation.get("field_tasks", []))
    if not field_tasks:
        raise SystemExit("Allocation input contains no field_tasks")

    closure_links = set(_active_closure_links(args.closure_state))
    for raw in args.closed_link_id:
        link_id = normalize_link_id(raw)
        if link_id is None:
            raise SystemExit(f"Invalid --closed-link-id: {raw}")
        closure_links.add(link_id)
    parameters = {
        "include_excluded_tasks": args.include_excluded_tasks,
        "default_speed_kph": args.default_speed_kph,
        "connector_speed_kph": args.connector_speed_kph,
        "max_snap_distance_meters": args.max_snap_distance_meters,
        "traffic_freshness_minutes": args.traffic_freshness_minutes,
        "live_traffic_enabled": not args.disable_live_traffic,
    }
    network_identity = {
        "nodes_sha256": file_sha256(args.nodes),
        "links_sha256": file_sha256(args.links),
    }
    generated_at = _generated_at(args.as_of)
    traffic_speeds: dict[str, float] = {}
    traffic_profile: dict[str, Any] = {
        "status": "disabled" if args.disable_live_traffic else "missing_input",
        "fresh_speed_link_count": 0,
    }
    if not args.disable_live_traffic and args.traffic.exists():
        with args.traffic.open(encoding="utf-8") as handle:
            traffic_payload = json.load(handle)
        traffic_records = (
            traffic_payload.get("records", [])
            if isinstance(traffic_payload, Mapping)
            else []
        )
        traffic_speeds, traffic_profile = current_traffic_speeds_by_link(
            traffic_records,
            as_of=generated_at,
            freshness_max_minutes=args.traffic_freshness_minutes,
        )
        traffic_profile["status"] = (
            "available" if traffic_speeds else "unavailable_no_fresh_positive_speed"
        )
        traffic_profile["source_id"] = "jeju_its_realtime_traffic"
        traffic_profile["source_path"] = _relative(args.traffic)

    network_identity["traffic_sha256"] = (
        file_sha256(args.traffic)
        if not args.disable_live_traffic and args.traffic.exists()
        else None
    )
    parameters["traffic_status"] = traffic_profile.get("status")
    parameters["traffic_as_of_5min"] = generated_at.replace(
        minute=(generated_at.minute // 5) * 5,
        second=0,
        microsecond=0,
    ).isoformat()
    cache_key = travel_matrix_cache_key(
        resource_payload=resource_payload,
        field_tasks=field_tasks,
        network_identity=network_identity,
        closed_link_ids=closure_links,
        parameters=parameters,
    )
    cache_dir = args.output_dir / "cache"
    cache_path = cache_dir / f"{cache_key}.json"

    if cache_path.exists() and not args.refresh_cache:
        with cache_path.open(encoding="utf-8") as handle:
            cached = json.load(handle)
        result, report = replay_cached_travel_matrix(
            cached["result"],
            cache_key=cache_key,
            resource_validation=cached["report"]["resource_validation"],
            graph_report=cached["report"]["graph"],
        )
        cache_status = "hit"
    else:
        nodes = load_records(args.nodes)
        links = load_records(args.links)
        result, report = build_travel_time_matrix(
            resource_payload,
            field_tasks,
            nodes,
            links,
            closed_link_ids=closure_links,
            include_excluded_tasks=args.include_excluded_tasks,
            default_speed_kph=args.default_speed_kph,
            connector_speed_kph=args.connector_speed_kph,
            max_snap_distance_meters=args.max_snap_distance_meters,
            observed_speed_by_link=traffic_speeds,
            traffic_profile=traffic_profile,
            generated_at=generated_at,
        )
        result["execution"]["cache_key"] = cache_key
        cache_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(cache_path, {"result": result, "report": report})
        cache_status = "refresh" if args.refresh_cache else "miss"

    resource_plan, _ = validate_resource_plan(resource_payload)
    baseline_recheck = recheck_allocation_plans(
        allocation.get("plans", []), result, resource_plan
    )
    result["allocation_baseline_recheck"] = baseline_recheck
    report["allocation_baseline_recheck"] = baseline_recheck
    result["execution"]["cache_status"] = cache_status
    result["network_identity"] = network_identity
    report["cache"] = {
        "status": cache_status,
        "key": cache_key,
        "path": _relative(cache_path),
    }
    report["inputs"] = {
        "resources": _relative(args.resources),
        "allocation": _relative(args.allocation),
        "nodes": _relative(args.nodes),
        "links": _relative(args.links),
        "closure_state": (
            _relative(args.closure_state) if args.closure_state.exists() else None
        ),
        "traffic": _relative(args.traffic) if args.traffic.exists() else None,
    }
    result_path = args.output_dir / "travel_time_matrix.json"
    report_path = args.output_dir / "quality_report.json"
    report["outputs"] = {
        "travel_time_matrix": _relative(result_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(result_path, result)
    write_json_atomic(report_path, report)

    team_route_rows = [
        row for row in result["routes"] if row["origin_type"] == "team_start"
    ]
    available_team_times = [
        row["travel_time_minutes"]
        for row in team_route_rows
        if row["travel_time_minutes"] is not None
    ]
    receipt: dict[str, Any] = {
        "status": report["status"],
        "scenario_id": resource_plan["scenario_id"],
        "execution_mode": result["execution"]["mode"],
        "cache_status": cache_status,
        "graph": report["graph"],
        "origin_count": report["origin_count"],
        "destination_count": report["destination_count"],
        "route_count": report["route_count"],
        "status_counts": report["status_counts"],
        "team_route_time_range_minutes": {
            "minimum": min(available_team_times) if available_team_times else None,
            "maximum": max(available_team_times) if available_team_times else None,
        },
        "closed_link_ids": result["closed_link_ids"],
        "route_semantics": result["route_semantics"],
        "traffic_profile": result.get("parameters", {}).get("traffic_profile", {}),
        "allocation_baseline_recheck": [
            {
                "strategy": row["strategy"],
                "network_total_travel_minutes": row[
                    "network_total_travel_minutes"
                ],
                "maximum_team_elapsed_minutes": row[
                    "maximum_team_elapsed_minutes"
                ],
                "shift_exceeded_team_count": row[
                    "shift_exceeded_team_count"
                ],
                "unavailable_route_leg_count": row[
                    "unavailable_route_leg_count"
                ],
            }
            for row in baseline_recheck
        ],
        "failed_checks": report["failed_checks"],
        "output": _relative(result_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
