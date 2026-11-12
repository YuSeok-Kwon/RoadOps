#!/usr/bin/env python3
"""Audit latest C-ITS snapshots against the Jeju reference road network.

최신 C-ITS 스냅샷을 제주 기준 도로망과 공간 결합해 감사합니다.
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

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.cits_spatial import (  # noqa: E402
    audit_cits_spatial_join,
    load_latest_successful_snapshots,
)
from roadops.quality import load_records  # noqa: E402
from roadops.spatial import build_road_links  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/cits_snapshot_monitor_v0_1/snapshots"
        ),
    )
    parser.add_argument(
        "--reference-links",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv"
        ),
    )
    parser.add_argument(
        "--reference-nodes",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_nodes.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/cits_spatial_join_audit_v0_1",
    )
    parser.add_argument("--spatial-threshold-meters", type=float, default=30.0)
    parser.add_argument("--minimum-margin-meters", type=float, default=5.0)
    parser.add_argument(
        "--exact-coordinate-threshold-meters",
        type=float,
        default=30.0,
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    snapshots = load_latest_successful_snapshots(args.snapshot_dir)
    link_rows = load_records(args.reference_links)
    node_rows = load_records(args.reference_nodes)
    links, network_issues = build_road_links(link_rows, node_rows)
    report, joined_records = audit_cits_spatial_join(
        snapshots,
        links,
        network_issues=network_issues,
        spatial_threshold_meters=args.spatial_threshold_meters,
        minimum_margin_meters=args.minimum_margin_meters,
        exact_coordinate_threshold_meters=args.exact_coordinate_threshold_meters,
        generated_at=datetime.now(ZoneInfo("Asia/Seoul")),
    )

    report_path = args.output_dir / "audit_report.json"
    joined_path = args.output_dir / "joined_records.jsonl"
    report["inputs"] = {
        "snapshot_dir": _relative(args.snapshot_dir),
        "reference_links": _relative(args.reference_links),
        "reference_nodes": _relative(args.reference_nodes),
    }
    report["outputs"] = {
        "audit_report": _relative(report_path),
        "joined_records": _relative(joined_path),
    }
    write_json_atomic(report_path, report)
    _write_jsonl(joined_path, joined_records)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
