#!/usr/bin/env python3
"""Collect official Jeju frequent-accident areas for the independent map layer."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.accident_hotspots import collect_accident_hotspots  # noqa: E402
from roadops.cits_snapshot import write_json_atomic  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
    parser.add_argument("--search-year", type=int, default=2025)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/accident_hotspots_v0_1",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _env_value(path: Path, name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'") or None
    return None


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    rows, report = collect_accident_hotspots(
        api_key=_env_value(args.env_file, "TAAS_API_KEY"),
        search_year=args.search_year,
        timeout=args.timeout,
    )
    payload = {
        "schema_version": 1,
        "source_id": "koroad_local_government_accident_hotspots",
        "generated_at": generated_at,
        "status": report["status"],
        "records": rows,
    }
    report = {"schema_version": 1, "generated_at": generated_at, **report}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.output_dir / "accident_hotspots.json", payload)
    write_json_atomic(args.output_dir / "quality_report.json", report)
    print(json.dumps({**report, "record_count": len(rows)}, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
