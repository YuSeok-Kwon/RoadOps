from pathlib import Path

from roadops.historical_similarity import (
    build_historical_similarity,
    summarize_weather,
    weather_similarity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_weather_summary_ignores_provider_missing_sentinel():
    summary = summarize_weather(
        [
            {"visibility": "1000", "road_temp": "-1", "friction": "0.5"},
            {"visibility": "3000", "road_temp": "8", "friction": "-1"},
        ]
    )
    assert summary["visibility"] == 2000
    assert summary["road_temp"] == 8
    assert summary["friction"] == 0.5


def test_similarity_reports_partial_evidence_coverage():
    score, coverage = weather_similarity(
        {"visibility": 10000, "road_temp": 10, "friction": None, "water_film": None, "snow": None},
        {"visibility": 9000, "road_temp": 12, "friction": None, "water_film": None, "snow": None},
    )
    assert score == 95
    assert coverage == 0.4


def test_repository_snapshots_produce_auditable_matches():
    matches, report = build_historical_similarity(
        PROJECT_ROOT / "02_outputs/data/cits_snapshot_monitor_v0_1/snapshots"
    )
    assert report["status"] == "available"
    assert report["snapshot_count"] >= 2
    assert matches
    assert all("similarity_score" in row for row in matches)
