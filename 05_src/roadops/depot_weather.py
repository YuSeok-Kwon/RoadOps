"""Match depot coordinates to their exact KMA grid without mixing weather sources."""

from __future__ import annotations

from math import isfinite
from typing import Any, Iterable, Mapping

from roadops.spatial import kma_grid_from_wgs84
from roadops.weather_timeline import DEFAULT_HORIZONS

KMA_SOURCE_URL = "https://www.data.go.kr/data/15084084/openapi.do"


def depot_grid(team: Mapping[str, Any]) -> tuple[int, int] | None:
    try:
        lat = float(team["start_latitude"])
        lon = float(team["start_longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    # Do not snap missing, swapped, or non-Jeju coordinates to an unrelated grid.
    if not (isfinite(lat) and isfinite(lon) and 32 <= lat <= 35 and 125 <= lon <= 128):
        return None
    return kma_grid_from_wgs84(lat, lon)


def depot_weather_grids(teams: Iterable[Mapping[str, Any]]) -> set[tuple[int, int]]:
    return {grid for team in teams if (grid := depot_grid(team)) is not None}


def build_depot_weather_rows(
    weather_rows: Iterable[Mapping[str, Any]], teams: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    indexed = {}
    for row in weather_rows:
        try:
            key = tuple(int(row[name]) for name in ("grid_x", "grid_y", "horizon_hours"))
        except (KeyError, TypeError, ValueError):
            continue
        # A source may contain older snapshots; retain the latest collected row.
        if key not in indexed or str(row.get("generated_at", "")) > str(indexed[key].get("generated_at", "")):
            indexed[key] = row
    result = []
    for team in teams:
        grid = depot_grid(team)
        for horizon in DEFAULT_HORIZONS:
            raw = indexed.get((*grid, horizon), {}) if grid else {}
            observed = horizon == 0 and raw.get("observation_status") == "matched"
            forecast = not observed and raw.get("forecast_status") == "matched"
            prefix = "observed" if observed else "forecast"
            usable = observed or forecast
            result.append({
                "team_id": team.get("team_id"),
                "depot_name": team.get("start_location_name"),
                "grid_x": grid[0] if grid else None,
                "grid_y": grid[1] if grid else None,
                "horizon_hours": horizon,
                "status": "usable" if usable else "unavailable",
                "evidence_kind": "observation" if observed else "forecast" if forecast else None,
                "source_id": "kma_ultra_short_nowcast" if observed else raw.get("forecast_source_id") if forecast else None,
                "source_url": KMA_SOURCE_URL,
                "weather_timeline_id": raw.get("weather_timeline_id"),
                "generated_at": raw.get("generated_at"),
                "target_at": raw.get("target_at"),
                "valid_at": raw.get("observed_at" if observed else "forecast_valid_at") if usable else None,
                "fetched_at": raw.get("observation_fetched_at" if observed else "forecast_fetched_at") if usable else None,
                "temperature_c": raw.get(f"{prefix}_temperature_c") if usable else None,
                "precipitation_type": raw.get(f"{prefix}_precipitation_type") if usable else None,
                "rainfall_raw": raw.get("observed_rainfall_1h_raw" if observed else "forecast_rainfall_raw") if usable else None,
                "humidity_percent": raw.get(f"{prefix}_humidity_percent") if usable else None,
                "quality_flags": raw.get("quality_flags") or ("depot_grid_weather_missing" if not raw else ""),
            })
    return result
