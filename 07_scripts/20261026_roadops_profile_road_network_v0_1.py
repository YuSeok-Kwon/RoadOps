#!/usr/bin/env python3
"""Profile RoadOps road-link and node exports before they enter scoring.

RoadOps 도로 링크·노드 원본을 점수 계산 전에 품질 검사합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.quality import file_sha256, load_records, profile_road_network  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--links", type=Path, required=True, help="Link CSV/JSON/JSONL")
    parser.add_argument("--nodes", type=Path, required=True, help="Node CSV/JSON/JSONL")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path")
    parser.add_argument(
        "--allow-quality-failures",
        action="store_true",
        help="Return exit code 0 even when a quality gate fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    link_rows = load_records(args.links)
    node_rows = load_records(args.nodes)
    report = profile_road_network(link_rows, node_rows)
    report["inputs"] = {
        "links": {
            "path": str(args.links),
            "sha256": file_sha256(args.links),
        },
        "nodes": {
            "path": str(args.nodes),
            "sha256": file_sha256(args.nodes),
        },
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if report["status"] == "fail" and not args.allow_quality_failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
