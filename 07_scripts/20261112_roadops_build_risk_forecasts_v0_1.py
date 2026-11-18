#!/usr/bin/env python3
"""Build RoadOps 0/1/3/6-hour operational-priority scenarios.

통합 현장 이벤트와 기상 시간축으로 0·1·3·6시간 운영 우선순위 시나리오를 생성합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.quality import load_records  # noqa: E402
from roadops.risk_forecast import (  # noqa: E402
    DEFAULT_HORIZONS,
    RISK_FORECAST_FIELDS,
    build_risk_forecasts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integrated-events",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/integrated_field_events_v0_1/integrated_field_events.csv"
        ),
    )
    parser.add_argument(
        "--weather-timeline",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/weather_timeline_v0_1/weather_timeline.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/risk_forecasts_v0_1",
    )
    parser.add_argument(
        "--gateway-pressure",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/gateway_pressure_v0_1/gateway_pressure.json",
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
    )
    parser.add_argument(
        "--as-of",
        help=(
            "Timezone-aware ISO timestamp for deterministic current-state checks. "
            "Defaults to the latest weather generation or evidence-fetch timestamp."
        ),
    )
    for flag, relative in {
        "scoring-policy": "config/scoring/operator_priority_v0_2.json",
        "accident-hotspots": "02_outputs/data/accident_hotspots_v0_1/accident_hotspots.json",
        "historical-similarity": "02_outputs/data/historical_similarity_v0_1/similar_incidents.json",
        "crime-statistics": "02_outputs/data/crime_statistics_v0_1/crime_statistics.json",
        "link-locations": "02_outputs/data/reverse_geocode_v0_1/link_locations.json",
    }.items():
        parser.add_argument("--" + flag, type=Path, default=PROJECT_ROOT / relative)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _generated_at(value: str | None, weather_rows: list[Mapping[str, Any]]) -> datetime:
    candidate = value
    if candidate is None:
        generated_timestamps = {
            str(row.get("generated_at") or "").strip()
            for row in weather_rows
            if str(row.get("generated_at") or "").strip()
        }
        if len(generated_timestamps) != 1:
            raise SystemExit(
                "Weather timeline must contain exactly one generated_at value, "
                "or pass --as-of explicitly."
            )
        timestamps = set(generated_timestamps)
        for row in weather_rows:
            timestamps.update(
                str(row.get(field) or "").strip()
                for field in ("observation_fetched_at", "forecast_fetched_at")
                if str(row.get(field) or "").strip()
            )
        parsed_timestamps = []
        for timestamp in timestamps:
            try:
                parsed_timestamp = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise SystemExit(f"Invalid weather evidence timestamp: {timestamp}") from exc
            if parsed_timestamp.tzinfo is None:
                raise SystemExit("Weather evidence timestamps must include a UTC offset")
            parsed_timestamps.append(parsed_timestamp)
        candidate = max(parsed_timestamps).isoformat()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"Invalid generated timestamp: {candidate}") from exc
    if parsed.tzinfo is None:
        raise SystemExit("Generated timestamp must include a UTC offset")
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def _write_csv_atomic(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RISK_FORECAST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if any(horizon < 0 for horizon in args.horizons):
        raise SystemExit("--horizons must be non-negative")
    for path in (args.integrated_events, args.weather_timeline):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {_relative(path)}")

    events = load_records(args.integrated_events)
    weather_rows = load_records(args.weather_timeline)
    generated_at = _generated_at(args.as_of, weather_rows)
    def read_optional(path):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not args.scoring_policy.exists():
        raise SystemExit("점수 설정 파일이 없습니다: " + str(args.scoring_policy))
    forecasts, report = build_risk_forecasts(
        events,
        weather_rows,
        generated_at=generated_at,
        horizons=args.horizons,
        scoring_policy=read_optional(args.scoring_policy),
        accident_hotspots=read_optional(args.accident_hotspots),
        historical_similarity=read_optional(args.historical_similarity),
        crime_statistics=read_optional(args.crime_statistics),
        link_cities={str(row["link_id"]): row.get("administrative_city") for row in (read_optional(args.link_locations) or {}).get("records", [])},
        gateway_pressure=(
            json.loads(args.gateway_pressure.read_text(encoding="utf-8"))
            if args.gateway_pressure.exists()
            else None
        ),
    )

    forecast_path = args.output_dir / "risk_forecasts.csv"
    report_path = args.output_dir / "quality_report.json"
    _write_csv_atomic(forecast_path, forecasts)
    report["inputs"] = {
        "integrated_events": _relative(args.integrated_events),
        "weather_timeline": _relative(args.weather_timeline),
        "gateway_pressure": _relative(args.gateway_pressure),
        **{name: _relative(getattr(args, name)) for name in ("scoring_policy", "accident_hotspots", "historical_similarity", "crime_statistics", "link_locations")},
    }
    report["outputs"] = {
        "risk_forecasts": _relative(forecast_path),
        "quality_report": _relative(report_path),
    }
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "horizons": report["horizons"],
        "input_event_rows": report["input_event_rows"],
        "output_rows": report["output_rows"],
        "status_counts": report["status_counts"],
        "scored_rows_by_horizon": report["scored_rows_by_horizon"],
        "score_distributions_by_horizon": report[
            "score_distributions_by_horizon"
        ],
        "gateway_inflow_status": report["gateway_inflow_status"],
        "failed_checks": report["failed_checks"],
        "output": _relative(forecast_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
