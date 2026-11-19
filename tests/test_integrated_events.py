from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.integrated_events import (
    INTEGRATED_EVENT_FIELDS,
    build_integrated_event_table,
    integration_class,
    latest_traffic_by_link,
    required_weather_grids,
    taas_by_link,
    weather_feature_for_grid,
)
from roadops.spatial import kma_grid_from_wgs84


NOW = datetime(2026, 11, 12, 14, 10, tzinfo=ZoneInfo("Asia/Seoul"))


def _joined(
    *,
    index: int,
    method: str,
    eligible: bool,
    matched_link_id: str | None,
    latitude: float = 33.3265,
    longitude: float = 126.8332,
    reason: str | None = None,
):
    return {
        "source_id": "jeju_cits_road_event",
        "snapshot_collected_at": "2026-11-12T14:00:00+09:00",
        "source_record_index": index,
        "scoring_eligible": eligible,
        "record": {
            "ocrr_id": f"event-{index}",
            "link_id": matched_link_id or "-1",
            "latitude": latitude,
            "longitude": longitude,
            "code": 534,
        },
        "match": {
            "method": method,
            "source_link_id_raw": matched_link_id or "-1",
            "matched_link_id": matched_link_id,
            "distance_meters": 2.0,
            "nearest_candidate_link_id": matched_link_id,
            "nearest_candidate_distance_meters": 2.0,
            "second_nearest_link_id": None,
            "second_nearest_distance_meters": None,
            "distance_margin_meters": 8.0,
            "reason": reason,
        },
    }


def test_integration_class_collapses_unsafe_matches_to_excluded():
    exact = _joined(
        index=0,
        method="exact_link_id",
        eligible=True,
        matched_link_id="4050000001",
    )
    spatial = _joined(
        index=1,
        method="spatial_fallback",
        eligible=True,
        matched_link_id="4050000002",
    )
    conflict = _joined(
        index=2,
        method="exact_link_id",
        eligible=False,
        matched_link_id="4050000001",
        reason="coordinate_exceeds_exact_link_threshold",
    )

    assert integration_class(exact) == "exact_link_id"
    assert integration_class(spatial) == "spatial_fallback"
    assert integration_class(conflict) == "excluded"


def test_latest_traffic_keeps_one_latest_row_per_link():
    index, profile = latest_traffic_by_link(
        [
            {
                "link_id": "4050000001",
                "prcn_dt": "20261112130000",
                "tfvl": "3",
                "sped": "20",
                "ocpy_rate": "2",
                "trvl_hh": "12",
            },
            {
                "link_id": "4050000001",
                "prcn_dt": "20261112140000",
                "tfvl": "5",
                "sped": "30",
                "ocpy_rate": "4",
                "trvl_hh": "9",
            },
            {"link_id": "bad", "prcn_dt": "20261112140000"},
        ]
    )

    assert len(index) == 1
    assert index["4050000001"]["traffic_volume"] == 5.0
    assert index["4050000001"]["speed_kph"] == 30.0
    assert profile["source_rows"] == 3
    assert profile["invalid_link_rows"] == 1


def test_weather_feature_selects_current_hour_and_pivots_categories():
    records = [
        {
            "baseDate": "20261112",
            "baseTime": "1300",
            "fcstDate": "20261112",
            "fcstTime": "1400",
            "category": category,
            "fcstValue": value,
            "nx": 58,
            "ny": 34,
        }
        for category, value in {
            "T1H": "18",
            "RN1": "강수없음",
            "SKY": "3",
            "PTY": "0",
            "REH": "70",
            "WSD": "2.5",
        }.items()
    ]

    feature = weather_feature_for_grid(
        records,
        target_at=NOW,
        fetched_at="2026-11-12T14:05:00+09:00",
        grid_x=58,
        grid_y=34,
    )

    assert feature["status"] == "matched"
    assert feature["forecast_at"] == "2026-11-12T14:00:00+09:00"
    assert feature["temperature_c"] == 18.0
    assert feature["rainfall_1h_raw"] == "강수없음"
    assert feature["humidity_percent"] == 70.0


def test_integrated_table_preserves_grain_and_blocks_excluded_link_features():
    joined = [
        _joined(
            index=0,
            method="exact_link_id",
            eligible=True,
            matched_link_id="4050000001",
        ),
        _joined(
            index=1,
            method="spatial_fallback",
            eligible=True,
            matched_link_id="4050000002",
            latitude=33.3275,
            longitude=126.8342,
        ),
        _joined(
            index=2,
            method="exact_link_id",
            eligible=False,
            matched_link_id="4050000001",
            reason="coordinate_exceeds_exact_link_threshold",
        ),
    ]
    reference = [
        {"link_id": "4050000001", "road_name": "제주로", "road_rank": "107"},
        {"link_id": "4050000002", "road_name": "중산간로", "road_rank": "106"},
    ]
    traffic_index, traffic_profile = latest_traffic_by_link(
        [
            {
                "link_id": "4050000001",
                "prcn_dt": "20261112140000",
                "tfvl": 7,
                "sped": 35,
                "ocpy_rate": 2,
                "trvl_hh": 8,
            }
        ]
    )
    grids = required_weather_grids(joined)
    weather_features = {
        grid: {
            "status": "matched",
            "grid_x": grid[0],
            "grid_y": grid[1],
            "base_at": "2026-11-12T13:00:00+09:00",
            "forecast_at": "2026-11-12T14:00:00+09:00",
            "temperature_c": 18.0,
        }
        for grid in grids
    }
    taas_index, taas_profile = taas_by_link(
        [
            {
                "link_id": "4050000001",
                "status": "ok",
                "risk_value": "12.5",
                "risk_grade": "02",
                "fetched_at": "2026-11-12T14:05:00+09:00",
            },
            {"link_id": "4050000002", "status": "api_error"},
        ]
    )
    geometry_prior_index = {
        "4050000001": {
            "mapping_status": "matched",
            "source_dataset_id": "1027",
            "geometry_proxy_class": "straight",
            "link_sinuosity": "1.0",
            "source_period_start_year": "2018",
            "source_period_end_year": "2020",
            "source_accident_count": "11441",
            "fatalities_per_100_accidents": "1.608251",
            "injuries_per_accident": "1.53317",
            "fatality_index_vs_straight": "1.0",
        },
        "4050000002": {
            "mapping_status": "matched",
            "source_dataset_id": "1027",
            "geometry_proxy_class": "curve",
            "link_sinuosity": "1.1",
            "source_period_start_year": "2018",
            "source_period_end_year": "2020",
            "source_accident_count": "1068",
            "fatalities_per_100_accidents": "2.808989",
            "injuries_per_accident": "1.674157",
            "fatality_index_vs_straight": "1.746611",
        },
    }

    rows, report = build_integrated_event_table(
        joined,
        reference,
        traffic_index=traffic_index,
        traffic_profile=traffic_profile,
        weather_features=weather_features,
        taas_index=taas_index,
        taas_profile=taas_profile,
        geometry_prior_index=geometry_prior_index,
        geometry_prior_profile={
            "duplicate_link_rows": 0,
            "unique_link_rows": 2,
        },
        generated_at=NOW,
    )

    assert len(rows) == len(joined) == 3
    assert all(set(row) == set(INTEGRATED_EVENT_FIELDS) for row in rows)
    assert len({row["event_id"] for row in rows}) == 3
    assert report["failed_checks"] == []
    assert report["integration_class_counts"] == {
        "exact_link_id": 1,
        "excluded": 1,
        "spatial_fallback": 1,
    }
    excluded = next(row for row in rows if row["integration_class"] == "excluded")
    assert excluded["audit_matched_link_id"] == "4050000001"
    assert excluded["effective_link_id"] is None
    assert excluded["hub_geometry_prior_status"] == "not_applicable_excluded"
    assert excluded["traffic_status"] == "not_applicable_excluded"
    assert excluded["taas_status"] == "not_applicable_excluded"
    assert excluded["weather_status"] == "matched"
    assert report["enrichment_coverage"]["traffic"]["matched_rows"] == 1
    assert report["enrichment_coverage"]["taas"]["matched_rows"] == 1
    assert (
        report["enrichment_coverage"]["jeju_datahub_geometry_prior"][
            "matched_rows"
        ]
        == 2
    )
    assert report["enrichment_coverage"]["traffic"]["distinct_link_rate"] == 0.5
    assert report["enrichment_coverage"]["taas"]["distinct_link_rate"] == 0.5


def test_integrated_table_marks_stale_and_future_traffic_without_zero_filling():
    joined = [
        _joined(
            index=0,
            method="exact_link_id",
            eligible=True,
            matched_link_id="4050000001",
        ),
        _joined(
            index=1,
            method="exact_link_id",
            eligible=True,
            matched_link_id="4050000002",
        ),
    ]
    reference = [
        {"link_id": "4050000001"},
        {"link_id": "4050000002"},
    ]
    traffic_index, traffic_profile = latest_traffic_by_link(
        [
            {"link_id": "4050000001", "prcn_dt": "20261112130000"},
            {"link_id": "4050000002", "prcn_dt": "20261112150000"},
        ]
    )
    taas_index, taas_profile = taas_by_link([])

    rows, _ = build_integrated_event_table(
        joined,
        reference,
        traffic_index=traffic_index,
        traffic_profile=traffic_profile,
        weather_features={},
        taas_index=taas_index,
        taas_profile=taas_profile,
        geometry_prior_index={},
        geometry_prior_profile={"duplicate_link_rows": 0},
        generated_at=NOW,
    )

    assert rows[0]["traffic_status"] == "stale"
    assert rows[1]["traffic_status"] == "future_timestamp"
    assert rows[0]["traffic_volume"] is None
    assert rows[1]["traffic_volume"] is None


def test_kma_grid_requirements_ignore_invalid_coordinates():
    valid = _joined(
        index=0,
        method="spatial_fallback",
        eligible=True,
        matched_link_id="4050000001",
    )
    invalid = _joined(
        index=1,
        method="invalid",
        eligible=False,
        matched_link_id=None,
        latitude=90.0,
        longitude=180.0,
    )

    assert required_weather_grids([valid, invalid]) == {
        kma_grid_from_wgs84(33.3265, 126.8332)
    }
