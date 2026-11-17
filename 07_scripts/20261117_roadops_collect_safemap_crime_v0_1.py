#!/usr/bin/env python3
"""Collect the authorized Safety Map crime-caution image for the Jeju extent."""

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

from roadops.safemap_crime import fetch_crime_caution_wms  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/safemap_crime_v0_1",
    )
    return parser.parse_args()


def env_value(path: Path, name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    service_key = env_value(args.env_file, "SAFEMAP_API_KEY")
    if not service_key:
        records: list[dict[str, object]] = []
        quality = {
            "status": "authorization_not_configured",
            "generated_at": generated_at,
            "required_environment_variable": "SAFEMAP_API_KEY",
            "application_note": "Location-based service authorization may be required by the provider.",
            "credential_exposed": False,
        }
    else:
        try:
            overlay, quality = fetch_crime_caution_wms(service_key, timeout_seconds=args.timeout)
            records = [overlay]
            quality["generated_at"] = generated_at
        except Exception as exc:  # external API boundary
            records = []
            quality = {
                "status": "connection_failed",
                "generated_at": generated_at,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:300],
                "credential_exposed": False,
            }
    write_json(
        args.output_dir / "crime_caution_overlay.json",
        {
            "schema_version": 1,
            "dataset": "safemap_crime_caution_wms_jeju",
            "generated_at": generated_at,
            "records": records,
        },
    )
    write_json(args.output_dir / "quality_report.json", quality)
    print(json.dumps(quality, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
