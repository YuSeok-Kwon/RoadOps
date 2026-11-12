#!/usr/bin/env python3
"""Audit Jeju air and sea gateway APIs and their passenger semantics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.gateway_audit import (  # noqa: E402
    GATEWAY_SOURCE_ROLES,
    audit_gateway_source,
    build_gateway_audit_report,
)
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import extract_records, load_source_specs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config/data_sources.json",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / "config/.env",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/gateway_api_audit_v0_1/quality_report.json"
        ),
    )
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read_env_value(path: Path, name: str) -> str | None:
    environment_value = os.environ.get(name)
    if environment_value:
        return environment_value
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


def _generated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def _safe_fetch_result(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key not in {"source_id", "endpoint_url"}
    }


def main() -> int:
    args = parse_args()
    generated_at = _generated_at(args.as_of)
    api_key = _read_env_value(args.env_file, "DATA_GO_KR_SERVICE_KEY")
    if not api_key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")

    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    missing_specs = sorted(set(GATEWAY_SOURCE_ROLES) - set(specs))
    if missing_specs:
        raise SystemExit(f"Missing gateway source specs: {', '.join(missing_specs)}")

    source_results: list[dict[str, Any]] = []
    for source_id in GATEWAY_SOURCE_ROLES:
        spec = specs[source_id]
        records: list[Mapping[str, Any]] = []
        try:
            payload, metadata = fetch_json_payload(
                spec,
                api_key=api_key,
                timeout_seconds=args.timeout,
                now=generated_at,
            )
            records = extract_records(payload)
            fetch_result = _safe_fetch_result(metadata)
        except LiveFetchError as exc:
            fetch_result = exc.to_dict()
        source_results.append(
            audit_gateway_source(
                source_id,
                records=records,
                fetch_result=fetch_result,
            )
        )

    report = build_gateway_audit_report(
        source_results,
        generated_at=generated_at.isoformat(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.output, report)

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "source_count": report["source_count"],
        "readiness_counts": report["readiness_counts"],
        "access_status_counts": report["access_status_counts"],
        "sources": [
            {
                "source_id": result["source_id"],
                "fetch_status": result["fetch_status"],
                "provider_result_code": result["provider_result_code"],
                "record_count": result["record_count"],
                "jeju_signal_rows": result["jeju_signal_rows"],
                "passenger_semantics": result["passenger_semantics"],
                "readiness": result["readiness"],
                "blockers": result["blockers"],
            }
            for result in report["sources"]
        ],
        "failed_checks": report["failed_checks"],
        "output": str(args.output.resolve().relative_to(PROJECT_ROOT.resolve())),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
