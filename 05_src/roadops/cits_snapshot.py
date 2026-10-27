"""Persist C-ITS snapshots and derive failure-safe record lifecycle changes.

C-ITS 스냅샷을 저장하고 실패에 안전한 레코드 생명주기 변화를 계산합니다.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from roadops.probe import SourceSpec, extract_records


CITS_SNAPSHOT_SOURCE_IDS = (
    "jeju_cits_road_event",
    "jeju_cits_road_close",
    "jeju_cits_road_work",
    "jeju_cits_road_weather",
)


def _isoformat(value: datetime) -> str:
    timezone = ZoneInfo("Asia/Seoul")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone)
    else:
        value = value.astimezone(timezone)
    return value.isoformat()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key).strip().lower(): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value


def _digest(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _identity_value(field: str, value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if field in {"latitude", "longitude"}:
        try:
            return f"{float(text):.8f}"
        except ValueError:
            return None
    return text


def record_identity(
    record: Mapping[str, Any], fields: Iterable[str]
) -> tuple[str, str] | None:
    """Return a stable serialized identity and digest for a configured record key."""

    canonical = _canonicalize(record)
    parts: list[str] = []
    for raw_field in fields:
        field = raw_field.strip().lower()
        value = _identity_value(field, canonical.get(field))
        if value is None:
            return None
        parts.append(value)
    serialized = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_success_snapshot(
    spec: SourceSpec,
    payload: Mapping[str, Any],
    *,
    fetch_metadata: Mapping[str, Any],
    collected_at: datetime,
) -> dict[str, Any]:
    """Build a credential-free snapshot from one successful provider response."""

    records = [_canonicalize(record) for record in extract_records(payload)]
    ordered_fingerprints = sorted(_digest(record) for record in records)
    safe_fetch = {
        key: value
        for key, value in fetch_metadata.items()
        if key not in {"source_id", "endpoint_url"}
    }
    return {
        "schema_version": 1,
        "dataset": "jeju_cits_snapshot",
        "source_id": spec.source_id,
        "collected_at": _isoformat(collected_at),
        "status": "success",
        "provider_result": payload.get("result"),
        "provider_reported_count": payload.get("info_cnt"),
        "record_count": len(records),
        "record_key_fields": list(spec.record_key),
        "snapshot_fingerprint": _digest(ordered_fingerprints),
        "fetch": safe_fetch,
        "records": records,
    }


def build_failure_snapshot(
    source_id: str,
    *,
    error: Mapping[str, Any],
    collected_at: datetime,
    record_key_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Represent a failed fetch without converting it to a successful empty snapshot."""

    return {
        "schema_version": 1,
        "dataset": "jeju_cits_snapshot",
        "source_id": source_id,
        "collected_at": _isoformat(collected_at),
        "status": "fetch_failed",
        "provider_reported_count": None,
        "record_count": None,
        "record_key_fields": list(record_key_fields),
        "snapshot_fingerprint": None,
        "error": dict(error),
        "records": [],
    }


def _empty_state(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": "jeju_cits_active_state",
        "source_id": snapshot["source_id"],
        "record_key_fields": list(snapshot.get("record_key_fields", [])),
        "first_success_at": None,
        "last_success_at": None,
        "last_attempt_at": None,
        "last_attempt_status": None,
        "successful_snapshot_count": 0,
        "active_records": {},
    }


def _transition(
    *,
    snapshot: Mapping[str, Any],
    change_status: str,
    record_key: str | None,
    record_key_hash: str | None,
    record: Mapping[str, Any] | None,
    first_seen_at: str | None,
    last_seen_at: str | None,
    fingerprint: str | None,
    previous_fingerprint: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    current = dict(record or {})
    source_status = snapshot["status"]
    return {
        "source_id": snapshot["source_id"],
        "record_key": record_key,
        "record_key_hash": record_key_hash,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "collected_at": snapshot["collected_at"],
        "change_status": change_status,
        "source_status": source_status,
        "link_id": current.get("link_id"),
        "latitude": current.get("latitude"),
        "longitude": current.get("longitude"),
        "heading": current.get("heading"),
        "fingerprint": fingerprint,
        "previous_fingerprint": previous_fingerprint,
        "match_method": "pending",
        "match_distance_m": None,
        "freshness_state": (
            "unknown_due_to_fetch_failure"
            if source_status != "success"
            else "source_timestamp_unavailable"
        ),
        "reason": reason,
    }


def evolve_snapshot_state(
    snapshot: Mapping[str, Any],
    previous_state: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Apply a snapshot and return updated state, lifecycle transitions, and audit."""

    state = json.loads(json.dumps(previous_state or _empty_state(snapshot)))
    if state.get("source_id") != snapshot.get("source_id"):
        raise ValueError("Snapshot and state source_id must match")

    collected_at = str(snapshot["collected_at"])
    active: dict[str, dict[str, Any]] = dict(state.get("active_records", {}))
    state["last_attempt_at"] = collected_at
    state["last_attempt_status"] = snapshot["status"]

    if snapshot["status"] != "success":
        transitions = [
            _transition(
                snapshot=snapshot,
                change_status="unknown",
                record_key=key,
                record_key_hash=entry["record_key_hash"],
                record=entry["record"],
                first_seen_at=entry["first_seen_at"],
                last_seen_at=entry["last_seen_at"],
                fingerprint=entry["fingerprint"],
                reason="fetch_failed_active_state_preserved",
            )
            for key, entry in sorted(active.items())
        ]
        quality = {
            "status": "unknown",
            "source_status": snapshot["status"],
            "record_count": None,
            "valid_unique_record_count": None,
            "incomplete_record_key_rows": None,
            "duplicate_record_key_rows": None,
            "reported_count_matches": None,
            "active_record_count": len(active),
            "transition_counts": dict(Counter(row["change_status"] for row in transitions)),
        }
        return state, transitions, quality

    key_fields = tuple(str(field) for field in snapshot.get("record_key_fields", []))
    if not key_fields:
        raise ValueError("Successful snapshots require record_key_fields")

    groups: defaultdict[str, list[tuple[dict[str, Any], str, str]]] = defaultdict(list)
    incomplete_records: list[tuple[dict[str, Any], str]] = []
    for raw_record in snapshot.get("records", []):
        record = _canonicalize(raw_record)
        fingerprint = _digest(record)
        identity = record_identity(record, key_fields)
        if identity is None:
            incomplete_records.append((record, fingerprint))
            continue
        record_key, record_key_hash = identity
        groups[record_key].append((record, fingerprint, record_key_hash))

    duplicate_keys = {key for key, rows in groups.items() if len(rows) > 1}
    unique_current = {
        key: rows[0] for key, rows in groups.items() if len(rows) == 1
    }
    new_active: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []

    for key, (record, fingerprint, record_key_hash) in sorted(unique_current.items()):
        previous = active.get(key)
        if previous is None:
            change_status = "new"
            first_seen_at = collected_at
            previous_fingerprint = None
            seen_snapshots = 1
        else:
            change_status = (
                "unchanged" if previous["fingerprint"] == fingerprint else "changed"
            )
            first_seen_at = previous["first_seen_at"]
            previous_fingerprint = previous["fingerprint"]
            seen_snapshots = int(previous.get("seen_snapshots", 1)) + 1
        entry = {
            "record_key_hash": record_key_hash,
            "first_seen_at": first_seen_at,
            "last_seen_at": collected_at,
            "last_changed_at": (
                collected_at
                if change_status in {"new", "changed"}
                else previous.get("last_changed_at")
            ),
            "seen_snapshots": seen_snapshots,
            "fingerprint": fingerprint,
            "record": record,
        }
        new_active[key] = entry
        transitions.append(
            _transition(
                snapshot=snapshot,
                change_status=change_status,
                record_key=key,
                record_key_hash=record_key_hash,
                record=record,
                first_seen_at=first_seen_at,
                last_seen_at=collected_at,
                fingerprint=fingerprint,
                previous_fingerprint=previous_fingerprint,
            )
        )

    for key in sorted(duplicate_keys):
        previous = active.get(key)
        record, fingerprint, record_key_hash = groups[key][0]
        if previous is not None:
            new_active[key] = previous
        transitions.append(
            _transition(
                snapshot=snapshot,
                change_status="unknown",
                record_key=key,
                record_key_hash=record_key_hash,
                record=record if previous is None else previous["record"],
                first_seen_at=(previous or {}).get("first_seen_at"),
                last_seen_at=(previous or {}).get("last_seen_at"),
                fingerprint=fingerprint if previous is None else previous["fingerprint"],
                reason="duplicate_record_key",
            )
        )

    for record, fingerprint in incomplete_records:
        transitions.append(
            _transition(
                snapshot=snapshot,
                change_status="unknown",
                record_key=None,
                record_key_hash=None,
                record=record,
                first_seen_at=None,
                last_seen_at=collected_at,
                fingerprint=fingerprint,
                reason="incomplete_record_key",
            )
        )

    ambiguous_snapshot = bool(incomplete_records or duplicate_keys)
    for key, previous in sorted(active.items()):
        if key in unique_current or key in duplicate_keys:
            continue
        if ambiguous_snapshot:
            new_active[key] = previous
            transitions.append(
                _transition(
                    snapshot=snapshot,
                    change_status="unknown",
                    record_key=key,
                    record_key_hash=previous["record_key_hash"],
                    record=previous["record"],
                    first_seen_at=previous["first_seen_at"],
                    last_seen_at=previous["last_seen_at"],
                    fingerprint=previous["fingerprint"],
                    reason="current_snapshot_has_ambiguous_record_keys",
                )
            )
        else:
            transitions.append(
                _transition(
                    snapshot=snapshot,
                    change_status="disappeared",
                    record_key=key,
                    record_key_hash=previous["record_key_hash"],
                    record=previous["record"],
                    first_seen_at=previous["first_seen_at"],
                    last_seen_at=previous["last_seen_at"],
                    fingerprint=previous["fingerprint"],
                    previous_fingerprint=previous["fingerprint"],
                    reason="absent_from_successful_snapshot",
                )
            )

    reported_count = snapshot.get("provider_reported_count")
    record_count = int(snapshot.get("record_count", 0))
    reported_count_matches = (
        reported_count == record_count if isinstance(reported_count, int) else None
    )
    duplicate_record_rows = sum(len(groups[key]) for key in duplicate_keys)
    quality_passed = (
        reported_count_matches is True
        and not incomplete_records
        and duplicate_record_rows == 0
    )
    transition_counts = Counter(row["change_status"] for row in transitions)
    state.update(
        {
            "record_key_fields": list(key_fields),
            "first_success_at": state.get("first_success_at") or collected_at,
            "last_success_at": collected_at,
            "successful_snapshot_count": int(
                state.get("successful_snapshot_count", 0)
            )
            + 1,
            "active_records": new_active,
        }
    )
    quality = {
        "status": "pass" if quality_passed else "fail",
        "source_status": "success",
        "record_count": record_count,
        "valid_unique_record_count": len(unique_current),
        "incomplete_record_key_rows": len(incomplete_records),
        "duplicate_record_key_rows": duplicate_record_rows,
        "reported_count_matches": reported_count_matches,
        "active_record_count": len(new_active),
        "transition_counts": dict(sorted(transition_counts.items())),
    }
    return state, transitions, quality


def read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON object when it exists."""

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Replace a JSON file only after a complete UTF-8 write."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def append_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Append lifecycle rows without logging request credentials."""

    materialized = [dict(row) for row in rows]
    if not materialized:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in materialized:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
