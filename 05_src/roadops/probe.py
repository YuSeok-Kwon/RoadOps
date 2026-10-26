"""Read-only feasibility probes for RoadOps data sources.

RoadOps 데이터 소스의 접근성과 응답 스키마를 읽기 전용으로 점검합니다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import httpx


@dataclass(frozen=True)
class SourceSpec:
    """Configuration for one documented data source."""

    source_id: str
    name: str
    name_ko: str
    documentation_url: str
    kind: str
    endpoint_url: str | None
    download_url: str | None
    authentication: Mapping[str, str] | None
    default_params: Mapping[str, Any]
    runtime_params: str | None
    join_key: str | None
    coordinate_system: str | None
    expected_fields: tuple[str, ...]


def load_source_specs(path: str | Path) -> list[SourceSpec]:
    """Load and minimally validate the source registry."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported data source schema version")

    specs: list[SourceSpec] = []
    for source in payload.get("sources", []):
        specs.append(
            SourceSpec(
                source_id=source["id"],
                name=source["name"],
                name_ko=source["name_ko"],
                documentation_url=source["documentation_url"],
                kind=source["kind"],
                endpoint_url=source.get("endpoint_url"),
                download_url=source.get("download_url"),
                authentication=source.get("authentication"),
                default_params=source.get("default_params", {}),
                runtime_params=source.get("runtime_params"),
                join_key=source.get("join_key"),
                coordinate_system=source.get("coordinate_system"),
                expected_fields=tuple(source.get("expected_fields", [])),
            )
        )
    return specs


def extract_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Extract records from the C-ITS, KMA, or TAAS response envelope."""

    cits_records = payload.get("Info")
    if isinstance(cits_records, list):
        return [record for record in cits_records if isinstance(record, Mapping)]

    response = payload.get("response")
    if isinstance(response, Mapping):
        body = response.get("body")
        if isinstance(body, Mapping):
            items = body.get("items")
            if isinstance(items, Mapping):
                item = items.get("item")
                if isinstance(item, list):
                    return [record for record in item if isinstance(record, Mapping)]
                if isinstance(item, Mapping):
                    return [item]

    items = payload.get("items")
    if isinstance(items, Mapping):
        item = items.get("item")
        if isinstance(item, list):
            return [record for record in item if isinstance(record, Mapping)]
        if isinstance(item, Mapping):
            return [item]
    return []


def missing_expected_fields(
    records: Iterable[Mapping[str, Any]], expected_fields: Iterable[str]
) -> list[str]:
    """Return expected fields not observed in any sampled record."""

    observed: set[str] = set()
    for index, record in enumerate(records):
        observed.update(record.keys())
        if index >= 19:
            break
    return sorted(set(expected_fields) - observed)


def _kma_runtime_params(now: datetime | None = None) -> dict[str, str]:
    """Choose the latest safely available hourly base time in Korea."""

    current = now or datetime.now(tz=ZoneInfo("Asia/Seoul"))
    base = current - timedelta(minutes=45)
    return {"base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H00")}


def _documentation_probe(client: httpx.Client, url: str) -> dict[str, Any]:
    """Probe public documentation without downloading large response bodies."""

    try:
        response = client.head(url)
        if response.status_code in {400, 403, 405}:
            response = client.get(url, headers={"Range": "bytes=0-1023"})
        return {
            "status": "available" if response.is_success else "http_error",
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "content_length": response.headers.get("content-length"),
            "last_modified": response.headers.get("last-modified"),
        }
    except httpx.HTTPError as exc:
        return {"status": "network_error", "error_type": type(exc).__name__}


def _live_probe(client: httpx.Client, spec: SourceSpec) -> dict[str, Any]:
    """Call one operational endpoint only when its key is available."""

    if spec.endpoint_url is None:
        return {"status": "not_applicable"}
    if spec.authentication is None:
        return {"status": "authentication_not_configured"}

    env_name = spec.authentication["environment_variable"]
    api_key = os.environ.get(env_name)
    if not api_key:
        return {"status": "credential_missing", "required_environment_variable": env_name}

    params = dict(spec.default_params)
    params[spec.authentication["query_parameter"]] = api_key
    if spec.runtime_params == "kma_ultra_short_now":
        params.update(_kma_runtime_params())

    try:
        response = client.get(spec.endpoint_url, params=params)
        content_type = response.headers.get("content-type", "")
        result: dict[str, Any] = {
            "status": "http_error" if not response.is_success else "response_received",
            "http_status": response.status_code,
            "content_type": content_type,
        }
        if "json" not in content_type.lower():
            result["status"] = "non_json_response"
            return result
        payload = response.json()
        records = extract_records(payload)
        missing = missing_expected_fields(records, spec.expected_fields)
        result.update(
            {
                "record_count": len(records),
                "missing_expected_fields": missing,
                "status": (
                    "schema_valid"
                    if response.is_success and records and not missing
                    else "schema_not_verified"
                ),
            }
        )
        return result
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"status": "network_or_parse_error", "error_type": type(exc).__name__}


def probe_sources(
    specs: Iterable[SourceSpec],
    *,
    live: bool = False,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Probe documentation and optionally authenticated operational endpoints."""

    rows: list[dict[str, Any]] = []
    documentation_cache: dict[str, dict[str, Any]] = {}
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": "Jeju-RoadOps-Data-Feasibility/0.1"},
    ) as client:
        for spec in specs:
            documentation = documentation_cache.get(spec.documentation_url)
            if documentation is None:
                documentation = _documentation_probe(client, spec.documentation_url)
                documentation_cache[spec.documentation_url] = documentation

            download = None
            if spec.download_url:
                download = _documentation_probe(client, spec.download_url)

            row = {
                "source_id": spec.source_id,
                "name": spec.name,
                "name_ko": spec.name_ko,
                "kind": spec.kind,
                "join_key": spec.join_key,
                "coordinate_system": spec.coordinate_system,
                "documentation": documentation,
                "download": download,
                "transport_security": (
                    "plaintext_http"
                    if spec.endpoint_url and spec.endpoint_url.startswith("http://")
                    else "https"
                    if spec.endpoint_url
                    else None
                ),
                "live": _live_probe(client, spec) if live else {"status": "not_requested"},
            }
            rows.append(row)

    return {
        "generated_at": datetime.now(tz=ZoneInfo("Asia/Seoul")).isoformat(),
        "live_probe_requested": live,
        "source_count": len(rows),
        "sources": rows,
    }
