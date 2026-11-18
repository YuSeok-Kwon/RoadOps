#!/usr/bin/env python3
"""Archive and validate RoadOps 0/1/3/6-hour priority forecasts."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.forecast_validation import (  # noqa: E402
    aggregate_link_forecasts,
    validate_forecast_snapshots,
)
from roadops.quality import load_records  # noqa: E402


BOOTSTRAP_REVISIONS = ("062ee500", "af310d61", "3ebb279", "dd7194e")
BOOTSTRAP_SOURCE = "08_dashboard/roadops_map_v0_1/src/data.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--risk-forecasts",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_forecasts_v0_1/risk_forecasts.csv",
    )
    parser.add_argument(
        "--bootstrap",
        type=Path,
        default=PROJECT_ROOT / "demo/cached_inputs_v0_1/forecast_replay_snapshots.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/forecast_validation_v0_1",
    )
    parser.add_argument("--generated-at")
    parser.add_argument("--recover-bootstrap", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(values[0]) if values else [
        "horizon_hours", "link_id", "target_at", "forecast_score", "outcome_score"
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)
    temporary.replace(path)


def _snapshot(snapshot_id: str, generated_at: str, rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "rows": rows,
        **extra,
    }


def _recover_bootstrap(path: Path) -> list[dict[str, Any]]:
    snapshots = []
    for revision in BOOTSTRAP_REVISIONS:
        completed = subprocess.run(
            ["git", "show", f"{revision}:{BOOTSTRAP_SOURCE}"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        rows = payload["queries"]["risk_links"]["rows"]
        snapshots.append(
            _snapshot(
                f"git:{revision}",
                payload["generatedAt"],
                aggregate_link_forecasts(rows),
                provenance={"git_revision": revision, "path": BOOTSTRAP_SOURCE},
            )
        )
    result = {
        "schema_version": 1,
        "description": "Immutable forecast replay bootstrap recovered from exact committed dashboard snapshots.",
        "snapshots": snapshots,
    }
    write_json_atomic(path, result)
    return snapshots


def _archive_current(risk_path: Path, archive_dir: Path) -> dict[str, Any]:
    rows = aggregate_link_forecasts(load_records(risk_path))
    generated_values = sorted({str(row.get("generated_at")) for row in rows if row.get("generated_at")})
    if len(generated_values) != 1:
        raise SystemExit("Current forecasts must contain exactly one generated_at value")
    generated_at = generated_values[0]
    archive_name = generated_at.replace(":", "").replace("+", "_") + ".json"
    archive_path = archive_dir / archive_name
    snapshot = _snapshot(
        f"archive:{generated_at}",
        generated_at,
        rows,
        provenance={"path": _relative(risk_path)},
    )
    if not archive_path.exists():
        write_json_atomic(archive_path, snapshot)
    return snapshot


def main() -> int:
    args = parse_args()
    if args.recover_bootstrap:
        bootstrap = _recover_bootstrap(args.bootstrap)
    elif args.bootstrap.exists():
        bootstrap = _read_json(args.bootstrap).get("snapshots", [])
    else:
        raise SystemExit("Bootstrap replay snapshots are missing; run with --recover-bootstrap once")
    if not args.risk_forecasts.exists():
        raise SystemExit(f"Required input is missing: {_relative(args.risk_forecasts)}")

    archive_dir = args.output_dir / "archive"
    current = _archive_current(args.risk_forecasts, archive_dir)
    archived = [
        _read_json(path)
        for path in sorted(archive_dir.glob("*.json"))
        if path.is_file()
    ]
    snapshots_by_id = {
        str(snapshot.get("snapshot_id")): snapshot
        for snapshot in [*bootstrap, *archived, current]
    }
    now = (
        datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
        if args.generated_at
        else datetime.now(ZoneInfo("Asia/Seoul"))
    )
    if now.tzinfo is None:
        raise SystemExit("--generated-at must include a UTC offset")
    report, matched = validate_forecast_snapshots(
        snapshots_by_id.values(), generated_at=now
    )
    report["inputs"] = {
        "current_forecasts": _relative(args.risk_forecasts),
        "bootstrap": _relative(args.bootstrap),
        "archive_directory": _relative(archive_dir),
    }
    report["outputs"] = {
        "quality_report": _relative(args.output_dir / "quality_report.json"),
        "matched_forecasts": _relative(args.output_dir / "matched_forecasts.csv"),
    }
    write_json_atomic(args.output_dir / "quality_report.json", report)
    _write_csv(args.output_dir / "matched_forecasts.csv", matched)
    print(
        json.dumps(
            {
                "status": report["status"],
                "snapshot_count": report["snapshot_count"],
                "leakage_failure_count": report["leakage_failure_count"],
                "metrics": report["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
