#!/usr/bin/env python3
"""Import a sanitized Jeju road-complaint export and publish anonymous hotspots."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "05_src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from roadops.complaint_hotspots import aggregate_complaint_hotspots  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "01_raw_data/external/jeju_road_complaints/road_complaints.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/complaint_hotspots_v0_1",
    )
    parser.add_argument("--minimum-count", type=int, default=3)
    parser.add_argument("--grid-degrees", type=float, default=0.005)
    return parser.parse_args()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    if not args.input.exists():
        records: list[dict[str, object]] = []
        quality = {
            "status": "source_not_provided",
            "generated_at": generated_at,
            "expected_input": str(args.input.relative_to(PROJECT_ROOT)),
            "required_fields": ["received_at", "category", "latitude", "longitude"],
            "optional_fields": ["complaint_id", "status", "responsible_agency"],
            "privacy_requirements": [
                "Remove reporter name, phone, email, exact address, and free-text complaint content before import.",
                "Only cells with at least three complaints are published.",
                "Exact input coordinates and complaint IDs are discarded after aggregation.",
            ],
        }
    else:
        with args.input.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        records, quality = aggregate_complaint_hotspots(
            rows,
            grid_degrees=args.grid_degrees,
            minimum_count=args.minimum_count,
        )
        quality.update(
            {
                "generated_at": generated_at,
                "source_file": str(args.input.relative_to(PROJECT_ROOT)),
            }
        )

    write_json(
        args.output_dir / "complaint_hotspots.json",
        {
            "schema_version": 1,
            "dataset": "privacy_preserving_jeju_road_complaint_hotspots",
            "generated_at": generated_at,
            "records": records,
        },
    )
    write_json(args.output_dir / "quality_report.json", quality)
    print(json.dumps(quality, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
