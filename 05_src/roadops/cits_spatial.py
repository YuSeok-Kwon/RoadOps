"""Audit C-ITS records against a reference road network with safe fallbacks.

C-ITS 레코드를 기준 도로망과 안전하게 공간 결합하고 감사합니다.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from roadops.cits_snapshot import CITS_SNAPSHOT_SOURCE_IDS
from roadops.spatial import RoadLink, audit_event_link_join


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_latest_successful_snapshots(
    snapshot_dir: str | Path,
    *,
    source_ids: Iterable[str] = CITS_SNAPSHOT_SOURCE_IDS,
) -> dict[str, dict[str, Any]]:
    """Load the latest successful, structurally valid snapshot for each source."""

    snapshot_dir = Path(snapshot_dir)
    expected = tuple(source_ids)
    selected: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for path in sorted(snapshot_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("status") != "success":
            continue
        source_id = str(payload.get("source_id") or "")
        collected_at = _parse_datetime(payload.get("collected_at"))
        records = payload.get("records")
        if source_id not in expected or collected_at is None or not isinstance(records, list):
            continue
        previous = selected.get(source_id)
        if previous is None or collected_at > previous[0]:
            payload["_snapshot_file"] = path.name
            selected[source_id] = (collected_at, payload)

    missing = [source_id for source_id in expected if source_id not in selected]
    if missing:
        raise ValueError(f"Missing successful C-ITS snapshots: {missing}")
    return {source_id: selected[source_id][1] for source_id in expected}


def _distribution(values: Iterable[float | None]) -> dict[str, float | int] | None:
    observed = sorted(float(value) for value in values if value is not None)
    if not observed:
        return None
    percentile_index = round(0.95 * (len(observed) - 1))
    return {
        "count": len(observed),
        "minimum": round(observed[0], 3),
        "median": round(median(observed), 3),
        "p95": round(observed[percentile_index], 3),
        "maximum": round(observed[-1], 3),
    }


def audit_cits_spatial_join(
    snapshots: Mapping[str, Mapping[str, Any]],
    links: Mapping[str, RoadLink],
    *,
    network_issues: Iterable[Mapping[str, Any]] = (),
    spatial_threshold_meters: float = 30.0,
    minimum_margin_meters: float = 5.0,
    exact_coordinate_threshold_meters: float = 30.0,
    generated_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a source-segmented audit report and joined record evidence."""

    issue_rows = [dict(issue) for issue in network_issues]
    source_reports: list[dict[str, Any]] = []
    joined_records: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()

    for source_id in CITS_SNAPSHOT_SOURCE_IDS:
        snapshot = snapshots[source_id]
        records = snapshot.get("records", [])
        if not isinstance(records, list):
            raise ValueError(f"Snapshot records must be a list: {source_id}")
        audit = audit_event_link_join(
            records,
            links,
            spatial_fallback_threshold_meters=spatial_threshold_meters,
            spatial_fallback_min_margin_meters=minimum_margin_meters,
            exact_coordinate_threshold_meters=exact_coordinate_threshold_meters,
        )
        audit_dict = audit.to_dict()
        matches = [asdict(match) for match in audit.matches]
        method_counts = Counter(match["method"] for match in matches)
        eligible_count = 0
        for record_index, (record, match) in enumerate(zip(records, matches)):
            scoring_eligible = match["method"] in {
                "exact_link_id",
                "spatial_fallback",
            } and match["coordinate_consistent"] is not False
            if scoring_eligible:
                eligible_count += 1
            joined_records.append(
                {
                    "source_id": source_id,
                    "snapshot_collected_at": snapshot.get("collected_at"),
                    "snapshot_file": snapshot.get("_snapshot_file"),
                    "source_record_index": record_index,
                    "scoring_eligible": scoring_eligible,
                    "record": record,
                    "match": match,
                }
            )

        fallback_population = audit.total_events - audit.exact_matches
        source_report = {
            "source_id": source_id,
            "snapshot_collected_at": snapshot.get("collected_at"),
            "snapshot_file": snapshot.get("_snapshot_file"),
            "record_count": audit.total_events,
            "exact_matches": audit.exact_matches,
            "spatial_matches": audit.spatial_matches,
            "ambiguous_events": audit.ambiguous_events,
            "unmatched_events": audit.unmatched_events,
            "invalid_events": audit.invalid_events,
            "coordinate_conflicts": audit.coordinate_conflicts,
            "scoring_eligible_records": eligible_count,
            "exact_match_rate": audit_dict["exact_match_rate"],
            "combined_match_rate": audit_dict["combined_match_rate"],
            "scoring_eligible_rate": (
                eligible_count / audit.total_events if audit.total_events else None
            ),
            "spatial_match_rate_among_fallback_population": (
                audit.spatial_matches / fallback_population
                if fallback_population
                else None
            ),
            "method_counts": dict(sorted(method_counts.items())),
            "exact_coordinate_distance_meters": _distribution(
                match["distance_meters"]
                for match in matches
                if match["method"] == "exact_link_id"
            ),
            "spatial_distance_meters": _distribution(
                match["distance_meters"]
                for match in matches
                if match["method"] == "spatial_fallback"
            ),
            "ambiguous_nearest_distance_meters": _distribution(
                match["distance_meters"]
                for match in matches
                if match["method"] == "ambiguous"
            ),
            "spatial_distance_margin_meters": _distribution(
                match["distance_margin_meters"]
                for match in matches
                if match["method"] == "spatial_fallback"
            ),
        }
        source_reports.append(source_report)
        for field in (
            "record_count",
            "exact_matches",
            "spatial_matches",
            "ambiguous_events",
            "unmatched_events",
            "invalid_events",
            "coordinate_conflicts",
            "scoring_eligible_records",
        ):
            totals[field] += int(source_report[field])

    total_records = totals["record_count"]
    excluded_records = total_records - totals["scoring_eligible_records"]
    issue_counts = Counter(str(issue.get("reason")) for issue in issue_rows)
    status = "pass"
    if issue_rows:
        status = "fail"
    elif excluded_records:
        status = "review"

    report = {
        "schema_version": 1,
        "dataset": "jeju_cits_spatial_join_audit",
        "generated_at": generated_at.isoformat(),
        "status": status,
        "grain": "one C-ITS record per source snapshot, matched to at most one reference road link",
        "reference_link_count": len(links),
        "network_issue_count": len(issue_rows),
        "network_issue_counts": dict(sorted(issue_counts.items())),
        "thresholds": {
            "spatial_distance_max_meters": spatial_threshold_meters,
            "nearest_candidate_margin_min_meters": minimum_margin_meters,
            "exact_link_coordinate_distance_max_meters": exact_coordinate_threshold_meters,
        },
        "totals": {
            **dict(totals),
            "excluded_records": excluded_records,
            "scoring_eligible_rate": (
                totals["scoring_eligible_records"] / total_records
                if total_records
                else None
            ),
        },
        "sources": source_reports,
        "network_issue_samples": issue_rows[:25],
        "decision_rules": [
            "A valid source link ID is preferred and its coordinate distance is audited.",
            "A spatial fallback is accepted only inside the distance threshold and outside the ambiguity margin.",
            "Ambiguous, unmatched, invalid, and coordinate-conflicting records are excluded from scoring.",
        ],
        "limitations": [
            "C-ITS records do not provide a source observation timestamp; snapshot_collected_at is ingestion time.",
            "A nearest road link is a geometric association, not proof of travel direction or provider intent.",
            "Records excluded from scoring remain in joined evidence for operator review.",
        ],
    }
    return report, joined_records
