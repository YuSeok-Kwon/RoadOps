#!/usr/bin/env python3
"""Audit Jeju C-ITS/ITS credentials and timeliness without logging secrets.

비밀값을 기록하지 않고 제주 C-ITS·ITS 인증키와 실시간성을 감사합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.jeju_audit import (  # noqa: E402
    JEJU_LIVE_AUDIT_SOURCE_IDS,
    audit_jeju_payload,
    build_jeju_audit_report,
)
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import load_source_specs  # noqa: E402
from roadops.quality import load_records  # noqa: E402


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
        "--reference-links",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/jeju_live_api_audit_v0_1/audit_report.json",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow the provider's documented HTTP endpoints after explicit risk acceptance.",
    )
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


def main() -> int:
    args = parse_args()
    if not args.allow_insecure_http:
        print(
            json.dumps(
                {
                    "status": "insecure_transport_blocked",
                    "required_flag": "--allow-insecure-http",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    evaluated_at = datetime.now(ZoneInfo("Asia/Seoul"))
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    reference_links = load_records(args.reference_links)
    source_results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for source_id in JEJU_LIVE_AUDIT_SOURCE_IDS:
        spec = specs[source_id]
        environment_variable = spec.authentication["environment_variable"]
        api_key = _read_env_value(args.env_file, environment_variable)
        if not api_key:
            failures.append(
                {
                    "source_id": source_id,
                    "reason": "credential_missing",
                    "required_environment_variable": environment_variable,
                }
            )
            continue
        try:
            payload, fetch_metadata = fetch_json_payload(
                spec,
                api_key=api_key,
                allow_insecure_http=True,
                timeout_seconds=args.timeout,
                now=evaluated_at,
            )
        except LiveFetchError as exc:
            failures.append({"source_id": source_id, **exc.to_dict()})
            continue
        source_results.append(
            audit_jeju_payload(
                spec,
                payload,
                reference_links,
                fetch_metadata=fetch_metadata,
                evaluated_at=evaluated_at,
            )
        )

    report = build_jeju_audit_report(
        source_results,
        evaluated_at=evaluated_at,
        failures=failures,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "status": report["status"],
        "evaluated_at": report["evaluated_at"],
        "credential_checks": report["credential_checks"],
        "realtime_traffic_status": report["realtime_traffic_status"],
        "source_count": report["source_count"],
        "failure_count": report["failure_count"],
        "output": str(args.output),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
