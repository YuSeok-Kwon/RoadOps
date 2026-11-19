#!/usr/bin/env python3
"""Validate source-to-field lineage for RoadOps Agent and dashboard outputs.

통합 이벤트부터 위험·경로·배분·Agent·지도까지 모든 결과 필드의
원천·변환·한계 계보를 검증합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.data_lineage import (  # noqa: E402
    LINEAGE_VALIDATION_VERSION,
    csv_columns,
    normalized_leaf_paths,
    validate_lineage_spec,
    validate_path_coverage,
    validate_tabular_field_coverage,
)
from roadops.environment_validation import run_command  # noqa: E402
from roadops.submission_validation import read_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lineage",
        type=Path,
        default=PROJECT_ROOT / "config/submission/data_lineage_v0_1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/data_lineage_validation_v0_1",
    )
    parser.add_argument("--skip-agent-smoke", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _check(
    check_id: str,
    passed: bool,
    *,
    evidence: Any,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "pass" if passed else "fail",
        "required": True,
        "evidence": evidence,
    }


def _dataset(payload: Mapping[str, Any], dataset_id: str) -> Mapping[str, Any]:
    for row in payload.get("datasets", []):
        if row.get("dataset_id") == dataset_id:
            return row
    raise KeyError(dataset_id)


def _output(payload: Mapping[str, Any], output_id: str) -> Mapping[str, Any]:
    for row in payload.get("final_outputs", []):
        if row.get("output_id") == output_id:
            return row
    raise KeyError(output_id)


def _csv_profile(path: Path, primary_key: list[str]) -> dict[str, Any]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    keys = [tuple(str(row.get(field) or "") for field in primary_key) for row in rows]
    blank_keys = sum(any(not value for value in key) for key in keys)
    return {
        "row_count": len(rows),
        "primary_key": primary_key,
        "blank_primary_key_count": blank_keys,
        "duplicate_primary_key_count": len(keys) - len(set(keys)),
    }


def _json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    args = parse_args()
    lineage = read_json(args.lineage)
    source_config = read_json(PROJECT_ROOT / "config/data_sources.json")
    configured_source_ids = [
        str(row["id"]) for row in source_config.get("sources", [])
    ]
    spec_validation = validate_lineage_spec(
        PROJECT_ROOT,
        lineage,
        configured_source_ids=configured_source_ids,
    )
    checks = [
        _check(
            "lineage_spec_references",
            spec_validation["status"] == "pass",
            evidence=spec_validation,
        )
    ]

    tabular_coverage: dict[str, Any] = {}
    for dataset_id in ("integrated_field_events", "risk_forecasts"):
        dataset = _dataset(lineage, dataset_id)
        path = PROJECT_ROOT / str(dataset["artifact"])
        coverage = validate_tabular_field_coverage(
            csv_columns(path), dataset.get("field_groups", [])
        )
        tabular_coverage[dataset_id] = coverage
        checks.append(
            _check(
                f"tabular_field_lineage:{dataset_id}",
                coverage["status"] == "pass",
                evidence=coverage,
            )
        )
        profile = _csv_profile(path, list(dataset.get("primary_key", [])))
        profile_passed = (
            profile["row_count"] == int(dataset.get("row_count", -1))
            and profile["blank_primary_key_count"] == 0
            and profile["duplicate_primary_key_count"] == 0
        )
        checks.append(
            _check(
                f"tabular_grain_and_key:{dataset_id}",
                profile_passed,
                evidence=profile,
            )
        )

    travel_dataset = _dataset(lineage, "travel_time_matrix")
    travel_payload = _json(PROJECT_ROOT / str(travel_dataset["artifact"]))
    travel_coverage = validate_path_coverage(
        normalized_leaf_paths(travel_payload),
        travel_dataset.get("coverage_rules", []),
    )
    checks.append(
        _check(
            "json_field_lineage:travel_time_matrix",
            travel_coverage["status"] == "pass",
            evidence=travel_coverage,
        )
    )
    route_count = len(travel_payload.get("routes", []))
    checks.append(
        _check(
            "travel_matrix_grain",
            route_count == int(travel_dataset.get("row_count", -1)),
            evidence={
                "route_count": route_count,
                "expected_route_count": travel_dataset.get("row_count"),
            },
        )
    )

    agent_output_dir = args.output_dir / "agent_result"
    smoke_run = None
    if not args.skip_agent_smoke:
        smoke_run = run_command(
            "cached_agent_for_lineage",
            [
                sys.executable,
                str(
                    PROJECT_ROOT
                    / "07_scripts/20261113_roadops_run_agent_flow_v0_1.py"
                ),
                "--output-dir",
                str(agent_output_dir),
                "--as-of",
                "2026-11-16T18:00:00+09:00",
                "--strict",
            ],
            cwd=PROJECT_ROOT,
        )
        checks.append(
            _check(
                "agent_lineage_smoke",
                smoke_run["status"] == "pass",
                evidence={
                    "status": smoke_run["status"],
                    "duration_seconds": smoke_run["duration_seconds"],
                    "return_code": smoke_run["return_code"],
                },
            )
        )

    agent_path = agent_output_dir / "agent_result.json"
    if agent_path.is_file():
        agent_payload = _json(agent_path)
        agent_coverage = validate_path_coverage(
            normalized_leaf_paths(agent_payload),
            _output(lineage, "agent_result").get("coverage_rules", []),
        )
    else:
        agent_coverage = {
            "status": "fail",
            "observed_path_count": 0,
            "covered_path_count": 0,
            "rule_count": 0,
            "uncovered_paths": ["agent_result_missing"],
            "unused_rules": [],
            "invalid_rules": [],
            "failures": ["agent_result_missing"],
        }
    checks.append(
        _check(
            "final_output_lineage:agent_result",
            agent_coverage["status"] == "pass",
            evidence=agent_coverage,
        )
    )

    dashboard_payload = _json(
        PROJECT_ROOT / "08_dashboard/roadops_map_v0_1/src/data.json"
    )
    dashboard_coverage = validate_path_coverage(
        normalized_leaf_paths(dashboard_payload),
        _output(lineage, "dashboard_snapshot").get("coverage_rules", []),
    )
    checks.append(
        _check(
            "final_output_lineage:dashboard_snapshot",
            dashboard_coverage["status"] == "pass",
            evidence=dashboard_coverage,
        )
    )

    failures = [
        check["check_id"] for check in checks if check["status"] == "fail"
    ]
    source_status_counts = Counter(
        str(row.get("usage_status")) for row in lineage.get("sources", [])
    )
    field_or_path_count = sum(
        result["observed_column_count"] for result in tabular_coverage.values()
    ) + sum(
        result["observed_path_count"]
        for result in (travel_coverage, agent_coverage, dashboard_coverage)
    )
    status = "fail" if failures else "pass_with_limitations"
    report = {
        "schema_version": 1,
        "validation_version": LINEAGE_VALIDATION_VERSION,
        "status": status,
        "lineage": _relative(args.lineage),
        "source_count": spec_validation["source_count"],
        "configured_api_source_count": len(configured_source_ids),
        "source_usage_status_counts": dict(sorted(source_status_counts.items())),
        "dataset_count": spec_validation["dataset_count"],
        "final_output_count": spec_validation["final_output_count"],
        "documented_field_or_leaf_path_count": field_or_path_count,
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": sum(
            check["status"] == "pass" for check in checks
        ),
        "failed_checks": failures,
        "limitations": [
            "Jeju Data Hub dataset 1027 raw redistribution terms require confirmation.",
            "Four air and ferry APIs remain blocked and contribute no gateway pressure.",
            "Future risk values are operational scenarios, not learned accident probabilities.",
            "The dashboard is a reviewed static snapshot, not an automatically refreshed service.",
        ],
    }
    output_path = args.output_dir / "data_lineage_validation.json"
    write_json_atomic(output_path, report)
    print(
        json.dumps(
            {
                "status": status,
                "source_count": report["source_count"],
                "dataset_count": report["dataset_count"],
                "final_output_count": report["final_output_count"],
                "documented_field_or_leaf_path_count": field_or_path_count,
                "required_check_count": report["required_check_count"],
                "passed_required_check_count": report[
                    "passed_required_check_count"
                ],
                "failed_checks": failures,
                "output": _relative(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
