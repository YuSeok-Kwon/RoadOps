#!/usr/bin/env python3
"""Collect official privacy-preserving 2025 crime statistics for Jeju cities."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.crime_statistics import (  # noqa: E402
    ANALYSIS_YEAR,
    download_official_crime_csv,
    normalize_jeju_crime_statistics,
    parse_crime_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/crime_statistics_v0_1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    content, fetch = download_official_crime_csv(args.timeout)
    source_rows = parse_crime_csv(content)
    records = normalize_jeju_crime_statistics(source_rows)
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    output_path = args.output_dir / "crime_statistics.json"
    report_path = args.output_dir / "quality_report.json"
    write_json_atomic(
        output_path,
        {
            "schema_version": 1,
            "dataset": "police_crime_statistics_by_jeju_city",
            "generated_at": generated_at,
            "analysis_year": ANALYSIS_YEAR,
            "records": records,
        },
    )
    report = {
        "status": "pass" if len(records) == 2 else "fail",
        "generated_at": generated_at,
        "source_row_count": len(source_rows),
        "record_count": len(records),
        "cities": [row["administrative_city"] for row in records],
        "spatial_grain": "administrative_city",
        "map_hotspot_eligible": False,
        "fetch": fetch,
        "limitations": [
            "시 단위 연간 비식별 통계이므로 개별 도로 또는 지점의 범죄 다발도로 해석할 수 없습니다.",
            "도로 우선순위 점수에는 반영하지 않고 선택 구간이 속한 행정시의 참고 통계로만 표시합니다.",
            "범죄주의구간 지도는 생활안전지도 별도 활용승인과 인증키가 필요합니다.",
        ],
    }
    write_json_atomic(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
