#!/usr/bin/env python3
"""Build explainable RoadOps risk scores from integrated field events.

통합 현장 이벤트에서 설명 가능한 RoadOps 위험점수를 생성합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import load_records  # noqa: E402
from roadops.risk_scoring import RISK_SCORE_FIELDS, score_risk_events  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integrated-events",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/integrated_field_events_v0_1/integrated_field_events.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_scores_v0_1",
    )
    parser.add_argument(
        "--as-of",
        help=(
            "Timezone-aware ISO timestamp used for deterministic freshness checks. "
            "Defaults to the current Asia/Seoul time."
        ),
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul"))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid --as-of timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise SystemExit("--as-of must include a UTC offset")
    return parsed


def _write_csv_atomic(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    fieldnames: Iterable[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(fieldnames))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if not args.integrated_events.exists():
        raise SystemExit(
            "Integrated events are missing. Run "
            "07_scripts/20261112_roadops_build_integrated_events_v0_1.py first."
        )
    generated_at = _as_of(args.as_of)
    input_rows = load_records(args.integrated_events)
    output_rows, report = score_risk_events(input_rows, generated_at=generated_at)

    score_path = args.output_dir / "risk_scores.csv"
    report_path = args.output_dir / "quality_report.json"
    _write_csv_atomic(score_path, output_rows, fieldnames=RISK_SCORE_FIELDS)
    report["inputs"] = {"integrated_events": _relative(args.integrated_events)}
    report["outputs"] = {
        "risk_scores": _relative(score_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "input_rows": report["input_rows"],
        "output_rows": report["output_rows"],
        "scored_rows": report["scored_rows"],
        "status_counts": report["status_counts"],
        "risk_level_counts": report["risk_level_counts"],
        "score_distribution": report["score_distribution"],
        "failed_checks": report["failed_checks"],
        "output": _relative(score_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
