#!/usr/bin/env python3
"""Build an auditable C-ITS event table enriched with traffic, weather, and TAAS.

C-ITS 현장 이벤트에 교통량·날씨·TAAS 위험지수를 감사 가능하게 결합합니다.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.integrated_events import (  # noqa: E402
    INTEGRATED_EVENT_FIELDS,
    build_integrated_event_table,
    latest_traffic_by_link,
    required_weather_grids,
    taas_by_link,
    weather_feature_for_grid,
)
from roadops.jeju_datahub_accidents import (  # noqa: E402
    index_link_geometry_priors,
)
from roadops.live import LiveFetchError, fetch_json_payload  # noqa: E402
from roadops.probe import extract_records, load_source_specs  # noqa: E402
from roadops.quality import load_records  # noqa: E402
from roadops.spatial import normalize_link_id  # noqa: E402
from roadops.taas_audit import (  # noqa: E402
    fetch_taas_link_risk,
    taas_linestring_from_wkt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--joined-records",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/cits_spatial_join_audit_v0_1/joined_records.jsonl"
        ),
    )
    parser.add_argument(
        "--reference-links",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/interim/molit_nodelink_jeju_20261014/jeju_links.csv"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config/data_sources.json",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / "config/.env",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/integrated_field_events_v0_1",
    )
    parser.add_argument(
        "--geometry-priors",
        type=Path,
        default=(
            PROJECT_ROOT
            / "02_outputs/data/jeju_datahub_geometry_severity_prior_v0_1"
            / "link_geometry_severity_priors.csv"
        ),
    )
    parser.add_argument(
        "--taas-cache-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/taas_cache",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--taas-request-delay", type=float, default=0.1)
    parser.add_argument("--refresh-enrichments", action="store_true")
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Allow the provider's documented HTTP traffic endpoint.",
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read_env_value(path: Path, name: str) -> str | None:
    environment_value = os.environ.get(name)
    if environment_value:
        return environment_value
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'") or None
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(payload)
    return rows


def _write_csv_atomic(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INTEGRATED_EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _safe_fetch_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key not in {"source_id", "endpoint_url"}
    }


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _load_or_fetch_traffic(
    *,
    cache_path: Path,
    spec,
    api_key: str | None,
    refresh: bool,
    allow_insecure_http: bool,
    timeout: float,
    now: datetime,
) -> dict[str, Any]:
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    if not allow_insecure_http:
        raise SystemExit("--allow-insecure-http is required to refresh ITS traffic")
    if not api_key:
        raise SystemExit("JEJU_ITS_API_KEY is required to refresh ITS traffic")
    payload, metadata = fetch_json_payload(
        spec,
        api_key=api_key,
        allow_insecure_http=True,
        timeout_seconds=timeout,
        now=now,
    )
    result = {
        "schema_version": 1,
        "source_id": spec.source_id,
        "fetch": _safe_fetch_metadata(metadata),
        "records": [dict(record) for record in extract_records(payload)],
    }
    write_json_atomic(cache_path, result)
    return result


def _load_or_fetch_weather(
    *,
    cache_path: Path,
    spec,
    api_key: str | None,
    grids: set[tuple[int, int]],
    refresh: bool,
    timeout: float,
    now: datetime,
) -> dict[str, Any]:
    if cache_path.exists() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_grids = {
            (int(row["grid_x"]), int(row["grid_y"]))
            for row in cached.get("grids", [])
        }
        if grids.issubset(cached_grids):
            return cached
    if not api_key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required to refresh weather")

    grid_results: list[dict[str, Any]] = []
    for grid_x, grid_y in sorted(grids):
        grid_spec = replace(
            spec,
            default_params={
                **spec.default_params,
                "nx": grid_x,
                "ny": grid_y,
            },
        )
        try:
            payload, metadata = fetch_json_payload(
                grid_spec,
                api_key=api_key,
                timeout_seconds=timeout,
                now=now,
            )
        except LiveFetchError as exc:
            grid_results.append(
                {
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "status": "fetch_failed",
                    "error": exc.to_dict(),
                    "records": [],
                }
            )
            continue
        grid_results.append(
            {
                "grid_x": grid_x,
                "grid_y": grid_y,
                "status": "success",
                "fetch": _safe_fetch_metadata(metadata),
                "records": [dict(record) for record in extract_records(payload)],
            }
        )
    result = {
        "schema_version": 1,
        "source_id": spec.source_id,
        "generated_at": now.isoformat(),
        "grids": grid_results,
    }
    write_json_atomic(cache_path, result)
    return result


def _load_or_fetch_taas(
    *,
    cache_path: Path,
    cache_dir: Path,
    spec,
    api_key: str | None,
    link_ids: set[str],
    reference_index: Mapping[str, Mapping[str, Any]],
    refresh: bool,
    timeout: float,
    request_delay: float,
) -> dict[str, Any]:
    if cache_path.exists() and not refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_links = {
            str(row.get("link_id")) for row in cached.get("results", [])
        }
        if link_ids.issubset(cached_links):
            return cached
    if not api_key:
        raise SystemExit("TAAS_API_KEY is required to refresh TAAS")

    results: list[dict[str, Any]] = []
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout),
        headers={"User-Agent": "Jeju-RoadOps-Integrated-Events/0.1"},
    ) as client:
        ordered_links = sorted(link_ids)
        for index, link_id in enumerate(ordered_links):
            reference = reference_index.get(link_id)
            search_line_string = taas_linestring_from_wkt(
                reference.get("geometry_wkt") if reference else None
            )
            if search_line_string is None:
                results.append(
                    {
                        "link_id": link_id,
                        "status": "invalid_reference_geometry",
                        "record_count": 0,
                        "complete_record_count": 0,
                    }
                )
                continue
            result = fetch_taas_link_risk(
                spec,
                api_key=api_key,
                link_id=link_id,
                search_line_string=search_line_string,
                cache_dir=cache_dir,
                refresh_cache=refresh,
                timeout_seconds=timeout,
                client=client,
            )
            result.pop("records", None)
            results.append(result)
            if (
                request_delay
                and result.get("fetch_source") == "live"
                and index < len(ordered_links) - 1
            ):
                time.sleep(request_delay)
    payload = {
        "schema_version": 1,
        "source_id": spec.source_id,
        "results": results,
    }
    write_json_atomic(cache_path, payload)
    return payload


def main() -> int:
    args = parse_args()
    if args.taas_request_delay < 0:
        raise SystemExit("--taas-request-delay must be non-negative")

    generated_at = datetime.now(ZoneInfo("Asia/Seoul"))
    joined_records = _read_jsonl(args.joined_records)
    reference_links = load_records(args.reference_links)
    if not args.geometry_priors.exists():
        raise SystemExit(
            "Jeju Data Hub geometry priors are missing. Run "
            "07_scripts/20261112_roadops_build_jeju_datahub_geometry_prior_v0_1.py "
            "first."
        )
    geometry_prior_rows = load_records(args.geometry_priors)
    geometry_prior_index, geometry_prior_profile = index_link_geometry_priors(
        geometry_prior_rows
    )
    reference_index = {
        link_id: {str(key).strip().lower(): value for key, value in row.items()}
        for row in reference_links
        if (link_id := normalize_link_id(row.get("link_id"))) is not None
    }
    specs = {spec.source_id: spec for spec in load_source_specs(args.config)}
    enrichment_dir = args.output_dir / "enrichments"
    traffic_path = enrichment_dir / "jeju_its_realtime_traffic.json"
    weather_path = enrichment_dir / "kma_ultra_short_forecast.json"
    taas_path = enrichment_dir / "taas_event_links.json"

    traffic_payload = _load_or_fetch_traffic(
        cache_path=traffic_path,
        spec=specs["jeju_its_realtime_traffic"],
        api_key=_read_env_value(args.env_file, "JEJU_ITS_API_KEY"),
        refresh=args.refresh_enrichments,
        allow_insecure_http=args.allow_insecure_http,
        timeout=args.timeout,
        now=generated_at,
    )
    traffic_index, traffic_profile = latest_traffic_by_link(
        traffic_payload.get("records", [])
    )

    grids = required_weather_grids(joined_records)
    weather_payload = _load_or_fetch_weather(
        cache_path=weather_path,
        spec=specs["kma_ultra_short_forecast"],
        api_key=_read_env_value(args.env_file, "DATA_GO_KR_SERVICE_KEY"),
        grids=grids,
        refresh=args.refresh_enrichments,
        timeout=args.timeout,
        now=generated_at,
    )
    weather_features: dict[tuple[int, int], dict[str, Any]] = {}
    for grid_result in weather_payload.get("grids", []):
        grid_x = int(grid_result["grid_x"])
        grid_y = int(grid_result["grid_y"])
        fetched_at = (
            grid_result.get("fetch", {}).get("fetched_at")
            if isinstance(grid_result.get("fetch"), Mapping)
            else None
        )
        weather_features[(grid_x, grid_y)] = weather_feature_for_grid(
            grid_result.get("records", []),
            target_at=generated_at,
            fetched_at=fetched_at,
            grid_x=grid_x,
            grid_y=grid_y,
        )

    event_link_ids = {
        link_id
        for row in joined_records
        if row.get("scoring_eligible")
        and (
            link_id := normalize_link_id(
                row.get("match", {}).get("matched_link_id")
            )
        )
        is not None
    }
    taas_payload = _load_or_fetch_taas(
        cache_path=taas_path,
        cache_dir=args.taas_cache_dir,
        spec=specs["taas_link_risk"],
        api_key=_read_env_value(args.env_file, "TAAS_API_KEY"),
        link_ids=event_link_ids,
        reference_index=reference_index,
        refresh=args.refresh_enrichments,
        timeout=args.timeout,
        request_delay=args.taas_request_delay,
    )
    taas_index, taas_profile = taas_by_link(taas_payload.get("results", []))

    table_rows, report = build_integrated_event_table(
        joined_records,
        reference_links,
        traffic_index=traffic_index,
        traffic_profile=traffic_profile,
        weather_features=weather_features,
        taas_index=taas_index,
        taas_profile=taas_profile,
        geometry_prior_index=geometry_prior_index,
        geometry_prior_profile=geometry_prior_profile,
        generated_at=generated_at,
    )
    table_path = args.output_dir / "integrated_field_events.csv"
    report_path = args.output_dir / "quality_report.json"
    report["inputs"] = {
        "joined_records": _relative(args.joined_records),
        "reference_links": _relative(args.reference_links),
        "jeju_datahub_geometry_priors": _relative(args.geometry_priors),
        "traffic_enrichment": _relative(traffic_path),
        "weather_enrichment": _relative(weather_path),
        "taas_enrichment": _relative(taas_path),
    }
    report["outputs"] = {
        "integrated_table": _relative(table_path),
        "quality_report": _relative(report_path),
    }
    _write_csv_atomic(table_path, table_rows)
    write_json_atomic(report_path, report)

    receipt = {
        "status": report["status"],
        "generated_at": report["generated_at"],
        "input_event_rows": report["input_event_rows"],
        "output_event_rows": report["output_event_rows"],
        "integration_class_counts": report["integration_class_counts"],
        "enrichment_coverage": report["enrichment_coverage"],
        "failed_checks": report["failed_checks"],
        "output": _relative(table_path),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
