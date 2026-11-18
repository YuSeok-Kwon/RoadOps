#!/usr/bin/env python3
"""Collect KMA API Hub HSR and QPF images for the RoadOps weather view."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.kma_radar import fetch_radar_frames  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/kma_radar_v0_1/radar_images.json",
    )
    parser.add_argument(
        "--app-output",
        type=Path,
        default=PROJECT_ROOT
        / "08_dashboard/roadops_map_v0_1/src/content/assets/kma-radar.json",
    )
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--strict", action="store_true")
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
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    auth_key = env_value(args.env_file, "KMA_API_HUB_AUTH_KEY")
    if not auth_key:
        print("KMA_API_HUB_AUTH_KEY is not configured", file=sys.stderr)
        return 2 if args.strict else 0

    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    payload = fetch_radar_frames(
        auth_key,
        as_of=as_of,
        timeout_seconds=args.timeout,
    )
    write_json(args.output, payload)

    if payload["ready_frame_count"]:
        write_json(args.app_output, payload)
    elif args.app_output.exists():
        print("No fresh radar frame; preserved the last dashboard cache", file=sys.stderr)

    print(
        json.dumps(
            {
                "status": payload["status"],
                "base_at": payload["base_at"],
                "ready_frame_count": payload["ready_frame_count"],
                "frame_count": payload["frame_count"],
                "app_cache_updated": bool(payload["ready_frame_count"]),
            },
            ensure_ascii=False,
        )
    )
    return 1 if args.strict and payload["status"] != "ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
