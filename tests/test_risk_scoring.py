from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadops.risk_scoring import (
    COMPONENT_WEIGHTS,
    parse_rainfall_millimeters,
    score_risk_event,
    score_risk_events,
    score_structural_component,
)


NOW = datetime(2026, 11, 12, 14, 30, tzinfo=ZoneInfo("Asia/Seoul"))


def _complete_row(**overrides):
    row = {
        "event_id": "event-1",
        "source_id": "jeju_cits_road_event",
        "event_type": "road_event",
        "event_code": "534",
        "snapshot_collected_at": "2026-11-12T14:20:00+09:00",
        "integration_class": "exact_link_id",
        "scoring_eligible": "True",
        "effective_link_id": "4050000001",
        "road_name": "평화로",
        "hub_geometry_prior_status": "matched",
        "hub_fatality_index_vs_straight": "1.746611",
        "traffic_status": "matched",
        "traffic_observed_at": "2026-11-12T14:25:00+09:00",
        "traffic_speed_kph": "80",
        "traffic_occupancy_rate": "30",
        "maximum_speed_limit": "80",
        "weather_status": "matched",
        "weather_forecast_at": "2026-11-12T14:00:00+09:00",
        "weather_precipitation_type": "1",
        "weather_rainfall_1h_raw": "2.0mm",
        "weather_wind_speed_mps": "4",
        "cits_visibility": "",
        "cits_snow": "",
        "cits_road_temperature": "",
        "cits_water_film": "",
        "cits_friction": "",
        "taas_status": "ok",
        "taas_risk_grade": "03",
        "quality_flags": "",
    }
    row.update(overrides)
    return row


def test_complete_exact_event_is_usable_and_reconciles_components():
    scored = score_risk_event(_complete_row(), generated_at=NOW)

    assert scored["scoring_status"] == "usable"
    assert scored["score_available"] is True
    assert scored["evidence_coverage_ratio"] == 1.0
    assert scored["risk_score_lower_bound"] == scored["risk_score"]
    assert scored["risk_score_upper_bound"] == scored["risk_score"]
    contributions = sum(
        scored[field]
        for field in (
            "event_contribution",
            "structural_contribution",
            "weather_road_contribution",
            "traffic_contribution",
        )
    )
    assert abs(contributions - scored["risk_score"]) <= 0.01


def test_risk_levels_are_operational_priority_bands():
    low = score_risk_event(
        _complete_row(
            source_id="jeju_cits_road_weather",
            event_type="road_weather",
            weather_precipitation_type="0",
            weather_rainfall_1h_raw="강수없음",
            weather_wind_speed_mps="1",
            cits_visibility="20000",
            cits_road_temperature="15",
            cits_friction="0.9",
            cits_snow="0",
            cits_water_film="0",
            traffic_speed_kph="20",
            maximum_speed_limit="80",
            traffic_occupancy_rate="0",
            taas_risk_grade="01",
            hub_fatality_index_vs_straight="1.0",
        ),
        generated_at=NOW,
    )
    moderate = score_risk_event(_complete_row(), generated_at=NOW)

    assert low["risk_score"] < 25
    assert low["risk_level"] == "low"
    assert moderate["risk_score"] >= 25
    assert moderate["risk_level"] in {"moderate", "high", "critical"}


def test_missing_traffic_expands_interval_instead_of_imputing_zero():
    row = _complete_row(
        traffic_status="missing_link",
        traffic_observed_at="",
        traffic_speed_kph="",
        traffic_occupancy_rate="",
    )

    scored = score_risk_event(row, generated_at=NOW)

    assert scored["scoring_status"] == "degraded"
    assert scored["traffic_score"] is None
    assert scored["traffic_contribution"] is None
    assert scored["evidence_coverage_ratio"] == 0.85
    assert scored["risk_score_lower_bound"] < scored["risk_score"]
    assert scored["risk_score"] < scored["risk_score_upper_bound"]


def test_spatial_fallback_requires_operator_review():
    scored = score_risk_event(
        _complete_row(integration_class="spatial_fallback"), generated_at=NOW
    )

    assert scored["scoring_status"] == "degraded"
    assert scored["requires_operator_review"] is True
    assert "integration:spatial_fallback" in scored["quality_flags"]


def test_provider_timestamp_gap_degrades_otherwise_complete_score():
    scored = score_risk_event(
        _complete_row(quality_flags="cits_source_timestamp_unavailable"),
        generated_at=NOW,
    )

    assert scored["scoring_status"] == "degraded"
    assert scored["score_available"] is True


def test_excluded_and_stale_events_are_held_without_scores():
    excluded = score_risk_event(
        _complete_row(
            integration_class="excluded",
            scoring_eligible="False",
            effective_link_id="",
        ),
        generated_at=NOW,
    )
    stale = score_risk_event(
        _complete_row(snapshot_collected_at="2026-11-12T12:00:00+09:00"),
        generated_at=NOW,
    )

    assert excluded["scoring_status"] == "hold"
    assert excluded["risk_score"] is None
    assert stale["scoring_status"] == "hold"
    assert stale["risk_score"] is None


def test_future_persistence_scenario_is_explicitly_degraded_not_silently_fresh():
    future = score_risk_event(
        _complete_row(snapshot_collected_at="2026-11-12T10:00:00+09:00"),
        generated_at=NOW,
        allow_event_persistence_scenario=True,
    )

    assert future["scoring_status"] == "degraded"
    assert future["score_available"] is True
    assert future["snapshot_age_minutes_at_scoring"] == 270.0
    assert "scenario:event_persistence_without_end_time" in future["quality_flags"]

    missing = score_risk_event(
        _complete_row(snapshot_collected_at=""),
        generated_at=NOW,
        allow_event_persistence_scenario=True,
    )
    assert missing["scoring_status"] == "hold"
    assert missing["score_available"] is False


def test_insufficient_evidence_is_held_not_ranked_low():
    row = _complete_row(
        hub_geometry_prior_status="missing_link",
        hub_fatality_index_vs_straight="",
        taas_status="api_error",
        taas_risk_grade="",
        traffic_status="missing_link",
        traffic_observed_at="",
        traffic_speed_kph="",
        traffic_occupancy_rate="",
        weather_status="missing",
        weather_forecast_at="",
        weather_precipitation_type="",
        weather_rainfall_1h_raw="",
        weather_wind_speed_mps="",
    )

    scored = score_risk_event(row, generated_at=NOW)

    assert scored["scoring_status"] == "hold"
    assert scored["risk_score"] is None
    assert scored["quality_flags"] == "hold:insufficient_evidence_coverage"


def test_structural_sources_share_one_bounded_component():
    component = score_structural_component(_complete_row())

    assert component["status"] == "available"
    assert component["coverage"] == 1.0
    assert 0 <= component["score"] <= 100
    assert component["details"]["double_count_rule"].startswith("bounded_70_30")
    assert COMPONENT_WEIGHTS["structural"] == 25.0


def test_partial_structural_evidence_preserves_uncertainty():
    component = score_structural_component(
        _complete_row(taas_status="api_error", taas_risk_grade="")
    )

    assert component["status"] == "partial"
    assert component["coverage"] == 0.3
    assert component["lower"] < component["score"] < component["upper"]


def test_road_weather_rows_do_not_receive_discrete_event_weight():
    scored = score_risk_event(
        _complete_row(
            source_id="jeju_cits_road_weather",
            event_type="road_weather",
            cits_visibility="80",
            cits_road_temperature="1",
            cits_friction="0.4",
            cits_snow="0",
            cits_water_film="0",
        ),
        generated_at=NOW,
    )

    assert scored["event_component_status"] == "not_applicable"
    assert scored["event_weight"] is None
    assert scored["expected_weight"] == 65.0
    assert scored["weather_road_score"] == 100.0
    assert "assumption:cits_visibility_unit_meters" in scored["quality_flags"]


def test_minus_one_road_temperature_is_missing_sentinel_not_freezing():
    scored = score_risk_event(
        _complete_row(
            source_id="jeju_cits_road_weather",
            event_type="road_weather",
            weather_precipitation_type="0",
            weather_rainfall_1h_raw="강수없음",
            weather_wind_speed_mps="1",
            cits_visibility="20000",
            cits_road_temperature="-1",
            cits_friction="-1",
            cits_snow="-1",
            cits_water_film="-1",
        ),
        generated_at=NOW,
    )

    assert scored["weather_road_score"] == 0.0
    assert scored["weather_road_driver"] != "cits_road_temperature"


def test_score_batch_is_deterministic_and_reports_duplicate_ids():
    first_rows, first_report = score_risk_events(
        [_complete_row()], generated_at=NOW
    )
    second_rows, second_report = score_risk_events(
        [_complete_row()], generated_at=NOW
    )

    assert first_rows == second_rows
    assert first_report == second_report

    _, duplicate_report = score_risk_events(
        [_complete_row(), _complete_row()], generated_at=NOW
    )
    assert "event_id_uniqueness" in duplicate_report["failed_checks"]


def test_rainfall_parser_preserves_no_rain_and_less_than_one():
    assert parse_rainfall_millimeters("강수없음") == 0.0
    assert parse_rainfall_millimeters("1mm 미만") == 0.5
    assert parse_rainfall_millimeters("7.5mm") == 7.5
    assert parse_rainfall_millimeters("미상") is None
