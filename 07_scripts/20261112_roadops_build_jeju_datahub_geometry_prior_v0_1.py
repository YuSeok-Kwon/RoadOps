#!/usr/bin/env python3
"""Build a quality-gated road-geometry severity prior from Jeju Data Hub data.

제주데이터허브 도로 선형별 사고 데이터로 품질 게이트를 거친 심각도 선행값을 만듭니다.
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
from roadops.jeju_datahub_accidents import (  # noqa: E402
    GEOMETRY_PRIOR_FIELDS,
    LINK_GEOMETRY_PRIOR_FIELDS,
    NORMALIZED_ACCIDENT_FIELDS,
    build_geometry_severity_priors,
    build_link_geometry_priors,
    load_accident_rows,
    profile_accident_rows,
)
from roadops.quality import load_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            PROJECT_ROOT
            / "01_raw_data/external/jeju_datahub_1027"
            / "제주도로선형별교통사고현황.csv"
        ),
    )
    parser.add_argument(
        "--reference-links",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/jeju_datahub_geometry_severity_prior_v0_1"
        ),
    )
    parser.add_argument("--curve-threshold-sinuosity", type=float, default=1.02)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


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
    if not args.source.exists():
        raise SystemExit(
            "Download Jeju Data Hub dataset 1027 and place "
            f"{args.source.name} at {_relative(args.source)}. "
            "Source: https://www.jejudatahub.net/data/view/data/1027"
        )
    generated_at = datetime.now(ZoneInfo("Asia/Seoul"))
    normalized_rows, source_metadata = load_accident_rows(args.source)
    source_metadata["path"] = _relative(args.source)
    source_report = profile_accident_rows(
        normalized_rows,
        source_metadata=source_metadata,
    )
    severity_priors = build_geometry_severity_priors(normalized_rows)
    reference_links = load_records(args.reference_links)
    link_priors, link_report = build_link_geometry_priors(
        reference_links,
        severity_priors,
        curve_threshold_sinuosity=args.curve_threshold_sinuosity,
    )

    normalized_path = args.output_dir / "normalized_accident_statistics.csv"
    severity_path = args.output_dir / "geometry_severity_priors.csv"
    link_path = args.output_dir / "link_geometry_severity_priors.csv"
    report_path = args.output_dir / "quality_report.json"
    _write_csv_atomic(
        normalized_path,
        normalized_rows,
        fieldnames=NORMALIZED_ACCIDENT_FIELDS,
    )
    _write_csv_atomic(
        severity_path,
        [severity_priors[key] for key in sorted(severity_priors)],
        fieldnames=GEOMETRY_PRIOR_FIELDS,
    )
    _write_csv_atomic(
        link_path,
        link_priors,
        fieldnames=LINK_GEOMETRY_PRIOR_FIELDS,
    )

    failed_checks = [
        *(f"source:{check_id}" for check_id in source_report["failed_checks"]),
        *(f"links:{check_id}" for check_id in link_report["failed_checks"]),
    ]
    report = {
        "schema_version": 1,
        "dataset": "roadops_jeju_datahub_geometry_severity_prior",
        "generated_at": generated_at.isoformat(),
        "status": "fail" if failed_checks else "pass_with_limitations",
        "source_profile": source_report,
        "severity_priors": {
            key: severity_priors[key] for key in sorted(severity_priors)
        },
        "link_mapping_profile": link_report,
        "failed_checks": failed_checks,
        "inputs": {
            "source": _relative(args.source),
            "reference_links": _relative(args.reference_links),
        },
        "outputs": {
            "normalized_accident_statistics": _relative(normalized_path),
            "geometry_severity_priors": _relative(severity_path),
            "link_geometry_severity_priors": _relative(link_path),
            "quality_report": _relative(report_path),
        },
        "use_policy": {
            "allowed": (
                "Use fatalities_per_100_accidents and injuries_per_accident as "
                "conditional severity context for a straight/curve geometry proxy."
            ),
            "prohibited": [
                "Do not interpret source accident counts as per-link accident incidence risk because exposure denominators are absent.",
                "Do not add this prior independently to TAAS link risk without an explicit double-counting rule.",
                "Do not treat the 1.02 sinuosity threshold as a provider-defined road-geometry label.",
            ],
        },
    }
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "source_rows": source_report["row_count"],
        "source_failed_checks": source_report["failed_checks"],
        "severity_priors": report["severity_priors"],
        "link_mapping": {
            "output_link_rows": link_report["output_link_rows"],
            "mapping_status_counts": link_report["mapping_status_counts"],
            "geometry_proxy_class_counts": (
                link_report["geometry_proxy_class_counts"]
            ),
            "failed_checks": link_report["failed_checks"],
        },
        "output": _relative(link_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
