#!/usr/bin/env python3
"""Refresh RoadOps live operational artifacts once with locking and an audit report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.refresh_pipeline import exclusive_lock, run_pipeline, write_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["operational", "full"], default="operational")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/refresh_pipeline_v0_1/latest_run.json",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/refresh_pipeline_v0_1/refresh.lock",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with exclusive_lock(args.lock_file):
            report = run_pipeline(
                PROJECT_ROOT,
                profile=args.profile,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
            write_report(args.output, report)
    except RuntimeError as exc:
        report = {"status": "skipped", "reason": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"pass", "dry_run", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
