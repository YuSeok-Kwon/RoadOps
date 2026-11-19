from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.forecast_validation import validate_forecast_snapshots


NOW = datetime(2026, 11, 18, 8, tzinfo=ZoneInfo("Asia/Seoul"))


def _row(horizon, target, generated, score, *, link="link-1", lower=None, upper=None):
    return {
        "horizon_hours": horizon,
        "link_id": link,
        "road_name": "평화로",
        "target_at": target,
        "generated_at": generated,
        "priority_score": score,
        "score_lower_bound": lower if lower is not None else score,
        "score_upper_bound": upper if upper is not None else score,
        "ranking_eligible": True,
        "forecast_semantics": "operational_priority_scenario_not_accident_probability",
    }


def test_validation_matches_future_forecast_and_persistence_baseline():
    snapshots = [
        {
            "snapshot_id": "before",
            "generated_at": "2026-11-18T07:05:00+09:00",
            "rows": [
                _row(0, "2026-11-18T07:00:00+09:00", "2026-11-18T07:05:00+09:00", 40),
                _row(1, "2026-11-18T08:00:00+09:00", "2026-11-18T07:05:00+09:00", 48, lower=43, upper=53),
            ],
        },
        {
            "snapshot_id": "outcome",
            "generated_at": "2026-11-18T08:10:00+09:00",
            "rows": [
                _row(0, "2026-11-18T08:00:00+09:00", "2026-11-18T08:10:00+09:00", 50),
            ],
        },
    ]

    report, matched = validate_forecast_snapshots(snapshots, generated_at=NOW)

    assert report["status"] == "pass_with_limitations"
    assert report["leakage_failure_count"] == 0
    assert len(matched) == 1
    assert matched[0]["forecast_absolute_error"] == 2
    assert matched[0]["persistence_absolute_error"] == 10
    assert matched[0]["interval_contains_outcome"] is True
    one_hour = next(row for row in report["metrics"] if row["horizon_hours"] == 1)
    assert one_hour["validation_status"] == "insufficient_evidence"
    assert one_hour["forecast_mae"] == 2
    assert one_hour["persistence_mae"] == 10
    assert one_hour["mae_improvement"] == 8


def test_validation_uses_earliest_forecast_vintage_only():
    snapshots = [
        {
            "snapshot_id": "early",
            "generated_at": "2026-11-18T07:05:00+09:00",
            "rows": [
                _row(0, "2026-11-18T07:00:00+09:00", "2026-11-18T07:05:00+09:00", 40),
                _row(1, "2026-11-18T08:00:00+09:00", "2026-11-18T07:05:00+09:00", 45),
            ],
        },
        {
            "snapshot_id": "late",
            "generated_at": "2026-11-18T07:35:00+09:00",
            "rows": [
                _row(0, "2026-11-18T07:00:00+09:00", "2026-11-18T07:35:00+09:00", 42),
                _row(1, "2026-11-18T08:00:00+09:00", "2026-11-18T07:35:00+09:00", 50),
            ],
        },
        {
            "snapshot_id": "outcome",
            "generated_at": "2026-11-18T08:05:00+09:00",
            "rows": [_row(0, "2026-11-18T08:00:00+09:00", "2026-11-18T08:05:00+09:00", 50)],
        },
    ]

    _, matched = validate_forecast_snapshots(snapshots, generated_at=NOW)

    assert len(matched) == 1
    assert matched[0]["forecast_score"] == 45
    assert matched[0]["persistence_score"] == 40


def test_validation_fails_future_evidence_leakage():
    forecast = _row(1, "2026-11-18T08:00:00+09:00", "2026-11-18T07:05:00+09:00", 48)
    forecast["weather_fetched_at"] = "2026-11-18T07:10:00+09:00"
    snapshots = [{
        "snapshot_id": "leak",
        "generated_at": "2026-11-18T07:05:00+09:00",
        "rows": [forecast],
    }]

    report, _ = validate_forecast_snapshots(snapshots, generated_at=NOW)

    assert report["status"] == "fail"
    assert report["leakage_failure_count"] == 1
    assert report["leakage_failures"][0]["check"] == "future_weather_fetched_at"


def test_unmatured_three_and_six_hour_forecasts_remain_pending():
    snapshots = [{
        "snapshot_id": "before",
        "generated_at": "2026-11-18T07:05:00+09:00",
        "rows": [
            _row(0, "2026-11-18T07:00:00+09:00", "2026-11-18T07:05:00+09:00", 40),
            _row(3, "2026-11-18T10:00:00+09:00", "2026-11-18T07:05:00+09:00", 50),
            _row(6, "2026-11-18T13:00:00+09:00", "2026-11-18T07:05:00+09:00", 55),
        ],
    }]

    report, matched = validate_forecast_snapshots(snapshots, generated_at=NOW)

    assert matched == []
    status = {row["horizon_hours"]: row["validation_status"] for row in report["metrics"]}
    assert status[3] == "pending"
    assert status[6] == "pending"


def test_validation_does_not_compare_different_operator_weights():
    old = {"snapshot_id": "old", "generated_at": "2026-11-18T07:05:00+09:00", "rows": [
        {**_row(0, "2026-11-18T07:00:00+09:00", "2026-11-18T07:05:00+09:00", 40), "forecast_version": "policy-a"},
        {**_row(1, "2026-11-18T08:00:00+09:00", "2026-11-18T07:05:00+09:00", 48), "forecast_version": "policy-a"}]}
    outcome = {"snapshot_id": "new", "generated_at": "2026-11-18T08:10:00+09:00", "rows": [
        {**_row(0, "2026-11-18T08:00:00+09:00", "2026-11-18T08:10:00+09:00", 80), "forecast_version": "policy-b"}]}
    _, matched = validate_forecast_snapshots([old, outcome], generated_at=NOW)
    assert matched == []
    outcome["rows"][0]["forecast_version"] = "policy-a"
    _, matched = validate_forecast_snapshots([old, outcome], generated_at=NOW)
    assert len(matched) == 1


def test_link_aggregation_keeps_zero_and_separates_policies():
    from roadops.forecast_validation import aggregate_link_forecasts
    base = {"effective_link_id": "road", "horizon_hours": 0, "target_at": "2026-11-18T08:00:00+09:00", "ranking_eligible": True}
    result = aggregate_link_forecasts([{**base, "forecast_priority_score": 0, "forecast_version": "a"},
                                      {**base, "forecast_priority_score": 10, "forecast_version": "b"}])
    assert [(row["forecast_version"], row["priority_score"]) for row in result] == [("a", 0), ("b", 10)]
