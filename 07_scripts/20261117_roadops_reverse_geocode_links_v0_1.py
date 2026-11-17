#!/usr/bin/env python3
"""Reverse-geocode current RoadOps link midpoints with a persistent provider cache."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.reverse_geocode import enrich_link_locations, midpoint  # noqa: E402
from roadops.spatial import parse_link_geometry_wkt  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--risk-forecasts",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_forecasts_v0_1/risk_forecasts.csv",
    )
    parser.add_argument(
        "--road-links",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/reverse_geocode_v0_1",
    )
    parser.add_argument("--request-delay", type=float, default=1.1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "config/.env")
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


def main() -> int:
    args = parse_args()
    with args.risk_forecasts.open(encoding="utf-8-sig", newline="") as handle:
        risk_rows = list(csv.DictReader(handle))
    required = {str(row.get("effective_link_id")) for row in risk_rows if row.get("effective_link_id")}
    points = []
    with args.road_links.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            link_id = str(row.get("link_id") or "")
            if link_id not in required:
                continue
            parsed = parse_link_geometry_wkt(str(row.get("geometry_wkt") or ""))
            parts = [
                [[point.longitude, point.latitude] for point in part]
                for part in parsed or ()
            ]
            coordinate = midpoint(parts)
            if coordinate:
                points.append({"link_id": link_id, "latitude": coordinate[0], "longitude": coordinate[1], "road_name": row.get("road_name")})
    records, report = enrich_link_locations(
        points,
        cache_path=args.output_dir / "provider_cache.json",
        request_delay_seconds=args.request_delay,
        timeout_seconds=args.timeout,
        sgis_consumer_key=env_value(args.env_file, "SGIS_CONSUMER_KEY"),
        sgis_consumer_secret=env_value(args.env_file, "SGIS_CONSUMER_SECRET"),
        sgis_cache_path=args.output_dir / "sgis_provider_cache.json",
    )
    output_path = args.output_dir / "link_locations.json"
    report_path = args.output_dir / "quality_report.json"
    write_json_atomic(output_path, {"schema_version": 1, "dataset": "roadops_link_reverse_geocode", "records": records})
    report["requested_link_count"] = len(required)
    report["limitations"] = [
        "SGIS 서비스 ID·보안 Key가 있으면 공식 도로명·지번 응답을 우선 사용하고, 없거나 실패하면 OpenStreetMap으로 보완합니다.",
        "SGIS 역지오코딩 응답에도 교차로 고유명은 없어 임의 생성하지 않습니다.",
        "정확한 교차로명 확정에는 운영기관 교차로 원장이 필요합니다.",
    ]
    write_json_atomic(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if records else 2


if __name__ == "__main__":
    raise SystemExit(main())
