from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from roadops.cits_snapshot import CITS_SNAPSHOT_SOURCE_IDS
from roadops.cits_spatial import (
    audit_cits_spatial_join,
    load_latest_successful_snapshots,
)
from roadops.spatial import build_road_links


NOW = datetime(2026, 11, 12, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))


def _network():
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
        {"node_id": "4080000003", "latitude": 33.3260, "longitude": 126.8347},
        {"node_id": "4080000004", "latitude": 33.3270, "longitude": 126.8357},
    ]
    return build_road_links(
        [
            {
                "link_id": "4050000001",
                "start_node_id": "4080000001",
                "end_node_id": "4080000002",
            },
            {
                "link_id": "4050000002",
                "start_node_id": "4080000003",
                "end_node_id": "4080000004",
            },
        ],
        nodes,
    )


def _snapshot(source_id: str, records: list[dict], collected_at: str) -> dict:
    return {
        "source_id": source_id,
        "status": "success",
        "collected_at": collected_at,
        "records": records,
    }


def test_latest_successful_snapshot_is_selected_per_source(tmp_path: Path):
    for source_id in CITS_SNAPSHOT_SOURCE_IDS:
        older = _snapshot(source_id, [{"version": "old"}], "2026-11-12T09:00:00+09:00")
        newer = _snapshot(source_id, [{"version": "new"}], "2026-11-12T10:00:00+09:00")
        (tmp_path / f"older_{source_id}.json").write_text(json.dumps(older))
        (tmp_path / f"newer_{source_id}.json").write_text(json.dumps(newer))
    (tmp_path / "failed.json").write_text(
        json.dumps(
            {
                "source_id": CITS_SNAPSHOT_SOURCE_IDS[0],
                "status": "fetch_failed",
                "collected_at": "2026-11-12T11:00:00+09:00",
                "records": [],
            }
        )
    )

    selected = load_latest_successful_snapshots(tmp_path)

    assert set(selected) == set(CITS_SNAPSHOT_SOURCE_IDS)
    assert all(snapshot["records"] == [{"version": "new"}] for snapshot in selected.values())


def test_missing_successful_snapshot_is_rejected(tmp_path: Path):
    payload = _snapshot(
        CITS_SNAPSHOT_SOURCE_IDS[0],
        [],
        "2026-11-12T10:00:00+09:00",
    )
    (tmp_path / "one.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Missing successful C-ITS snapshots"):
        load_latest_successful_snapshots(tmp_path)


def test_spatial_audit_separates_eligible_and_excluded_records():
    links, network_issues = _network()
    snapshots = {
        source_id: _snapshot(source_id, [], "2026-11-12T10:00:00+09:00")
        for source_id in CITS_SNAPSHOT_SOURCE_IDS
    }
    snapshots["jeju_cits_road_event"]["records"] = [
        {
            "link_id": "4050000001",
            "latitude": 33.3265,
            "longitude": 126.8332,
        }
    ]
    snapshots["jeju_cits_road_weather"]["records"] = [
        {"link_id": "-1", "latitude": 33.3265, "longitude": 126.8352},
        {"link_id": "-1", "latitude": 90.0, "longitude": 180.0},
    ]

    report, joined = audit_cits_spatial_join(
        snapshots,
        links,
        network_issues=network_issues,
        generated_at=NOW,
    )

    assert report["status"] == "review"
    assert report["totals"]["record_count"] == 3
    assert report["totals"]["exact_matches"] == 1
    assert report["totals"]["spatial_matches"] == 1
    assert report["totals"]["invalid_events"] == 1
    assert report["totals"]["scoring_eligible_records"] == 2
    assert sum(row["scoring_eligible"] for row in joined) == 2
    assert {row["match"]["method"] for row in joined} == {
        "exact_link_id",
        "spatial_fallback",
        "invalid",
    }
