#!/usr/bin/env python3
"""Validate and collect the Jeju AI road-control platform when credentials exist."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "05_src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from roadops.jeju_ai_platform import (  # noqa: E402
    extract_records,
    fetch_platform_json,
    normalize_platform_events,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
    parser.add_argument("--endpoint-url")
    parser.add_argument("--token")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/jeju_ai_platform_v0_1",
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
    endpoint = args.endpoint_url or env_value(args.env_file, "JEJU_AI_CONTROL_API_URL")
    token = args.token or env_value(args.env_file, "JEJU_AI_CONTROL_API_TOKEN")
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    if not endpoint or not token:
        events: list[dict[str, object]] = []
        quality = {
            "status": "connection_information_not_issued",
            "generated_at": generated_at,
            "endpoint_configured": bool(endpoint),
            "token_configured": bool(token),
            "required_environment_variables": [
                "JEJU_AI_CONTROL_API_URL",
                "JEJU_AI_CONTROL_API_TOKEN",
            ],
            "reason": "The pilot platform has not published a public endpoint or authentication contract.",
        }
    else:
        try:
            payload, fetch = fetch_platform_json(
                endpoint,
                token,
                timeout_seconds=args.timeout,
                allow_insecure_http=args.allow_insecure_http,
            )
            raw_records = extract_records(payload)
            events, profile = normalize_platform_events(raw_records, fetched_at=fetch["fetched_at"])
            quality = {
                "status": "ready" if events else "response_without_usable_events",
                "generated_at": generated_at,
                "fetch": fetch,
                **profile,
            }
        except Exception as exc:  # external API boundary
            events = []
            quality = {
                "status": "connection_failed",
                "generated_at": generated_at,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:300],
                "credential_exposed": False,
            }

    write_json(
        args.output_dir / "normalized_events.json",
        {
            "schema_version": 1,
            "dataset": "jeju_ai_road_control_platform_events",
            "generated_at": generated_at,
            "records": events,
        },
    )
    write_json(args.output_dir / "quality_report.json", quality)
    print(json.dumps(quality, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
