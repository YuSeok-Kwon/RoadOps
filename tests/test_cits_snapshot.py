from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.cits_snapshot import (
    build_failure_snapshot,
    build_success_snapshot,
    evolve_snapshot_state,
    record_identity,
)
from roadops.probe import SourceSpec


T1 = datetime(2026, 10, 27, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
T2 = datetime(2026, 10, 27, 10, 5, tzinfo=ZoneInfo("Asia/Seoul"))
T3 = datetime(2026, 10, 27, 10, 10, tzinfo=ZoneInfo("Asia/Seoul"))


def _spec(record_key=("ocrr_id", "link_id")) -> SourceSpec:
    return SourceSpec(
        source_id="jeju_cits_road_event",
        name="Road event",
        name_ko="도로위험",
        documentation_url="https://example.com",
        kind="json_api",
        endpoint_url="http://api.example.com",
        download_url=None,
        authentication={
            "environment_variable": "JEJU_CITS_API_KEY",
            "query_parameter": "code",
        },
        default_params={},
        runtime_params=None,
        join_key="link_id",
        coordinate_system="EPSG:4326",
        expected_fields=("ocrr_id", "link_id", "latitude", "longitude"),
        record_key=record_key,
        timestamp_field=None,
        source_timezone="Asia/Seoul",
        freshness_max_minutes=None,
    )


def _payload(records):
    return {"result": "success", "info_cnt": len(records), "info": records}


def _snapshot(records, collected_at):
    return build_success_snapshot(
        _spec(),
        _payload(records),
        fetch_metadata={
            "status": "response_received",
            "endpoint_url": "http://api.example.com?code=must-not-survive",
            "transport": "http",
        },
        collected_at=collected_at,
    )


def _event(event_id, link_id="4050000001", text="initial"):
    return {
        "ocrr_id": event_id,
        "link_id": link_id,
        "latitude": "33.3",
        "longitude": "126.5",
        "text": text,
    }


def test_record_identity_normalizes_coordinate_precision():
    left = record_identity(
        {"latitude": "33.300000000", "longitude": 126.5},
        ("latitude", "longitude"),
    )
    right = record_identity(
        {"latitude": 33.3, "longitude": "126.50000000"},
        ("latitude", "longitude"),
    )

    assert left == right


def test_initial_snapshot_marks_records_new_and_removes_endpoint_url():
    snapshot = _snapshot([_event("event-1"), _event("event-2")], T1)

    state, transitions, quality = evolve_snapshot_state(snapshot)

    assert {row["change_status"] for row in transitions} == {"new"}
    assert len(state["active_records"]) == 2
    assert quality["status"] == "pass"
    assert quality["transition_counts"] == {"new": 2}
    assert "endpoint_url" not in snapshot["fetch"]
    assert "must-not-survive" not in str(snapshot)


def test_identical_snapshot_preserves_first_seen_and_marks_unchanged():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    second = _snapshot([_event("event-1")], T2)

    updated, transitions, quality = evolve_snapshot_state(second, state)

    assert quality["transition_counts"] == {"unchanged": 1}
    assert transitions[0]["first_seen_at"] == T1.isoformat()
    assert transitions[0]["last_seen_at"] == T2.isoformat()
    entry = next(iter(updated["active_records"].values()))
    assert entry["seen_snapshots"] == 2


def test_changed_new_and_disappeared_are_separated():
    first = _snapshot([_event("event-1"), _event("event-2")], T1)
    state, _, _ = evolve_snapshot_state(first)
    second = _snapshot(
        [_event("event-1", text="changed"), _event("event-3")],
        T2,
    )

    updated, transitions, quality = evolve_snapshot_state(second, state)

    assert quality["transition_counts"] == {
        "changed": 1,
        "disappeared": 1,
        "new": 1,
    }
    assert len(updated["active_records"]) == 2
    disappeared = next(row for row in transitions if row["change_status"] == "disappeared")
    assert disappeared["last_seen_at"] == T1.isoformat()


def test_fetch_failure_marks_active_records_unknown_without_disappearing_them():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    failed = build_failure_snapshot(
        "jeju_cits_road_event",
        error={"reason": "timeout"},
        collected_at=T2,
        record_key_fields=("ocrr_id", "link_id"),
    )

    updated, transitions, quality = evolve_snapshot_state(failed, state)

    assert quality["status"] == "unknown"
    assert quality["transition_counts"] == {"unknown": 1}
    assert len(updated["active_records"]) == 1
    assert updated["last_success_at"] == T1.isoformat()
    assert transitions[0]["reason"] == "fetch_failed_active_state_preserved"


def test_successful_empty_snapshot_is_not_a_failure_and_marks_disappearance():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    empty = _snapshot([], T2)

    updated, transitions, quality = evolve_snapshot_state(empty, state)

    assert quality["status"] == "pass"
    assert quality["record_count"] == 0
    assert quality["transition_counts"] == {"disappeared": 1}
    assert updated["active_records"] == {}


def test_duplicate_key_is_unknown_and_previous_state_is_preserved():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    duplicate = _snapshot(
        [_event("event-1", text="a"), _event("event-1", text="b")],
        T2,
    )

    updated, transitions, quality = evolve_snapshot_state(duplicate, state)

    assert quality["status"] == "fail"
    assert quality["duplicate_record_key_rows"] == 2
    assert quality["transition_counts"] == {"unknown": 1}
    assert len(updated["active_records"]) == 1
    assert transitions[0]["reason"] == "duplicate_record_key"


def test_duplicate_key_prevents_unrelated_false_disappearance():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    duplicate_other_key = _snapshot(
        [_event("event-2", text="a"), _event("event-2", text="b")],
        T2,
    )

    updated, transitions, quality = evolve_snapshot_state(
        duplicate_other_key,
        state,
    )

    assert quality["status"] == "fail"
    assert quality["transition_counts"] == {"unknown": 2}
    assert len(updated["active_records"]) == 1
    assert not any(row["change_status"] == "disappeared" for row in transitions)
    preserved = next(
        row for row in transitions if row["record_key"] == '["event-1","4050000001"]'
    )
    assert preserved["reason"] == "current_snapshot_has_ambiguous_record_keys"


def test_unkeyed_record_prevents_false_disappearance():
    first = _snapshot([_event("event-1")], T1)
    state, _, _ = evolve_snapshot_state(first)
    incomplete = _snapshot([{"latitude": "33.3", "longitude": "126.5"}], T3)

    updated, transitions, quality = evolve_snapshot_state(incomplete, state)

    assert quality["status"] == "fail"
    assert quality["incomplete_record_key_rows"] == 1
    assert quality["transition_counts"] == {"unknown": 2}
    assert len(updated["active_records"]) == 1
    assert not any(row["change_status"] == "disappeared" for row in transitions)
