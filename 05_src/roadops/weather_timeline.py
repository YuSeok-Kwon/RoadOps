"""Normalize KMA observations and forecasts into auditable horizon rows."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
DEFAULT_HORIZONS = (0, 1, 3, 6)
WEATHER_TIMELINE_FIELDS = (
    "weather_timeline_id",
    "generated_at",
    "grid_x",
    "grid_y",
    "horizon_hours",
    "target_at",
    "row_status",
    "observation_status",
    "observed_at",
    "observation_fetched_at",
    "observation_age_minutes",
    "observed_temperature_c",
    "observed_rainfall_1h_raw",
    "observed_precipitation_type",
    "observed_humidity_percent",
    "observed_wind_speed_mps",
    "forecast_status",
    "forecast_source_id",
    "forecast_base_at",
    "forecast_valid_at",
    "forecast_fetched_at",
    "forecast_offset_minutes",
    "forecast_temperature_c",
    "forecast_rainfall_raw",
    "forecast_sky_code",
    "forecast_precipitation_type",
    "forecast_humidity_percent",
    "forecast_wind_speed_mps",
    "quality_flags",
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _kma_datetime(date_value: Any, time_value: Any) -> datetime | None:
    date_text = _text(date_value)
    time_text = _text(time_value)
    if date_text is None or time_text is None:
        return None
    try:
        return datetime.strptime(
            f"{date_text}{time_text.zfill(4)}", "%Y%m%d%H%M"
        ).replace(tzinfo=KST)
    except ValueError:
        return None


def _iso_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _pivot_observation(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    by_time: defaultdict[datetime, dict[str, Any]] = defaultdict(dict)
    for record in records:
        observed_at = _kma_datetime(record.get("baseDate"), record.get("baseTime"))
        category = _text(record.get("category"))
        if observed_at is None or category is None:
            continue
        by_time[observed_at][category] = record.get("obsrValue")
    if not by_time:
        return None
    observed_at = max(by_time)
    values = by_time[observed_at]
    return {
        "observed_at": observed_at,
        "temperature_c": _number(values.get("T1H")),
        "rainfall_1h_raw": _text(values.get("RN1")),
        "precipitation_type": _text(values.get("PTY")),
        "humidity_percent": _number(values.get("REH")),
        "wind_speed_mps": _number(values.get("WSD")),
        "available_categories": sorted(values),
    }


def _forecast_slots(
    records: Iterable[Mapping[str, Any]], *, source_id: str
) -> dict[datetime, dict[str, Any]]:
    by_time: defaultdict[datetime, dict[str, Any]] = defaultdict(dict)
    base_times: dict[datetime, datetime] = {}
    for record in records:
        valid_at = _kma_datetime(record.get("fcstDate"), record.get("fcstTime"))
        base_at = _kma_datetime(record.get("baseDate"), record.get("baseTime"))
        category = _text(record.get("category"))
        if valid_at is None or category is None:
            continue
        by_time[valid_at][category] = record.get("fcstValue")
        if base_at is not None:
            base_times[valid_at] = base_at

    slots: dict[datetime, dict[str, Any]] = {}
    for valid_at, values in by_time.items():
        short = source_id == "kma_short_forecast"
        slots[valid_at] = {
            "source_id": source_id,
            "base_at": base_times.get(valid_at),
            "valid_at": valid_at,
            "temperature_c": _number(values.get("TMP" if short else "T1H")),
            "rainfall_raw": _text(values.get("PCP" if short else "RN1")),
            "sky_code": _text(values.get("SKY")),
            "precipitation_type": _text(values.get("PTY")),
            "humidity_percent": _number(values.get("REH")),
            "wind_speed_mps": _number(values.get("WSD")),
            "available_categories": sorted(values),
        }
    return slots


def _select_forecast(
    target_at: datetime,
    ultra_slots: Mapping[datetime, Mapping[str, Any]],
    short_slots: Mapping[datetime, Mapping[str, Any]],
) -> dict[str, Any] | None:
    if target_at in ultra_slots:
        return dict(ultra_slots[target_at])
    if target_at in short_slots:
        return dict(short_slots[target_at])
    candidates: list[tuple[float, int, datetime, Mapping[str, Any]]] = []
    for priority, slots in ((0, ultra_slots), (1, short_slots)):
        for valid_at, slot in slots.items():
            offset = abs((valid_at - target_at).total_seconds())
            if offset <= 3600:
                candidates.append((offset, priority, valid_at, slot))
    if not candidates:
        return None
    _, _, _, slot = min(candidates, key=lambda item: (item[0], item[1]))
    return dict(slot)


def _timeline_id(grid_x: int, grid_y: int, target_at: datetime) -> str:
    raw = f"{grid_x}|{grid_y}|{target_at.isoformat()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_weather_timeline(
    grids: Iterable[tuple[int, int]],
    *,
    observation_records: Mapping[tuple[int, int], Iterable[Mapping[str, Any]]],
    ultra_forecast_records: Mapping[
        tuple[int, int], Iterable[Mapping[str, Any]]
    ],
    short_forecast_records: Mapping[
        tuple[int, int], Iterable[Mapping[str, Any]]
    ],
    fetch_metadata: Mapping[tuple[str, int, int], Mapping[str, Any]],
    generated_at: datetime,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one observation/forecast evidence row per grid and horizon."""

    now = generated_at.astimezone(KST)
    target_base = now.replace(minute=0, second=0, microsecond=0)
    ordered_grids = sorted(set(grids))
    ordered_horizons = sorted(set(int(value) for value in horizons))
    rows: list[dict[str, Any]] = []

    for grid_x, grid_y in ordered_grids:
        grid = (grid_x, grid_y)
        observation = _pivot_observation(observation_records.get(grid, []))
        ultra_slots = _forecast_slots(
            ultra_forecast_records.get(grid, []),
            source_id="kma_ultra_short_forecast",
        )
        short_slots = _forecast_slots(
            short_forecast_records.get(grid, []),
            source_id="kma_short_forecast",
        )
        observation_fetch = fetch_metadata.get(
            ("kma_ultra_short_nowcast", grid_x, grid_y), {}
        )
        for horizon in ordered_horizons:
            target_at = target_base + timedelta(hours=horizon)
            forecast = _select_forecast(target_at, ultra_slots, short_slots)
            quality_flags: list[str] = []

            observed_at = observation.get("observed_at") if observation else None
            observation_age = (
                round((now - observed_at).total_seconds() / 60, 3)
                if isinstance(observed_at, datetime)
                else None
            )
            observation_status = "matched" if observation else "missing"
            if observation_age is not None and (observation_age < -5 or observation_age > 120):
                observation_status = "stale_or_future"
                quality_flags.append("observation:stale_or_future")
            elif observation is None:
                quality_flags.append("observation:missing")

            forecast_source_id = forecast.get("source_id") if forecast else None
            forecast_fetch = fetch_metadata.get(
                (str(forecast_source_id), grid_x, grid_y), {}
            )
            forecast_valid_at = forecast.get("valid_at") if forecast else None
            forecast_offset = (
                round((forecast_valid_at - target_at).total_seconds() / 60, 3)
                if isinstance(forecast_valid_at, datetime)
                else None
            )
            forecast_status = "matched" if forecast else "missing"
            if forecast is None:
                quality_flags.append("forecast:missing")
            elif forecast_offset is None or abs(forecast_offset) > 60:
                forecast_status = "misaligned"
                quality_flags.append("forecast:misaligned")

            if horizon == 0:
                row_status = (
                    "usable"
                    if observation_status == "matched"
                    else "degraded"
                    if forecast_status == "matched"
                    else "hold"
                )
            else:
                row_status = "usable" if forecast_status == "matched" else "hold"

            row = {
                "weather_timeline_id": _timeline_id(grid_x, grid_y, target_at),
                "generated_at": now.isoformat(),
                "grid_x": grid_x,
                "grid_y": grid_y,
                "horizon_hours": horizon,
                "target_at": target_at.isoformat(),
                "row_status": row_status,
                "observation_status": observation_status,
                "observed_at": observed_at.isoformat() if observed_at else None,
                "observation_fetched_at": observation_fetch.get("fetched_at"),
                "observation_age_minutes": observation_age,
                "observed_temperature_c": observation.get("temperature_c") if observation else None,
                "observed_rainfall_1h_raw": observation.get("rainfall_1h_raw") if observation else None,
                "observed_precipitation_type": observation.get("precipitation_type") if observation else None,
                "observed_humidity_percent": observation.get("humidity_percent") if observation else None,
                "observed_wind_speed_mps": observation.get("wind_speed_mps") if observation else None,
                "forecast_status": forecast_status,
                "forecast_source_id": forecast_source_id,
                "forecast_base_at": (
                    forecast["base_at"].isoformat()
                    if forecast and forecast.get("base_at")
                    else None
                ),
                "forecast_valid_at": (
                    forecast_valid_at.isoformat() if forecast_valid_at else None
                ),
                "forecast_fetched_at": forecast_fetch.get("fetched_at"),
                "forecast_offset_minutes": forecast_offset,
                "forecast_temperature_c": forecast.get("temperature_c") if forecast else None,
                "forecast_rainfall_raw": forecast.get("rainfall_raw") if forecast else None,
                "forecast_sky_code": forecast.get("sky_code") if forecast else None,
                "forecast_precipitation_type": forecast.get("precipitation_type") if forecast else None,
                "forecast_humidity_percent": forecast.get("humidity_percent") if forecast else None,
                "forecast_wind_speed_mps": forecast.get("wind_speed_mps") if forecast else None,
                "quality_flags": "|".join(sorted(set(quality_flags))),
            }
            rows.append(row)

    failed_checks: list[str] = []
    expected_rows = len(ordered_grids) * len(ordered_horizons)
    if len(rows) != expected_rows:
        failed_checks.append("row_count_mismatch")
    if any(set(row) != set(WEATHER_TIMELINE_FIELDS) for row in rows):
        failed_checks.append("schema_mismatch")
    identifiers = [row["weather_timeline_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        failed_checks.append("duplicate_weather_timeline_id")
    if any(row["horizon_hours"] not in ordered_horizons for row in rows):
        failed_checks.append("unexpected_horizon")

    status_counts = Counter(str(row["row_status"]) for row in rows)
    observation_counts = Counter(str(row["observation_status"]) for row in rows)
    forecast_counts = Counter(str(row["forecast_status"]) for row in rows)
    status = "fail" if failed_checks else (
        "pass" if status_counts.get("hold", 0) == 0 else "pass_with_limitations"
    )
    report = {
        "schema_version": 1,
        "status": status,
        "generated_at": now.isoformat(),
        "grid_count": len(ordered_grids),
        "horizons": ordered_horizons,
        "expected_rows": expected_rows,
        "output_rows": len(rows),
        "row_status_counts": dict(sorted(status_counts.items())),
        "observation_status_counts": dict(sorted(observation_counts.items())),
        "forecast_status_counts": dict(sorted(forecast_counts.items())),
        "failed_checks": failed_checks,
    }
    return rows, report
