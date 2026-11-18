import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from roadops.context_priority import accident_evidence, history_evidence, safety_evidence
from roadops.priority_policy import calculate_priority, policy_id, validate_policy

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/scoring/operator_priority_v0_2.json").read_text())
NOW = datetime(2026, 11, 18, 20, tzinfo=ZoneInfo("Asia/Seoul"))
EVENT = {"event_latitude": 33.5, "event_longitude": 126.5, "effective_link_id": "a"}


def policy(**weights):
    return {**POLICY, "weights": {key: weights.get(key, 0) for key in POLICY["weights"]}}


def inputs(**values):
    return {"factors": [{"key": key, "value": value, "coverage": 1 if value is not None else 0,
                         "status": "available", "description": "test"} for key, value in values.items()]}


def test_selection_weighting_missingness_and_zero_are_distinct():
    selected = policy(event=60, traffic=40)
    result = calculate_priority(inputs(event=50, traffic=100), selected)
    assert result["score"] == 70
    assert sum(row["contribution"] or 0 for row in result["factors"]) == 70
    assert calculate_priority(inputs(event=50, traffic=None), selected)["score"] == 50
    assert calculate_priority(inputs(event=50, traffic=0), selected)["score"] == 30
    assert calculate_priority(inputs(event=None, traffic=100), selected)["score"] is None
    assert calculate_priority(inputs(event=50, traffic=None), {**selected, "method": "complete"})["score"] is None
    assert calculate_priority({**inputs(event=50, traffic=100), "blocked": True}, selected)["score"] is None


def test_hotspot_overlap_only_deducted_when_structural_selected():
    raw = inputs(structural=60, accident_hotspot=80, event=10)
    result = calculate_priority(raw, policy(structural=50, accident_hotspot=50))
    assert result["score"] == 40
    assert next(row for row in result["factors"] if row["key"] == "accident_hotspot")["value"] == 20
    assert calculate_priority(raw, policy(event=50, accident_hotspot=50))["score"] == 45


@pytest.mark.parametrize("weights", [dict(event=-1, traffic=101), dict(event=float("nan")), dict(event=99), dict(city_safety=100)])
def test_invalid_weights_rejected(weights):
    with pytest.raises(ValueError):
        validate_policy(policy(**weights))


def test_changed_policy_has_separate_forecast_identity():
    assert policy_id(policy(event=100)) != policy_id(policy(traffic=100))
    assert policy_id(POLICY) != policy_id({**POLICY, "method": "complete"})


def test_hotspot_uses_actual_road_distance_and_missing_is_not_zero():
    source = {"status": "pass", "generated_at": (NOW - timedelta(days=1)).isoformat(), "records": [
        {"analysis_year": 2025, "latitude": 33.5, "longitude": 126.5, "accident_count": 20, "location_name": "교차로"}]}
    assert accident_evidence(EVENT, {}, source, NOW)["value"] == 50
    assert accident_evidence({**EVENT, "event_longitude": 127}, {}, source, NOW)["value"] == 0
    assert accident_evidence(EVENT, {}, None, NOW)["value"] is None
    assert accident_evidence(EVENT, {}, {**source, "generated_at": (NOW + timedelta(hours=1)).isoformat()}, NOW)["value"] is None


def test_history_excludes_today_future_and_duplicate_snapshots():
    prior = {"observed_at": (NOW - timedelta(days=2)).isoformat(), "event_snapshot_available": True,
             "similarity_score": 100, "evidence_coverage_ratio": 1, "event_link_ids": ["a"]}
    records = [prior, prior, {**prior, "observed_at": NOW.isoformat()}, {**prior, "observed_at": (NOW + timedelta(days=2)).isoformat()}]
    source = {"current_observed_at": NOW.isoformat(), "scoring_records": records}
    result = history_evidence(EVENT, source, NOW, 0)
    assert result["value"] == pytest.approx(100 / 3, abs=1e-6)
    assert len(result["matched_days"]) == 1
    assert history_evidence({"effective_link_id": "b"}, source, NOW, 0)["value"] == 0
    assert history_evidence(EVENT, {**source, "scoring_records": records[2:]}, NOW, 0)["value"] is None


def test_safety_uses_city_scope_and_excludes_traffic_and_fraud():
    source = {"generated_at": NOW.isoformat(), "records": [
        {"analysis_year": 2025, "administrative_city": city,
         "major_categories": [{"crime_group": group, "occurrence_count": count} for group in ("강력범죄", "절도범죄", "폭력범죄")]
            + [{"crime_group": "교통범죄", "occurrence_count": 99999}]}
        for city, count in [("제주시", 30), ("서귀포시", 10)]]}
    assert safety_evidence(EVENT, source, {"a": "제주시"}, NOW)["value"] == 75
    assert safety_evidence(EVENT, source, {}, NOW)["value"] is None
    assert safety_evidence(EVENT, {**source, "records": source["records"][:1]}, {"a": "제주시"}, NOW)["value"] is None
