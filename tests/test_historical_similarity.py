import json
from pathlib import Path

from roadops.historical_similarity import (
    build_historical_similarity,
    event_locations,
    summarize_weather,
    weather_similarity,
)


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


def test_event_locations_preserve_coordinates_and_group_codes():
    locations = event_locations(
        [
            {"link_id": "road-1", "longitude": 126.4, "latitude": 33.4, "code": 534},
            {"link_id": "road-1", "longitude": 126.4, "latitude": 33.4, "code": 258},
        ]
    )
    assert locations == [
        {
            "link_id": "road-1",
            "longitude": 126.4,
            "latitude": 33.4,
            "event_codes": ["258", "534"],
        }
    ]


def test_saved_snapshots_produce_auditable_matches(tmp_path: Path):
    # Synthetic files exercise the real archive reader without private API captures.
    snapshots = {
        "20261119T100000_jeju_cits_road_weather.json": {
            "status": "success", "collected_at": "2026-11-19T10:00:00+09:00",
            "records": [{"visibility": 9000, "road_temp": 12}],
        },
        "20261119T110000_jeju_cits_road_weather.json": {
            "status": "success", "collected_at": "2026-11-19T11:00:00+09:00",
            "records": [{"visibility": 10000, "road_temp": 10}],
        },
        "20261119T120000_jeju_cits_road_weather.json": {
            "status": "error", "collected_at": "2026-11-19T12:00:00+09:00",
            "records": [],
        },
        "20261119T100000_jeju_cits_road_event.json": {
            "status": "success", "records": [
                {"link_id": "road-1", "longitude": 126.4, "latitude": 33.4, "code": 534},
            ],
        },
    }
    for name, payload in snapshots.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    matches, report = build_historical_similarity(tmp_path)
    assert report["status"] == "available"
    assert report["snapshot_count"] == 2
    assert report["current_observed_at"] == "2026-11-19T11:00:00+09:00"
    assert len(matches) == 1
    assert matches[0]["similarity_score"] == 95
    assert matches[0]["evidence_coverage_ratio"] == 0.4
    assert matches[0]["event_snapshot_available"] is True
    assert matches[0]["event_locations"] == [
        {"link_id": "road-1", "longitude": 126.4, "latitude": 33.4, "event_codes": ["534"]}
    ]
