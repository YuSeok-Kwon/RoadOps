#!/usr/bin/env python3
"""Fetch or load a dynamic road source and validate it against the Jeju network.

실시간 도로 소스를 가져오거나 읽어 제주 기준망과의 호환성을 검증합니다.
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

from roadops.compatibility import profile_link_compatibility  # noqa: E402
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import extract_records, load_source_specs  # noqa: E402
from roadops.quality import file_sha256, load_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--reference-links",
        type=Path,
        required=True,
        help="Validated reference link CSV/JSON/JSONL.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Existing source response. Omit to fetch the configured endpoint.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "data_sources.json",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--link-field", default="link_id")
    parser.add_argument("--expected-field", action="append", default=[])
    parser.add_argument("--record-key", action="append", default=[])
    parser.add_argument("--timestamp-field", default=None)
    parser.add_argument("--source-timezone", default=None)
    parser.add_argument("--freshness-max-minutes", type=float, default=None)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Transmit the API key over HTTP only after explicit risk acceptance.",
    )
    parser.add_argument("--allow-quality-failures", action="store_true")
    return parser.parse_args()


def _source_spec(args: argparse.Namespace):
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    if args.source_id not in specs:
        raise ValueError(f"Unknown source_id: {args.source_id}")
    return specs[args.source_id]


def _default_raw_output(source_id: str) -> Path:
    timestamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%dT%H%M%S")
    return PROJECT_ROOT / "02_outputs" / "data" / "live" / f"{timestamp}_{source_id}.json"


def main() -> int:
    args = parse_args()
    spec = _source_spec(args)
    fetch_metadata: dict[str, object]
    if args.input is not None:
        source_rows = load_records(args.input)
        source_input_path = args.input
        fetch_metadata = {"status": "not_requested", "mode": "existing_input"}
    else:
        if spec.authentication is None:
            result = {"status": "authentication_not_configured", "source_id": spec.source_id}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3
        environment_variable = spec.authentication["environment_variable"]
        api_key = os.environ.get(environment_variable, "")
        if not api_key:
            result = {
                "status": "credential_missing",
                "source_id": spec.source_id,
                "required_environment_variable": environment_variable,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3
        try:
            payload, fetch_metadata = fetch_json_payload(
                spec,
                api_key=api_key,
                allow_insecure_http=args.allow_insecure_http,
            )
        except LiveFetchError as exc:
            result = {"source_id": spec.source_id, **exc.to_dict()}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 4
        source_rows = [dict(row) for row in extract_records(payload)]
        source_input_path = args.raw_output or _default_raw_output(spec.source_id)
        source_input_path.parent.mkdir(parents=True, exist_ok=True)
        source_input_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    reference_rows = load_records(args.reference_links)
    expected_fields = tuple(dict.fromkeys((*spec.expected_fields, *args.expected_field)))
    record_key = tuple(args.record_key) if args.record_key else spec.record_key
    timestamp_field = args.timestamp_field or spec.timestamp_field
    source_timezone = args.source_timezone or spec.source_timezone
    freshness_max_minutes = (
        args.freshness_max_minutes
        if args.freshness_max_minutes is not None
        else spec.freshness_max_minutes
    )
    report = profile_link_compatibility(
        source_rows,
        reference_rows,
        source_id=spec.source_id,
        link_field=args.link_field,
        expected_fields=expected_fields,
        record_key_fields=record_key,
        timestamp_field=timestamp_field,
        source_timezone=source_timezone,
        freshness_max_minutes=freshness_max_minutes,
    )
    report["inputs"] = {
        "source": {
            "path": str(source_input_path),
            "sha256": file_sha256(source_input_path),
            "mode": "existing_input" if args.input is not None else "live_fetch",
        },
        "reference_links": {
            "path": str(args.reference_links),
            "sha256": file_sha256(args.reference_links),
        },
        "fetch": fetch_metadata,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if report["status"] == "fail" and not args.allow_quality_failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
