"""Run the RoadOps operational refresh as an observable, non-overlapping pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


OPERATIONAL_STAGES = (
    ("jeju_live_apis", "20261027_roadops_audit_jeju_live_api_v0_1.py", "--allow-insecure-http"),
    ("safemap_crime", "20261117_roadops_collect_safemap_crime_v0_1.py"),
    (
        "safemap_response_layers",
        "20261118_roadops_collect_safemap_response_layers_v0_1.py",
    ),
    ("cits_snapshots", "20261027_roadops_collect_cits_snapshots_v0_1.py", "--allow-insecure-http"),
    ("spatial_join", "20261112_roadops_audit_cits_spatial_join_v0_1.py"),
    (
        "integrated_events",
        "20261112_roadops_build_integrated_events_v0_1.py",
        "--refresh-enrichments",
        "--allow-insecure-http",
    ),
    ("risk_scores", "20261112_roadops_build_risk_scores_v0_1.py"),
    ("weather_timeline", "20261112_roadops_build_weather_timeline_v0_1.py"),
    ("kma_radar", "20261118_roadops_collect_kma_radar_v0_1.py"),
    ("gateway_api_audit", "20261112_roadops_audit_gateway_apis_v0_1.py"),
    ("gateway_pressure", "20261117_roadops_build_gateway_pressure_v0_1.py"),
    ("risk_forecasts", "20261112_roadops_build_risk_forecasts_v0_1.py"),
    ("forecast_validation", "20261118_roadops_validate_risk_forecasts_v0_1.py"),
    ("reverse_geocode", "20261117_roadops_reverse_geocode_links_v0_1.py"),
    ("allocation_baselines", "20261112_roadops_build_allocation_baselines_v0_1.py"),
    ("travel_time", "20261113_roadops_build_travel_time_matrix_v0_1.py", "--refresh-cache"),
    ("optimized_allocation", "20261113_roadops_optimize_allocation_v0_1.py"),
    ("partial_replanning", "20261113_roadops_replan_scenarios_v0_1.py"),
    ("historical_similarity", "20261117_roadops_build_historical_similarity_v0_1.py"),
    ("complaint_hotspots", "20261117_roadops_collect_complaint_hotspots_v0_1.py"),
    ("dashboard_snapshot", "20261113_roadops_build_map_snapshot_v0_1.py", "--build-status", "complete"),
)

REFERENCE_STAGES = (
    ("accident_hotspots", "20261117_roadops_collect_accident_hotspots_v0_1.py"),
    ("crime_statistics", "20261117_roadops_collect_crime_statistics_v0_1.py"),
)


def commands(project_root: Path, profile: str) -> list[tuple[str, list[str]]]:
    stages = (
        OPERATIONAL_STAGES[:-1] + REFERENCE_STAGES + OPERATIONAL_STAGES[-1:]
        if profile == "full"
        else OPERATIONAL_STAGES
    )
    python = project_root / ".venv/bin/python"
    executable = str(python if python.exists() else Path(sys.executable))
    return [
        (stage[0], [executable, str(project_root / "07_scripts" / stage[1]), *stage[2:]])
        for stage in stages
    ]


@contextmanager
def exclusive_lock(path: Path):
    """Create a recoverable PID lock and reject concurrent scheduler runs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("refresh_already_running") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def run_pipeline(
    project_root: Path,
    *,
    profile: str,
    timeout_seconds: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = datetime.now(ZoneInfo("Asia/Seoul"))
    stage_results: list[dict[str, Any]] = []
    status = "dry_run" if dry_run else "pass"
    for stage_id, command in commands(project_root, profile):
        if dry_run:
            stage_results.append({"stage_id": stage_id, "status": "planned", "command": command})
            continue
        stage_started = datetime.now(ZoneInfo("Asia/Seoul"))
        try:
            completed = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            stage_status = "pass" if completed.returncode == 0 else "fail"
            stage_results.append(
                {
                    "stage_id": stage_id,
                    "status": stage_status,
                    "return_code": completed.returncode,
                    "started_at": stage_started.isoformat(),
                    "finished_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                    "stdout_tail": completed.stdout[-4000:],
                    "stderr_tail": completed.stderr[-4000:],
                }
            )
        except subprocess.TimeoutExpired as exc:
            stage_results.append(
                {
                    "stage_id": stage_id,
                    "status": "timeout",
                    "started_at": stage_started.isoformat(),
                    "finished_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                    "timeout_seconds": timeout_seconds,
                    "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                    "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                }
            )
        if stage_results[-1]["status"] != "pass":
            status = "fail"
            break

    return {
        "schema_version": 1,
        "dataset": "roadops_refresh_run",
        "profile": profile,
        "status": status,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "stage_count": len(stage_results),
        "completed_stage_count": sum(row["status"] == "pass" for row in stage_results),
        "failed_stage_id": next(
            (row["stage_id"] for row in stage_results if row["status"] in {"fail", "timeout"}),
            None,
        ),
        "stages": stage_results,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
