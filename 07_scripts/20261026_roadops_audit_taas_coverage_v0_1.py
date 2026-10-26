#!/usr/bin/env python3
"""Audit TAAS detailed-link risk coverage against sampled Jeju road links.

제주 도로 링크 표본으로 TAAS 세부링크 위험지수의 결합 품질을 감사합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.probe import load_source_specs  # noqa: E402
from roadops.taas_audit import audit_taas_links  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--links",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv",
    )
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
        default=PROJECT_ROOT / "02_outputs/data/taas_coverage_audit_v0_1",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/taas_cache",
    )
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--request-delay", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--refresh-cache", action="store_true")
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


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for row in materialized for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)


def main() -> int:
    args = parse_args()
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    spec = specs["taas_link_risk"]
    env_name = spec.authentication["environment_variable"] if spec.authentication else ""
    api_key = _read_env_value(args.env_file, env_name)
    if not api_key:
        raise SystemExit(f"Missing required environment variable: {env_name}")

    report, results, features = audit_taas_links(
        _read_csv(args.links),
        spec,
        api_key=api_key,
        sample_size=args.sample_size,
        seed=args.seed,
        cache_dir=args.cache_dir,
        request_delay_seconds=args.request_delay,
        refresh_cache=args.refresh_cache,
        timeout_seconds=args.timeout,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "audit_report.json"
    results_path = args.output_dir / "sample_results.csv"
    features_path = args.output_dir / "road_risk_features_v0_1.csv"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(results_path, results)
    _write_csv(features_path, features)

    receipt = {
        "status": report["status"],
        "summary": report["summary"],
        "failed_checks": report["failed_checks"],
        "output_files": {
            "report": str(report_path),
            "sample_results": str(results_path),
            "risk_features": str(features_path),
        },
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
