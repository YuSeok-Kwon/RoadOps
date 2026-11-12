#!/usr/bin/env python3
"""Build KMA observation/forecast rows for RoadOps 0/1/3/6-hour horizons."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.integrated_events import required_weather_grids  # noqa: E402
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import extract_records, load_source_specs  # noqa: E402
from roadops.weather_timeline import (  # noqa: E402
    DEFAULT_HORIZONS,
    WEATHER_TIMELINE_FIELDS,
    build_weather_timeline,
)


WEATHER_SOURCE_IDS = (
    "kma_ultra_short_nowcast",
    "kma_ultra_short_forecast",
    "kma_short_forecast",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--joined-records",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/cits_spatial_join_audit_v0_1/joined_records.jsonl"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config/data_sources.json",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / "config/.env",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/weather_timeline_v0_1",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
    )
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read_env_value(path: Path, name: str) -> str | None:
    environment_value = os.environ.get(name)
    if environment_value:
        return environment_value
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'") or None
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(payload)
    return rows


def _generated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def _safe_fetch_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key not in {"source_id", "endpoint_url"}
    }


def _write_csv_atomic(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WEATHER_TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if any(horizon < 0 for horizon in args.horizons):
        raise SystemExit("--horizons must be non-negative")
    generated_at = _generated_at(args.as_of)
    api_key = _read_env_value(args.env_file, "DATA_GO_KR_SERVICE_KEY")
    if not api_key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")

    joined_records = _read_jsonl(args.joined_records)
    grids = required_weather_grids(joined_records)
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    missing_specs = sorted(set(WEATHER_SOURCE_IDS) - set(specs))
    if missing_specs:
        raise SystemExit(f"Missing weather source specs: {', '.join(missing_specs)}")

    records_by_source: dict[str, dict[tuple[int, int], list[Mapping[str, Any]]]] = {
        source_id: {} for source_id in WEATHER_SOURCE_IDS
    }
    fetch_metadata: dict[tuple[str, int, int], dict[str, Any]] = {}
    source_snapshots: list[dict[str, Any]] = []

    for source_id in WEATHER_SOURCE_IDS:
        source_spec = specs[source_id]
        for grid_x, grid_y in sorted(grids):
            grid_spec = replace(
                source_spec,
                default_params={
                    **source_spec.default_params,
                    "nx": grid_x,
                    "ny": grid_y,
                },
            )
            try:
                payload, metadata = fetch_json_payload(
                    grid_spec,
                    api_key=api_key,
                    timeout_seconds=args.timeout,
                    now=generated_at,
                )
                records = [dict(record) for record in extract_records(payload)]
                safe_metadata = _safe_fetch_metadata(metadata)
                records_by_source[source_id][(grid_x, grid_y)] = records
                fetch_metadata[(source_id, grid_x, grid_y)] = safe_metadata
                source_snapshots.append(
                    {
                        "source_id": source_id,
                        "grid_x": grid_x,
                        "grid_y": grid_y,
                        "status": "success",
                        "fetch": safe_metadata,
                        "record_count": len(records),
                        "records": records,
                    }
                )
            except LiveFetchError as exc:
                records_by_source[source_id][(grid_x, grid_y)] = []
                source_snapshots.append(
                    {
                        "source_id": source_id,
                        "grid_x": grid_x,
                        "grid_y": grid_y,
                        "status": "fetch_failed",
                        "error": exc.to_dict(),
                        "record_count": 0,
                        "records": [],
                    }
                )

    rows, report = build_weather_timeline(
        grids,
        observation_records=records_by_source["kma_ultra_short_nowcast"],
        ultra_forecast_records=records_by_source["kma_ultra_short_forecast"],
        short_forecast_records=records_by_source["kma_short_forecast"],
        fetch_metadata=fetch_metadata,
        generated_at=generated_at,
        horizons=args.horizons,
    )
    source_status_counts: dict[str, dict[str, int]] = {}
    for source_id in WEATHER_SOURCE_IDS:
        source_rows = [
            row for row in source_snapshots if row["source_id"] == source_id
        ]
        source_status_counts[source_id] = {
            "success": sum(row["status"] == "success" for row in source_rows),
            "fetch_failed": sum(
                row["status"] == "fetch_failed" for row in source_rows
            ),
            "records": sum(int(row["record_count"]) for row in source_rows),
        }
    report["source_fetches"] = source_status_counts
    report["input_joined_records"] = str(
        args.joined_records.resolve().relative_to(PROJECT_ROOT.resolve())
    )

    timeline_path = args.output_dir / "weather_timeline.csv"
    report_path = args.output_dir / "quality_report.json"
    snapshot_path = args.output_dir / "source_snapshots.json"
    _write_csv_atomic(timeline_path, rows)
    write_json_atomic(report_path, report)
    write_json_atomic(
        snapshot_path,
        {
            "schema_version": 1,
            "generated_at": generated_at.isoformat(),
            "snapshots": source_snapshots,
        },
    )

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "grid_count": report["grid_count"],
        "horizons": report["horizons"],
        "output_rows": report["output_rows"],
        "row_status_counts": report["row_status_counts"],
        "source_fetches": report["source_fetches"],
        "failed_checks": report["failed_checks"],
        "output": str(timeline_path.resolve().relative_to(PROJECT_ROOT.resolve())),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
