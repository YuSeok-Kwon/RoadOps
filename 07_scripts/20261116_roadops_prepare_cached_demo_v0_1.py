#!/usr/bin/env python3
"""Package a compact, key-free RoadOps cached demo from reviewed outputs.

검토된 산출물에서 인증키가 필요 없는 소형 캐시 데모를 만듭니다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.environment_validation import file_sha256  # noqa: E402


DEMO_VERSION = "roadops-cached-demo-v0.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--risk-forecasts",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_forecasts_v0_1/risk_forecasts.csv",
    )
    parser.add_argument(
        "--risk-quality",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_forecasts_v0_1/quality_report.json",
    )
    parser.add_argument(
        "--integrated-events",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/integrated_field_events_v0_1/integrated_field_events.csv",
    )
    parser.add_argument(
        "--event-quality",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/integrated_field_events_v0_1/quality_report.json",
    )
    parser.add_argument(
        "--travel-time-matrix",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/travel_time_matrix_v0_1/travel_time_matrix.json",
    )
    parser.add_argument(
        "--travel-quality",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/travel_time_matrix_v0_1/quality_report.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "demo/cached_inputs_v0_1",
    )
    parser.add_argument(
        "--packaged-at",
        default="2026-11-16T18:00:00+09:00",
        help="Fixed ISO 8601 provenance timestamp for reproducible packaging.",
    )
    return parser.parse_args()


def _read(path: Path):
    if not path.is_file():
        raise SystemExit(f"Required reviewed output is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"Required reviewed output is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".csv":
        text = source.read_text(encoding="utf-8-sig")
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return
    shutil.copyfile(source, destination)


def _slim_travel_matrix(source: dict) -> dict:
    fields = (
        "route_id",
        "origin_id",
        "origin_type",
        "destination_task_id",
        "destination_link_id",
        "status",
        "failure_reason",
        "source_mode",
        "route_semantics",
        "travel_time_minutes",
        "distance_km",
    )
    return {
        "schema_version": source.get("schema_version"),
        "travel_time_version": source.get("travel_time_version"),
        "scenario_id": source.get("scenario_id"),
        "status": source.get("status"),
        "generated_at": source.get("generated_at"),
        "route_semantics": source.get("route_semantics"),
        "closed_link_ids": source.get("closed_link_ids", []),
        "execution": {
            **dict(source.get("execution", {})),
            "bundle_semantics": "route_geometry_omitted_metrics_preserved",
        },
        "routes": [
            {
                **{field: row.get(field) for field in fields},
                "route_link_ids": [],
            }
            for row in source.get("routes", [])
        ],
        "limitations": [
            *list(source.get("limitations", [])),
            "The committed cached demo omits route geometry and cannot rebuild the map.",
            "Travel times remain frozen free-flow estimates and are not live ETA.",
        ],
    }


def main() -> int:
    args = parse_args()
    copies = {
        "risk_forecasts.csv": args.risk_forecasts,
        "risk_quality_report.json": args.risk_quality,
        "integrated_field_events.csv": args.integrated_events,
        "event_quality_report.json": args.event_quality,
        "travel_quality_report.json": args.travel_quality,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, source in copies.items():
        _copy_file(source, args.output_dir / name)

    matrix = _read(args.travel_time_matrix)
    if matrix.get("status") != "pass" or len(matrix.get("routes", [])) != 108:
        raise SystemExit("Travel-time source must be the reviewed 108-route pass artifact")
    write_json_atomic(
        args.output_dir / "travel_time_matrix.json",
        _slim_travel_matrix(matrix),
    )

    files = []
    for path in sorted(args.output_dir.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        files.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "demo_version": DEMO_VERSION,
        "packaged_at": args.packaged_at,
        "semantics": "frozen_reviewed_derived_demo_not_live_data",
        "api_keys_required": False,
        "raw_api_payloads_included": False,
        "route_geometry_included": False,
        "source_outputs": {
            "risk_forecasts": _relative(args.risk_forecasts),
            "integrated_events": _relative(args.integrated_events),
            "travel_time_matrix": _relative(args.travel_time_matrix),
        },
        "limitations": [
            "This bundle is for reproducible offline demonstration only.",
            "It is not current road status and must never be described as live data.",
            "Submission redistribution terms for upstream derived data still require final review.",
        ],
        "files": files,
    }
    write_json_atomic(args.output_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "pass",
                "demo_version": DEMO_VERSION,
                "file_count": len(files),
                "total_bytes": sum(item["bytes"] for item in files),
                "output": _relative(args.output_dir / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
