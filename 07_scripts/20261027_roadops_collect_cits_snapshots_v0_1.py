#!/usr/bin/env python3
"""Collect C-ITS snapshots and track record lifecycle changes safely.

C-ITS 스냅샷을 수집하고 레코드 생명주기 변화를 안전하게 추적합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import (  # noqa: E402
    CITS_SNAPSHOT_SOURCE_IDS,
    append_jsonl,
    build_failure_snapshot,
    build_success_snapshot,
    evolve_snapshot_state,
    read_json,
    write_json_atomic,
)
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import load_source_specs  # noqa: E402


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
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/cits_snapshot_monitor_v0_1",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
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


def _run_id(collected_at: datetime) -> str:
    return collected_at.strftime("%Y%m%dT%H%M%S%f%z")


def _collect_once(args: argparse.Namespace) -> dict[str, object]:
    collected_at = datetime.now(ZoneInfo("Asia/Seoul"))
    run_id = _run_id(collected_at)
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    source_reports: list[dict[str, object]] = []
    all_transitions: list[dict[str, object]] = []

    for source_id in CITS_SNAPSHOT_SOURCE_IDS:
        spec = specs[source_id]
        environment_variable = spec.authentication["environment_variable"]
        api_key = _read_env_value(args.env_file, environment_variable)
        if not api_key:
            snapshot = build_failure_snapshot(
                source_id,
                error={
                    "status": "fetch_failed",
                    "reason": "credential_missing",
                    "required_environment_variable": environment_variable,
                },
                collected_at=collected_at,
                record_key_fields=spec.record_key,
            )
        else:
            try:
                payload, fetch_metadata = fetch_json_payload(
                    spec,
                    api_key=api_key,
                    allow_insecure_http=True,
                    timeout_seconds=args.timeout,
                    now=collected_at,
                )
            except LiveFetchError as exc:
                snapshot = build_failure_snapshot(
                    source_id,
                    error=exc.to_dict(),
                    collected_at=collected_at,
                    record_key_fields=spec.record_key,
                )
            else:
                snapshot = build_success_snapshot(
                    spec,
                    payload,
                    fetch_metadata=fetch_metadata,
                    collected_at=collected_at,
                )

        state_path = args.output_dir / "state" / f"{source_id}.json"
        previous_state = read_json(state_path)
        state, transitions, quality = evolve_snapshot_state(snapshot, previous_state)
        snapshot_path = (
            args.output_dir / "snapshots" / f"{run_id}_{source_id}.json"
        )
        write_json_atomic(snapshot_path, snapshot)
        write_json_atomic(state_path, state)
        append_jsonl(args.output_dir / "lifecycle_events.jsonl", transitions)
        all_transitions.extend(transitions)
        source_reports.append(
            {
                "source_id": source_id,
                "snapshot_status": snapshot["status"],
                "snapshot_path": str(snapshot_path),
                "state_path": str(state_path),
                "quality": quality,
            }
        )

    transition_counts = Counter(
        transition["change_status"] for transition in all_transitions
    )
    failed_sources = [
        row["source_id"]
        for row in source_reports
        if row["snapshot_status"] != "success"
    ]
    quality_failed_sources = [
        row["source_id"]
        for row in source_reports
        if row["quality"]["status"] == "fail"
    ]
    run_report: dict[str, object] = {
        "schema_version": 1,
        "dataset": "jeju_cits_snapshot_run",
        "grain": "one result per configured C-ITS endpoint per collection run",
        "run_id": run_id,
        "collected_at": collected_at.isoformat(),
        "status": (
            "pass"
            if not failed_sources and not quality_failed_sources
            else "unknown"
            if failed_sources and not quality_failed_sources
            else "fail"
        ),
        "source_count": len(source_reports),
        "failed_source_count": len(failed_sources),
        "failed_sources": failed_sources,
        "quality_failed_source_count": len(quality_failed_sources),
        "quality_failed_sources": quality_failed_sources,
        "transition_counts": dict(sorted(transition_counts.items())),
        "transition_row_count": len(all_transitions),
        "lifecycle_path": str(args.output_dir / "lifecycle_events.jsonl"),
        "sources": source_reports,
        "limitations": [
            "C-ITS records have no provider observation timestamp; collected_at is an ingestion timestamp, not proof of event freshness.",
            "A failed fetch produces unknown lifecycle states and never disappearance events.",
        ],
    }
    run_path = args.output_dir / "runs" / f"{run_id}_run_report.json"
    run_report["run_report_path"] = str(run_path)
    write_json_atomic(run_path, run_report)
    return run_report


def main() -> int:
    args = parse_args()
    if args.iterations < 1:
        raise SystemExit("--iterations must be at least 1")
    if args.interval_seconds < 0:
        raise SystemExit("--interval-seconds must be non-negative")
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

    reports: list[dict[str, object]] = []
    for iteration in range(args.iterations):
        report = _collect_once(args)
        reports.append(report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "run_id": report["run_id"],
                    "collected_at": report["collected_at"],
                    "failed_source_count": report["failed_source_count"],
                    "quality_failed_source_count": report[
                        "quality_failed_source_count"
                    ],
                    "transition_counts": report["transition_counts"],
                    "run_report_path": report["run_report_path"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if iteration + 1 < args.iterations:
            time.sleep(args.interval_seconds)

    failed = any(report["status"] != "pass" for report in reports)
    return 2 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
