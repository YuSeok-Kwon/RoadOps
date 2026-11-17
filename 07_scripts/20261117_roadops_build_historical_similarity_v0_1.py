#!/usr/bin/env python3
"""Build a reviewed list of past road-weather situations similar to the latest snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.historical_similarity import build_historical_similarity  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/cits_snapshot_monitor_v0_1/snapshots",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/historical_similarity_v0_1",
    )
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matches, report = build_historical_similarity(args.snapshot_dir, limit=args.limit)
    output_path = args.output_dir / "similar_incidents.json"
    report_path = args.output_dir / "quality_report.json"
    write_json_atomic(
        output_path,
        {
            "schema_version": 1,
            "dataset": "roadops_historical_weather_incident_similarity",
            "current_observed_at": report.get("current_observed_at"),
            "records": matches,
        },
    )
    report["outputs"] = {
        "matches": str(output_path.relative_to(PROJECT_ROOT)),
        "quality_report": str(report_path.relative_to(PROJECT_ROOT)),
    }
    write_json_atomic(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
