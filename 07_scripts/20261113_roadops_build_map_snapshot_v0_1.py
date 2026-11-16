#!/usr/bin/env python3
"""Build the reviewed data snapshot used by the RoadOps map dashboard."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "05_src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from roadops.map_snapshot import build_map_snapshot  # noqa: E402


DEFAULT_APP_DIR = PROJECT_ROOT / "08_dashboard/roadops_map_v0_1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--risk-forecasts",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/risk_forecasts_v0_1/risk_forecasts.csv",
    )
    parser.add_argument(
        "--optimized-allocation",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/optimized_allocation_v0_1/optimized_allocation.json",
    )
    parser.add_argument(
        "--replanning",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/partial_replanning_v0_1/replanning_scenarios.json",
    )
    parser.add_argument(
        "--resources",
        type=Path,
        default=PROJECT_ROOT
        / "config/resource_scenarios/demo_three_teams_v0_1.json",
    )
    parser.add_argument(
        "--allocation",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/allocation_baselines_v0_1/allocation_baselines.json",
    )
    parser.add_argument(
        "--road-links",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/map_snapshot_v0_1",
    )
    parser.add_argument(
        "--app-data",
        type=Path,
        default=DEFAULT_APP_DIR / "src/data.json",
    )
    parser.add_argument(
        "--build-status",
        choices=["creating", "updating", "complete", "paused"],
        default="creating",
    )
    parser.add_argument(
        "--generated-at",
        help="Timezone-aware ISO timestamp. Defaults to current Asia/Seoul time.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def source(
    label: str,
    paths: list[Path],
    component_ids: list[str],
    caveats: list[str],
) -> dict[str, Any]:
    return {
        "label": label,
        "caveats": caveats,
        "tables": [relative(path) for path in paths],
        "metricDefinitions": [
            {
                "label": label,
                "definition": (
                    "Repository-local reviewed snapshot generated deterministically "
                    "from the listed source artifacts."
                ),
                "componentIds": component_ids,
                "sourceLineage": [{"tables": [relative(path) for path in paths]}],
            }
        ],
    }


def build_data_app_snapshot(
    queries: dict[str, list[dict[str, Any]]],
    *,
    generated_at: str,
    build_status: str,
    inputs: dict[str, Path],
) -> dict[str, Any]:
    shared_caveats = [
        "This is a repository-local snapshot, not a continuously refreshed live feed.",
        "Risk values are operational priority scenarios, not accident probabilities.",
        "Travel time is a road-network free-flow estimate, not a live ETA.",
        "Replanning layers are What-if scenarios and require operator approval.",
    ]
    query_sources = {
        "map_metadata": source(
            "Map snapshot metadata",
            [inputs["risk_forecasts"]],
            ["map-status"],
            shared_caveats,
        ),
        "road_background": source(
            "MOLIT Jeju standard road-link geometry",
            [inputs["road_links"]],
            ["roadops-map"],
            ["Only selected major named roads are used as visual context."],
        ),
        "risk_links": source(
            "RoadOps explainable risk forecasts",
            [inputs["risk_forecasts"], inputs["road_links"]],
            ["roadops-map", "risk-detail"],
            shared_caveats,
        ),
        "field_tasks": source(
            "RoadOps field-task candidates",
            [inputs["allocation"]],
            ["roadops-map", "task-queue"],
            ["Excluded tasks are shown as constraints and are not dispatch recommendations."],
        ),
        "teams": source(
            "Demo patrol resource scenario",
            [inputs["resources"]],
            ["roadops-map"],
            ["Team locations and shifts are demonstrative scenario inputs."],
        ),
        "plan_routes": source(
            "Constraint-based allocation routes",
            [inputs["optimized_allocation"], inputs["road_links"]],
            ["roadops-map"],
            shared_caveats,
        ),
        "plan_metrics": source(
            "Constraint-based allocation metrics",
            [inputs["optimized_allocation"]],
            ["allocation-kpis", "plan-comparison"],
            shared_caveats,
        ),
        "replan_routes": source(
            "Partial replanning route comparison",
            [inputs["replanning"], inputs["road_links"]],
            ["roadops-map", "replan-summary"],
            shared_caveats,
        ),
        "scenario_summary": source(
            "Partial replanning explanations",
            [inputs["replanning"]],
            ["replan-summary"],
            shared_caveats,
        ),
        "scenario_impacts": source(
            "What-if closure and heavy-rain impact links",
            [inputs["replanning"], inputs["road_links"]],
            ["roadops-map"],
            shared_caveats,
        ),
        "data_availability": source(
            "External layer availability",
            [inputs["risk_forecasts"]],
            ["gateway-availability"],
            ["Unavailable evidence remains missing and contributes no score."],
        ),
    }
    return {
        "id": "roadops:jeju-field-operations-map:v0.1",
        "title": "RoadOps 제주 현장 운영 워크벤치",
        "generatedAt": generated_at,
        "status": "reviewed_local_snapshot",
        "surface": "dashboard",
        "filters": [],
        "queries": {
            query_id: {"rows": rows, "source": query_sources[query_id]}
            for query_id, rows in queries.items()
        },
        "buildStatus": build_status,
        "exportPreferences": {"selected": None, "destinations": []},
    }


def main() -> int:
    args = parse_args()
    generated_at = args.generated_at or datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    inputs = {
        "risk_forecasts": args.risk_forecasts,
        "optimized_allocation": args.optimized_allocation,
        "replanning": args.replanning,
        "resources": args.resources,
        "allocation": args.allocation,
        "road_links": args.road_links,
    }
    for name, path in inputs.items():
        if not path.exists():
            raise FileNotFoundError(f"{name}: {path}")

    queries, quality = build_map_snapshot(
        risk_rows=read_csv(args.risk_forecasts),
        optimized=read_json(args.optimized_allocation),
        replanning=read_json(args.replanning),
        resources=read_json(args.resources),
        allocation=read_json(args.allocation),
        link_rows=read_csv(args.road_links),
        generated_at=generated_at,
    )
    app_snapshot = build_data_app_snapshot(
        queries,
        generated_at=generated_at,
        build_status=args.build_status,
        inputs=inputs,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.app_data.parent.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "map_snapshot.json").write_text(
        json.dumps(queries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.app_data.write_text(
        json.dumps(app_snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    return 0 if quality["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
