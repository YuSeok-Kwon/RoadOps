#!/usr/bin/env python3
"""Run the RoadOps data-source feasibility probe.

RoadOps 데이터 소스의 문서 접근성과 선택적 실시간 응답을 점검합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.probe import load_source_specs, probe_sources  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "data_sources.json",
        help="Path to the data source registry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Generated data should stay under 02_outputs.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call operational endpoints when their API-key environment variables exist.",
    )
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow API keys over plaintext HTTP only after explicit risk acceptance.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = load_source_specs(args.config)
    report = probe_sources(
        specs,
        live=args.live,
        allow_insecure_http=args.allow_insecure_http,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
