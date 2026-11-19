#!/usr/bin/env python3
"""Build a quality-gated airport and ferry access-pressure feature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.gateway_pressure import build_gateway_pressure  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/gateway_api_audit_v0_1/quality_report.json",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/gateway_api_audit_v0_1/gateway_records.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/gateway_pressure_v0_1/gateway_pressure.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    record_payload = json.loads(args.records.read_text(encoding="utf-8"))
    by_source = {
        str(row.get("source_id")): row.get("records", [])
        for row in record_payload.get("sources", [])
    }
    result = build_gateway_pressure(by_source, audit, generated_at=str(audit["generated_at"]))
    write_json_atomic(args.output, result)
    print(json.dumps({key: result[key] for key in ("status", "generated_at", "source_readiness")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
