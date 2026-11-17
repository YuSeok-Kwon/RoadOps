"""Find comparable historical road-weather snapshots and their observed events."""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


FEATURES = {
    "visibility": 20_000.0,
    "road_temp": 40.0,
    "friction": 1.0,
    "water_film": 10.0,
    "snow": 20.0,
}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def summarize_weather(records: Iterable[Mapping[str, Any]]) -> dict[str, float | None]:
    """Return robust island-wide weather features without treating -1 as observed."""

    materialized = list(records)
    summary: dict[str, float | None] = {}
    for field in FEATURES:
        values = [value for row in materialized if (value := _number(row.get(field))) is not None]
        summary[field] = round(statistics.median(values), 3) if values else None
    return summary


def weather_similarity(
    current: Mapping[str, float | None],
    candidate: Mapping[str, float | None],
) -> tuple[float | None, float]:
    """Return a 0-100 similarity and evidence coverage for comparable features."""

    distances: list[float] = []
    for field, scale in FEATURES.items():
        left = current.get(field)
        right = candidate.get(field)
        if left is None or right is None:
            continue
        distances.append(min(1.0, abs(float(left) - float(right)) / scale))
    coverage = len(distances) / len(FEATURES)
    if not distances:
        return None, coverage
    return round((1.0 - statistics.mean(distances)) * 100, 1), round(coverage, 2)


def _read_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _run_key(path: Path, source_id: str) -> str:
    suffix = f"_{source_id}.json"
    return path.name[: -len(suffix)] if path.name.endswith(suffix) else path.stem


def build_historical_similarity(
    snapshot_dir: Path,
    *,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare the latest successful RWIS snapshot with prior archived snapshots."""

    weather_source = "jeju_cits_road_weather"
    event_source = "jeju_cits_road_event"
    weather_paths = sorted(snapshot_dir.glob(f"*_{weather_source}.json"))
    successful: list[tuple[Path, dict[str, Any]]] = []
    for path in weather_paths:
        snapshot = _read_snapshot(path)
        if snapshot.get("status") == "success":
            successful.append((path, snapshot))
    if not successful:
        return [], {
            "status": "unavailable",
            "reason": "no_successful_weather_snapshots",
            "snapshot_count": 0,
            "match_count": 0,
        }

    current_path, current_snapshot = successful[-1]
    current_features = summarize_weather(current_snapshot.get("records", []))
    candidates: list[dict[str, Any]] = []
    for path, snapshot in successful[:-1]:
        run_key = _run_key(path, weather_source)
        event_path = snapshot_dir / f"{run_key}_{event_source}.json"
        event_snapshot = _read_snapshot(event_path) if event_path.exists() else {}
        event_records = (
            list(event_snapshot.get("records", []))
            if event_snapshot.get("status") == "success"
            else []
        )
        features = summarize_weather(snapshot.get("records", []))
        similarity, coverage = weather_similarity(current_features, features)
        if similarity is None:
            continue
        candidates.append(
            {
                "observed_at": snapshot.get("collected_at"),
                "similarity_score": similarity,
                "evidence_coverage_ratio": coverage,
                "event_count": len(event_records),
                "event_link_ids": sorted(
                    {
                        str(row.get("link_id"))
                        for row in event_records
                        if str(row.get("link_id") or "").strip() not in {"", "-1"}
                    }
                ),
                "event_codes": sorted(
                    {
                        str(row.get("code"))
                        for row in event_records
                        if str(row.get("code") or "").strip()
                    }
                ),
                **{f"weather_{key}": value for key, value in features.items()},
            }
        )

    candidates.sort(
        key=lambda row: (
            float(row["similarity_score"]),
            str(row.get("observed_at") or ""),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    selected_times: list[datetime] = []
    for row in candidates:
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        if any(abs((observed - prior).total_seconds()) < 30 * 60 for prior in selected_times):
            continue
        selected.append(row)
        selected_times.append(observed)
        if len(selected) >= limit:
            break

    report = {
        "status": "available" if selected else "limited",
        "current_observed_at": current_snapshot.get("collected_at"),
        "current_features": current_features,
        "snapshot_count": len(successful),
        "candidate_count": len(candidates),
        "match_count": len(selected),
        "minimum_spacing_minutes": 30,
        "limitations": [
            "C-ITS 노면기상에는 제공기관 관측시각이 없어 수집시각을 비교 기준으로 사용했습니다.",
            "현재 저장소에 축적된 수집 이력만 검색하며 장기 계절 대표성을 보장하지 않습니다.",
            "유사도는 가시거리·노면온도·마찰·수막·적설 중 실제 값이 있는 항목만 사용합니다.",
            "동일 시점의 도로 돌발정보 건수는 상관관계이며 인과관계가 아닙니다.",
        ],
        "current_snapshot": current_path.name,
    }
    return selected, report
