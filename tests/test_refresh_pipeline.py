from pathlib import Path

import pytest

from roadops.refresh_pipeline import commands, exclusive_lock, run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_operational_refresh_order_preserves_dependencies():
    stage_ids = [stage_id for stage_id, _ in commands(PROJECT_ROOT, "operational")]
    assert stage_ids.index("cits_snapshots") < stage_ids.index("spatial_join")
    assert stage_ids.index("integrated_events") < stage_ids.index("risk_scores")
    assert stage_ids.index("travel_time") < stage_ids.index("optimized_allocation")
    assert stage_ids[-1] == "dashboard_snapshot"


def test_dry_run_does_not_execute_provider_calls():
    report = run_pipeline(PROJECT_ROOT, profile="operational", timeout_seconds=1, dry_run=True)
    assert report["status"] == "dry_run"
    assert report["stage_count"] >= 10
    assert all(row["status"] == "planned" for row in report["stages"])


def test_lock_rejects_overlapping_refresh(tmp_path):
    lock = tmp_path / "refresh.lock"
    with exclusive_lock(lock):
        with pytest.raises(RuntimeError, match="refresh_already_running"):
            with exclusive_lock(lock):
                pass
    assert not lock.exists()
