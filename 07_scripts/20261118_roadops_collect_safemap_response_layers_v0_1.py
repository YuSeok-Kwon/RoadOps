#!/usr/bin/env python3
"""Collect Safety Map police, fire, and traffic-accident response layers."""

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

from roadops.safemap_response_layers import (  # noqa: E402
    FACILITY_INTERFACES,
    fetch_paginated_records,
    fetch_traffic_accident_wms,
    normalize_jeju_facilities,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/safemap_response_layers_v0_1",
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
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    service_key = env_value(args.env_file, "SAFEMAP_API_KEY")
    facilities: list[dict[str, object]] = []
    accident_overlays: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    if not service_key:
        overall_status = "authorization_not_configured"
        sources.append(
            {
                "source_id": "safemap_response_layers",
                "status": overall_status,
                "required_environment_variable": "SAFEMAP_API_KEY",
                "credential_exposed": False,
            }
        )
    else:
        for facility_kind, interface_id in FACILITY_INTERFACES.items():
            try:
                raw_records, source_quality = fetch_paginated_records(
                    service_key,
                    interface_id,
                    timeout_seconds=args.timeout,
                )
                normalized = normalize_jeju_facilities(
                    raw_records,
                    facility_kind=facility_kind,
                )
                facilities.extend(normalized)
                sources.append(
                    {
                        "source_id": f"safemap_{facility_kind}_facilities",
                        "status": "ready",
                        "jeju_record_count": len(normalized),
                        **source_quality,
                    }
                )
            except Exception as exc:  # external API boundary
                sources.append(
                    {
                        "source_id": f"safemap_{facility_kind}_facilities",
                        "interface_id": interface_id,
                        "status": "connection_failed",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:300],
                        "credential_exposed": False,
                    }
                )
        try:
            overlay, source_quality = fetch_traffic_accident_wms(
                service_key,
                timeout_seconds=args.timeout,
            )
            accident_overlays.append(overlay)
            sources.append(
                {
                    "source_id": "safemap_traffic_accident_wms",
                    **source_quality,
                }
            )
        except Exception as exc:  # external API boundary
            sources.append(
                {
                    "source_id": "safemap_traffic_accident_wms",
                    "status": "connection_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                    "credential_exposed": False,
                }
            )
        ready_count = sum(row.get("status") == "ready" for row in sources)
        overall_status = (
            "ready"
            if ready_count == len(sources)
            else "partial"
            if ready_count
            else "connection_failed"
        )

    write_json(
        args.output_dir / "emergency_facilities.json",
        {
            "schema_version": 1,
            "dataset": "safemap_jeju_police_and_fire_facilities",
            "generated_at": generated_at,
            "records": facilities,
        },
    )
    write_json(
        args.output_dir / "traffic_accident_overlay.json",
        {
            "schema_version": 1,
            "dataset": "safemap_jeju_traffic_accident_hotspot_wms",
            "generated_at": generated_at,
            "records": accident_overlays,
        },
    )
    quality = {
        "status": overall_status,
        "generated_at": generated_at,
        "facility_count": len(facilities),
        "traffic_accident_overlay_count": len(accident_overlays),
        "sources": sources,
        "credential_exposed": False,
    }
    write_json(args.output_dir / "quality_report.json", quality)
    print(json.dumps(quality, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
