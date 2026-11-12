"""Build one-row-per-event RoadOps features without hiding join uncertainty.

결합 불확실성을 숨기지 않고 현장 이벤트 1건당 1개 피처 행을 만듭니다.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from roadops.spatial import kma_grid_from_wgs84, normalize_link_id, parse_point


INTEGRATION_CLASSES = ("exact_link_id", "spatial_fallback", "excluded")
EVENT_TYPE_BY_SOURCE = {
    "jeju_cits_road_event": "road_event",
    "jeju_cits_road_close": "road_close",
    "jeju_cits_road_work": "road_work",
    "jeju_cits_road_weather": "road_weather",
}

INTEGRATED_EVENT_FIELDS = (
    "event_id",
    "source_id",
    "event_type",
    "snapshot_collected_at",
    "snapshot_age_minutes_at_build",
    "source_record_index",
    "integration_class",
    "scoring_eligible",
    "source_link_id",
    "audit_matched_link_id",
    "effective_link_id",
    "match_method",
    "match_distance_meters",
    "nearest_candidate_link_id",
    "nearest_candidate_distance_meters",
    "second_nearest_link_id",
    "second_nearest_distance_meters",
    "distance_margin_meters",
    "match_reason",
    "exclusion_reason",
    "event_latitude",
    "event_longitude",
    "event_heading",
    "event_code",
    "event_text",
    "whole_lane",
    "block_lane",
    "cits_visibility",
    "cits_snow",
    "cits_road_temperature",
    "cits_water_film",
    "cits_friction",
    "road_name",
    "road_rank",
    "lane_count",
    "maximum_speed_limit",
    "road_type",
    "hub_geometry_prior_status",
    "hub_dataset_id",
    "hub_geometry_proxy_class",
    "hub_link_sinuosity",
    "hub_source_period_start_year",
    "hub_source_period_end_year",
    "hub_source_accident_count",
    "hub_fatalities_per_100_accidents",
    "hub_injuries_per_accident",
    "hub_fatality_index_vs_straight",
    "traffic_status",
    "traffic_observed_at",
    "traffic_age_minutes_at_build",
    "traffic_volume",
    "traffic_speed_kph",
    "traffic_occupancy_rate",
    "traffic_travel_time",
    "weather_status",
    "weather_grid_x",
    "weather_grid_y",
    "weather_base_at",
    "weather_forecast_at",
    "weather_valid_time_offset_minutes_at_build",
    "weather_temperature_c",
    "weather_rainfall_1h_raw",
    "weather_sky_code",
    "weather_precipitation_type",
    "weather_humidity_percent",
    "weather_wind_speed_mps",
    "taas_status",
    "taas_risk_value",
    "taas_risk_grade",
    "taas_fetched_at",
    "operational_feature_source_count",
    "quality_flags",
)


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _text(value: Any) -> str | None:
    if not _present(value):
        return None
    return str(value).strip()


def _numeric(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _datetime(value: Any, *, timezone: ZoneInfo | None = None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        parsed = None
        for pattern in (
            "%Y%m%d%H%M%S",
            "%Y%m%d%H%M",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    target_timezone = timezone or ZoneInfo("Asia/Seoul")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=target_timezone)
    return parsed.astimezone(target_timezone)


def _minutes_between(later: datetime, earlier: datetime | None) -> float | None:
    if earlier is None:
        return None
    return round((later - earlier).total_seconds() / 60, 3)


def _event_id(row: Mapping[str, Any]) -> str:
    record = row.get("record") if isinstance(row.get("record"), Mapping) else {}
    identity = [
        row.get("source_id"),
        row.get("snapshot_collected_at"),
        row.get("source_record_index"),
        record.get("ocrr_id"),
        record.get("latitude"),
        record.get("longitude"),
    ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def integration_class(row: Mapping[str, Any]) -> str:
    """Collapse detailed match outcomes into three operational classes."""

    if not bool(row.get("scoring_eligible")):
        return "excluded"
    match = row.get("match")
    method = match.get("method") if isinstance(match, Mapping) else None
    return method if method in {"exact_link_id", "spatial_fallback"} else "excluded"


def latest_traffic_by_link(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Select exactly one latest parseable traffic record per valid link."""

    rows = [dict(row) for row in records]
    selected: dict[str, tuple[datetime, dict[str, Any]]] = {}
    invalid_link_rows = 0
    invalid_timestamp_rows = 0
    duplicate_link_timestamp_rows = 0
    seen_keys: set[tuple[str, str]] = set()
    timestamps: list[datetime] = []
    for row in rows:
        link_id = normalize_link_id(row.get("link_id"))
        if link_id is None:
            invalid_link_rows += 1
            continue
        observed_at = _datetime(row.get("prcn_dt"))
        if observed_at is None:
            invalid_timestamp_rows += 1
            continue
        key = (link_id, observed_at.isoformat())
        if key in seen_keys:
            duplicate_link_timestamp_rows += 1
            continue
        seen_keys.add(key)
        timestamps.append(observed_at)
        normalized = {
            "link_id": link_id,
            "observed_at": observed_at.isoformat(),
            "traffic_volume": _numeric(row.get("tfvl")),
            "speed_kph": _numeric(row.get("sped")),
            "occupancy_rate": _numeric(row.get("ocpy_rate")),
            "travel_time": _numeric(row.get("trvl_hh")),
        }
        previous = selected.get(link_id)
        if previous is None or observed_at > previous[0]:
            selected[link_id] = (observed_at, normalized)
    return (
        {link_id: item[1] for link_id, item in selected.items()},
        {
            "source_rows": len(rows),
            "valid_latest_link_rows": len(selected),
            "invalid_link_rows": invalid_link_rows,
            "invalid_timestamp_rows": invalid_timestamp_rows,
            "duplicate_link_timestamp_rows": duplicate_link_timestamp_rows,
            "earliest_observed_at": min(timestamps).isoformat() if timestamps else None,
            "latest_observed_at": max(timestamps).isoformat() if timestamps else None,
        },
    )


def required_weather_grids(
    joined_records: Iterable[Mapping[str, Any]],
) -> set[tuple[int, int]]:
    """Return KMA grids for every event with a valid Jeju coordinate."""

    grids: set[tuple[int, int]] = set()
    for joined in joined_records:
        record = joined.get("record")
        if not isinstance(record, Mapping):
            continue
        point = parse_point(record.get("latitude"), record.get("longitude"))
        if point is not None:
            grids.add(kma_grid_from_wgs84(point.latitude, point.longitude))
    return grids


def weather_feature_for_grid(
    records: Iterable[Mapping[str, Any]],
    *,
    target_at: datetime,
    fetched_at: str | None,
    grid_x: int,
    grid_y: int,
) -> dict[str, Any]:
    """Select one forecast slot and pivot its categories into one grid feature."""

    target_hour = target_at.astimezone(ZoneInfo("Asia/Seoul")).replace(
        minute=0, second=0, microsecond=0
    )
    by_slot: defaultdict[datetime, dict[str, Any]] = defaultdict(dict)
    base_times: dict[datetime, datetime] = {}
    for row in records:
        forecast_at = _datetime(
            f"{row.get('fcstDate', '')}{str(row.get('fcstTime', '')).zfill(4)}"
        )
        base_at = _datetime(
            f"{row.get('baseDate', '')}{str(row.get('baseTime', '')).zfill(4)}"
        )
        category = _text(row.get("category"))
        if forecast_at is None or category is None:
            continue
        by_slot[forecast_at][category] = row.get("fcstValue")
        if base_at is not None:
            base_times[forecast_at] = base_at

    future_slots = sorted(slot for slot in by_slot if slot >= target_hour)
    selected_at = future_slots[0] if future_slots else max(by_slot, default=None)
    if selected_at is None:
        return {
            "status": "missing_forecast",
            "grid_x": grid_x,
            "grid_y": grid_y,
            "fetched_at": fetched_at,
        }
    categories = by_slot[selected_at]
    return {
        "status": "matched",
        "grid_x": grid_x,
        "grid_y": grid_y,
        "fetched_at": fetched_at,
        "base_at": (
            base_times[selected_at].isoformat()
            if selected_at in base_times
            else None
        ),
        "forecast_at": selected_at.isoformat(),
        "temperature_c": _numeric(categories.get("T1H")),
        "rainfall_1h_raw": _text(categories.get("RN1")),
        "sky_code": _text(categories.get("SKY")),
        "precipitation_type": _text(categories.get("PTY")),
        "humidity_percent": _numeric(categories.get("REH")),
        "wind_speed_mps": _numeric(categories.get("WSD")),
        "available_categories": sorted(categories),
    }


def taas_by_link(
    results: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Normalize one TAAS request result per unique link without filling errors."""

    index: dict[str, dict[str, Any]] = {}
    duplicate_links = 0
    status_counts: Counter[str] = Counter()
    for result in results:
        link_id = normalize_link_id(result.get("link_id"))
        if link_id is None:
            continue
        if link_id in index:
            duplicate_links += 1
            continue
        status = str(result.get("status") or "unknown")
        status_counts[status] += 1
        index[link_id] = {
            "link_id": link_id,
            "status": status,
            "risk_value": _numeric(result.get("risk_value")),
            "risk_grade": _text(result.get("risk_grade")),
            "fetched_at": _text(result.get("fetched_at")),
            "fetch_source": _text(result.get("fetch_source")),
            "provider_result_code": _text(result.get("provider_result_code")),
            "provider_result_message": _text(result.get("provider_result_message")),
        }
    return index, {
        "result_rows": len(index) + duplicate_links,
        "unique_link_rows": len(index),
        "duplicate_link_rows": duplicate_links,
        "status_counts": dict(sorted(status_counts.items())),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _distribution(values: Iterable[float | None]) -> dict[str, Any] | None:
    observed = sorted(float(value) for value in values if value is not None)
    if not observed:
        return None
    return {
        "count": len(observed),
        "minimum": round(observed[0], 3),
        "median": round(median(observed), 3),
        "maximum": round(observed[-1], 3),
    }


def build_integrated_event_table(
    joined_records: Iterable[Mapping[str, Any]],
    reference_links: Iterable[Mapping[str, Any]],
    *,
    traffic_index: Mapping[str, Mapping[str, Any]],
    traffic_profile: Mapping[str, Any],
    weather_features: Mapping[tuple[int, int], Mapping[str, Any]],
    taas_index: Mapping[str, Mapping[str, Any]],
    taas_profile: Mapping[str, Any],
    geometry_prior_index: Mapping[str, Mapping[str, Any]],
    geometry_prior_profile: Mapping[str, Any],
    generated_at: datetime,
    traffic_freshness_max_minutes: float = 30.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the integrated table and report one-to-one join quality."""

    input_rows = [dict(row) for row in joined_records]
    link_index: dict[str, dict[str, Any]] = {}
    reference_duplicate_links = 0
    for raw_link in reference_links:
        link = {str(key).strip().lower(): value for key, value in raw_link.items()}
        link_id = normalize_link_id(link.get("link_id"))
        if link_id is None:
            continue
        if link_id in link_index:
            reference_duplicate_links += 1
            continue
        link_index[link_id] = link

    output_rows: list[dict[str, Any]] = []
    for joined in input_rows:
        record = joined.get("record")
        match = joined.get("match")
        record = dict(record) if isinstance(record, Mapping) else {}
        match = dict(match) if isinstance(match, Mapping) else {}
        classification = integration_class(joined)
        eligible = classification != "excluded"
        audited_link_id = normalize_link_id(match.get("matched_link_id"))
        effective_link_id = audited_link_id if eligible else None
        reference = link_index.get(effective_link_id or "", {})
        snapshot_at = _datetime(joined.get("snapshot_collected_at"))

        geometry_prior = geometry_prior_index.get(effective_link_id or "")
        if not eligible:
            geometry_prior_status = "not_applicable_excluded"
        elif geometry_prior is None:
            geometry_prior_status = "missing_link"
        else:
            geometry_prior_status = str(
                geometry_prior.get("mapping_status") or "unknown"
            )

        traffic = traffic_index.get(effective_link_id or "")
        traffic_at = _datetime(traffic.get("observed_at")) if traffic else None
        traffic_age = _minutes_between(generated_at, traffic_at)
        if not eligible:
            traffic_status = "not_applicable_excluded"
        elif traffic is None:
            traffic_status = "missing_link"
        elif traffic_age is None:
            traffic_status = "invalid_timestamp"
        elif traffic_age < -5:
            traffic_status = "future_timestamp"
        elif traffic_age > traffic_freshness_max_minutes:
            traffic_status = "stale"
        else:
            traffic_status = "matched"

        point = parse_point(record.get("latitude"), record.get("longitude"))
        grid = (
            kma_grid_from_wgs84(point.latitude, point.longitude)
            if point is not None
            else None
        )
        weather = weather_features.get(grid) if grid is not None else None
        if point is None:
            weather_status = "invalid_coordinate"
        elif weather is None:
            weather_status = "missing_grid"
        else:
            weather_status = str(weather.get("status") or "unknown")
        forecast_at = _datetime(weather.get("forecast_at")) if weather else None
        weather_time_offset = (
            round((forecast_at - generated_at).total_seconds() / 60, 3)
            if forecast_at is not None
            else None
        )
        if weather_status == "matched" and (
            weather_time_offset is None or weather_time_offset < -60
        ):
            weather_status = "stale_forecast"

        taas = taas_index.get(effective_link_id or "")
        if not eligible:
            taas_status = "not_applicable_excluded"
        elif taas is None:
            taas_status = "missing_link"
        else:
            taas_status = str(taas.get("status") or "unknown")

        quality_flags = ["cits_source_timestamp_unavailable"]
        if classification == "excluded":
            quality_flags.append(f"excluded:{match.get('reason') or match.get('method')}")
        if geometry_prior_status != "matched":
            quality_flags.append(f"hub_geometry_prior:{geometry_prior_status}")
        if traffic_status != "matched":
            quality_flags.append(f"traffic:{traffic_status}")
        if weather_status != "matched":
            quality_flags.append(f"weather:{weather_status}")
        if taas_status != "ok":
            quality_flags.append(f"taas:{taas_status}")

        operational_feature_source_count = sum(
            (
                traffic_status == "matched",
                weather_status == "matched",
                taas_status == "ok",
            )
        )
        output_rows.append(
            {
                "event_id": _event_id(joined),
                "source_id": joined.get("source_id"),
                "event_type": EVENT_TYPE_BY_SOURCE.get(
                    str(joined.get("source_id")), "unknown"
                ),
                "snapshot_collected_at": joined.get("snapshot_collected_at"),
                "snapshot_age_minutes_at_build": _minutes_between(
                    generated_at, snapshot_at
                ),
                "source_record_index": joined.get("source_record_index"),
                "integration_class": classification,
                "scoring_eligible": eligible,
                "source_link_id": match.get("source_link_id_raw"),
                "audit_matched_link_id": match.get("matched_link_id"),
                "effective_link_id": effective_link_id,
                "match_method": match.get("method"),
                "match_distance_meters": match.get("distance_meters"),
                "nearest_candidate_link_id": match.get("nearest_candidate_link_id"),
                "nearest_candidate_distance_meters": match.get(
                    "nearest_candidate_distance_meters"
                ),
                "second_nearest_link_id": match.get("second_nearest_link_id"),
                "second_nearest_distance_meters": match.get(
                    "second_nearest_distance_meters"
                ),
                "distance_margin_meters": match.get("distance_margin_meters"),
                "match_reason": match.get("reason"),
                "exclusion_reason": (
                    match.get("reason") or match.get("method")
                    if classification == "excluded"
                    else None
                ),
                "event_latitude": record.get("latitude"),
                "event_longitude": record.get("longitude"),
                "event_heading": record.get("heading"),
                "event_code": record.get("code"),
                "event_text": record.get("text"),
                "whole_lane": record.get("whole_lane"),
                "block_lane": record.get("block_lane"),
                "cits_visibility": record.get("visibility"),
                "cits_snow": record.get("snow"),
                "cits_road_temperature": record.get("road_temp"),
                "cits_water_film": record.get("water_film"),
                "cits_friction": record.get("friction"),
                "road_name": reference.get("road_name"),
                "road_rank": reference.get("road_rank"),
                "lane_count": reference.get("lane_count"),
                "maximum_speed_limit": reference.get("maximum_speed_limit"),
                "road_type": reference.get("road_type"),
                "hub_geometry_prior_status": geometry_prior_status,
                "hub_dataset_id": (
                    geometry_prior.get("source_dataset_id")
                    if geometry_prior
                    else None
                ),
                "hub_geometry_proxy_class": (
                    geometry_prior.get("geometry_proxy_class")
                    if geometry_prior
                    else None
                ),
                "hub_link_sinuosity": (
                    _numeric(geometry_prior.get("link_sinuosity"))
                    if geometry_prior
                    else None
                ),
                "hub_source_period_start_year": (
                    geometry_prior.get("source_period_start_year")
                    if geometry_prior
                    else None
                ),
                "hub_source_period_end_year": (
                    geometry_prior.get("source_period_end_year")
                    if geometry_prior
                    else None
                ),
                "hub_source_accident_count": (
                    _numeric(geometry_prior.get("source_accident_count"))
                    if geometry_prior
                    else None
                ),
                "hub_fatalities_per_100_accidents": (
                    _numeric(geometry_prior.get("fatalities_per_100_accidents"))
                    if geometry_prior
                    else None
                ),
                "hub_injuries_per_accident": (
                    _numeric(geometry_prior.get("injuries_per_accident"))
                    if geometry_prior
                    else None
                ),
                "hub_fatality_index_vs_straight": (
                    _numeric(geometry_prior.get("fatality_index_vs_straight"))
                    if geometry_prior
                    else None
                ),
                "traffic_status": traffic_status,
                "traffic_observed_at": traffic.get("observed_at") if traffic else None,
                "traffic_age_minutes_at_build": traffic_age,
                "traffic_volume": traffic.get("traffic_volume") if traffic else None,
                "traffic_speed_kph": traffic.get("speed_kph") if traffic else None,
                "traffic_occupancy_rate": (
                    traffic.get("occupancy_rate") if traffic else None
                ),
                "traffic_travel_time": (
                    traffic.get("travel_time") if traffic else None
                ),
                "weather_status": weather_status,
                "weather_grid_x": grid[0] if grid else None,
                "weather_grid_y": grid[1] if grid else None,
                "weather_base_at": weather.get("base_at") if weather else None,
                "weather_forecast_at": (
                    weather.get("forecast_at") if weather else None
                ),
                "weather_valid_time_offset_minutes_at_build": weather_time_offset,
                "weather_temperature_c": (
                    weather.get("temperature_c") if weather else None
                ),
                "weather_rainfall_1h_raw": (
                    weather.get("rainfall_1h_raw") if weather else None
                ),
                "weather_sky_code": weather.get("sky_code") if weather else None,
                "weather_precipitation_type": (
                    weather.get("precipitation_type") if weather else None
                ),
                "weather_humidity_percent": (
                    weather.get("humidity_percent") if weather else None
                ),
                "weather_wind_speed_mps": (
                    weather.get("wind_speed_mps") if weather else None
                ),
                "taas_status": taas_status,
                "taas_risk_value": taas.get("risk_value") if taas else None,
                "taas_risk_grade": taas.get("risk_grade") if taas else None,
                "taas_fetched_at": taas.get("fetched_at") if taas else None,
                "operational_feature_source_count": (
                    operational_feature_source_count
                ),
                "quality_flags": "|".join(quality_flags),
            }
        )

    event_ids = [str(row["event_id"]) for row in output_rows]
    class_counts = Counter(str(row["integration_class"]) for row in output_rows)
    source_class_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in output_rows:
        source_class_counts[str(row["source_id"])][str(row["integration_class"])] += 1

    eligible_rows = [row for row in output_rows if row["scoring_eligible"]]
    coordinate_rows = [
        row
        for row in output_rows
        if parse_point(row["event_latitude"], row["event_longitude"]) is not None
    ]
    traffic_matched = sum(row["traffic_status"] == "matched" for row in eligible_rows)
    weather_matched = sum(row["weather_status"] == "matched" for row in coordinate_rows)
    taas_matched = sum(row["taas_status"] == "ok" for row in eligible_rows)
    geometry_prior_matched = sum(
        row["hub_geometry_prior_status"] == "matched" for row in eligible_rows
    )
    all_three = sum(
        row["operational_feature_source_count"] == 3 for row in eligible_rows
    )
    all_four = sum(
        row["operational_feature_source_count"] == 3
        and row["hub_geometry_prior_status"] == "matched"
        for row in eligible_rows
    )
    eligible_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["effective_link_id"]
    }
    traffic_matched_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["traffic_status"] == "matched" and row["effective_link_id"]
    }
    taas_matched_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["taas_status"] == "ok" and row["effective_link_id"]
    }
    geometry_prior_matched_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["hub_geometry_prior_status"] == "matched"
        and row["effective_link_id"]
    }
    all_three_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["operational_feature_source_count"] == 3
        and row["effective_link_id"]
    }
    all_four_link_ids = {
        str(row["effective_link_id"])
        for row in eligible_rows
        if row["operational_feature_source_count"] == 3
        and row["hub_geometry_prior_status"] == "matched"
        and row["effective_link_id"]
    }
    required_weather_grid_ids = {
        (str(row["weather_grid_x"]), str(row["weather_grid_y"]))
        for row in coordinate_rows
    }
    matched_weather_grid_ids = {
        (str(row["weather_grid_x"]), str(row["weather_grid_y"]))
        for row in coordinate_rows
        if row["weather_status"] == "matched"
    }
    effective_reference_matches = sum(
        row["effective_link_id"] in link_index for row in eligible_rows
    )

    checks = [
        {
            "check_id": "one_output_row_per_input_event",
            "passed": len(output_rows) == len(input_rows),
            "numerator": len(output_rows),
            "denominator": len(input_rows),
        },
        {
            "check_id": "event_id_uniqueness",
            "passed": len(set(event_ids)) == len(event_ids),
            "numerator": len(set(event_ids)),
            "denominator": len(event_ids),
        },
        {
            "check_id": "integration_class_validity",
            "passed": set(class_counts).issubset(INTEGRATION_CLASSES),
            "observed_values": sorted(class_counts),
            "allowed_values": list(INTEGRATION_CLASSES),
        },
        {
            "check_id": "eligible_effective_link_completeness",
            "passed": all(row["effective_link_id"] for row in eligible_rows),
            "numerator": sum(bool(row["effective_link_id"]) for row in eligible_rows),
            "denominator": len(eligible_rows),
        },
        {
            "check_id": "excluded_effective_link_is_null",
            "passed": all(
                row["effective_link_id"] is None
                for row in output_rows
                if row["integration_class"] == "excluded"
            ),
            "numerator": sum(
                row["effective_link_id"] is None
                for row in output_rows
                if row["integration_class"] == "excluded"
            ),
            "denominator": class_counts["excluded"],
        },
        {
            "check_id": "effective_link_reference_integrity",
            "passed": effective_reference_matches == len(eligible_rows),
            "numerator": effective_reference_matches,
            "denominator": len(eligible_rows),
        },
        {
            "check_id": "reference_link_uniqueness",
            "passed": reference_duplicate_links == 0,
            "duplicate_rows": reference_duplicate_links,
        },
        {
            "check_id": "traffic_latest_link_uniqueness",
            "passed": int(traffic_profile.get("duplicate_link_timestamp_rows") or 0)
            == 0,
            "duplicate_rows": traffic_profile.get("duplicate_link_timestamp_rows"),
        },
        {
            "check_id": "taas_link_uniqueness",
            "passed": int(taas_profile.get("duplicate_link_rows") or 0) == 0,
            "duplicate_rows": taas_profile.get("duplicate_link_rows"),
        },
        {
            "check_id": "hub_geometry_prior_link_uniqueness",
            "passed": int(
                geometry_prior_profile.get("duplicate_link_rows") or 0
            )
            == 0,
            "duplicate_rows": geometry_prior_profile.get("duplicate_link_rows"),
        },
    ]
    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    status = "fail" if failed_checks else "pass_with_limitations"
    issue_samples = [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "integration_class": row["integration_class"],
            "effective_link_id": row["effective_link_id"],
            "hub_geometry_prior_status": row["hub_geometry_prior_status"],
            "traffic_status": row["traffic_status"],
            "weather_status": row["weather_status"],
            "taas_status": row["taas_status"],
            "quality_flags": row["quality_flags"],
        }
        for row in output_rows
        if row["hub_geometry_prior_status"] != "matched"
        or row["traffic_status"] != "matched"
        or row["weather_status"] != "matched"
        or row["taas_status"] != "ok"
    ][:25]
    report = {
        "schema_version": 1,
        "dataset": "roadops_integrated_field_events",
        "generated_at": generated_at.isoformat(),
        "grain": "one row per C-ITS record in one selected source snapshot",
        "status": status,
        "input_event_rows": len(input_rows),
        "output_event_rows": len(output_rows),
        "unique_event_ids": len(set(event_ids)),
        "integration_class_counts": dict(sorted(class_counts.items())),
        "source_class_counts": {
            source_id: dict(sorted(counts.items()))
            for source_id, counts in sorted(source_class_counts.items())
        },
        "reference": {
            "link_rows": len(link_index),
            "duplicate_link_rows": reference_duplicate_links,
        },
        "enrichment_coverage": {
            "traffic": {
                "matched_rows": traffic_matched,
                "eligible_rows": len(eligible_rows),
                "rate": _rate(traffic_matched, len(eligible_rows)),
                "matched_distinct_links": len(traffic_matched_link_ids),
                "eligible_distinct_links": len(eligible_link_ids),
                "distinct_link_rate": _rate(
                    len(traffic_matched_link_ids), len(eligible_link_ids)
                ),
            },
            "weather": {
                "matched_rows": weather_matched,
                "valid_coordinate_rows": len(coordinate_rows),
                "rate": _rate(weather_matched, len(coordinate_rows)),
                "matched_grids": len(matched_weather_grid_ids),
                "required_grids": len(required_weather_grid_ids),
                "grid_rate": _rate(
                    len(matched_weather_grid_ids), len(required_weather_grid_ids)
                ),
            },
            "jeju_datahub_geometry_prior": {
                "matched_rows": geometry_prior_matched,
                "eligible_rows": len(eligible_rows),
                "rate": _rate(geometry_prior_matched, len(eligible_rows)),
                "matched_distinct_links": len(geometry_prior_matched_link_ids),
                "eligible_distinct_links": len(eligible_link_ids),
                "distinct_link_rate": _rate(
                    len(geometry_prior_matched_link_ids),
                    len(eligible_link_ids),
                ),
            },
            "taas": {
                "matched_rows": taas_matched,
                "eligible_rows": len(eligible_rows),
                "rate": _rate(taas_matched, len(eligible_rows)),
                "matched_distinct_links": len(taas_matched_link_ids),
                "eligible_distinct_links": len(eligible_link_ids),
                "distinct_link_rate": _rate(
                    len(taas_matched_link_ids), len(eligible_link_ids)
                ),
            },
            "all_three_features": {
                "matched_rows": all_three,
                "eligible_rows": len(eligible_rows),
                "rate": _rate(all_three, len(eligible_rows)),
                "matched_distinct_links": len(all_three_link_ids),
                "eligible_distinct_links": len(eligible_link_ids),
                "distinct_link_rate": _rate(
                    len(all_three_link_ids), len(eligible_link_ids)
                ),
            },
            "all_four_features": {
                "matched_rows": all_four,
                "eligible_rows": len(eligible_rows),
                "rate": _rate(all_four, len(eligible_rows)),
                "matched_distinct_links": len(all_four_link_ids),
                "eligible_distinct_links": len(eligible_link_ids),
                "distinct_link_rate": _rate(
                    len(all_four_link_ids), len(eligible_link_ids)
                ),
            },
        },
        "profiles": {
            "traffic": dict(traffic_profile),
            "taas": dict(taas_profile),
            "jeju_datahub_geometry_prior": dict(geometry_prior_profile),
            "weather_grid_count": len(weather_features),
        },
        "temporal": {
            "snapshot_age_minutes_at_build": _distribution(
                row["snapshot_age_minutes_at_build"] for row in output_rows
            ),
            "traffic_age_minutes_at_build": _distribution(
                row["traffic_age_minutes_at_build"] for row in output_rows
            ),
            "weather_valid_time_offset_minutes_at_build": _distribution(
                row["weather_valid_time_offset_minutes_at_build"]
                for row in output_rows
            ),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "issue_samples": issue_samples,
        "limitations": [
            "C-ITS records have no provider observation timestamp; snapshot time is ingestion time.",
            "TAAS is structural prior risk and is not a real-time incident measure.",
            "Jeju Data Hub dataset 1027 covers 2018-2020 and supplies conditional crash severity by a RoadOps straight/curve geometry proxy, not per-link crash incidence.",
            "Dataset 1027 is sourced from TAAS; the future scoring rule must prevent independent additive double counting with TAAS link risk.",
            "Missing enrichment values remain null with an explicit status and are never imputed as zero.",
            "Excluded events retain evidence but have no effective_link_id and cannot receive link-level geometry-prior, traffic, or TAAS features.",
        ],
    }
    return output_rows, report
