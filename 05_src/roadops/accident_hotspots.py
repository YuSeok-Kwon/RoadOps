"""Collect official KoROAD frequent-accident areas for Jeju.

한국도로교통공단 지자체별 교통사고 다발지역을 제주 범위로 정규화합니다.
"""

from __future__ import annotations

import csv
from http.cookiejar import CookieJar
import io
import json
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


REST_ENDPOINT = "https://opendata.koroad.or.kr/data/rest/frequentzone/lg"
DATASET_PAGE = "https://opendata.koroad.or.kr/api/selectLgDataSet.do"
CSV_ENDPOINT = "https://opendata.koroad.or.kr/api/down/lgdown.jsp"
JEJU_JURISDICTIONS = (("110", "제주시"), ("130", "서귀포시"))


def _integer(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _polygon_coordinates(value: Any) -> list[list[list[float]]]:
    try:
        payload = json.loads(str(value or "").strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    coordinates = payload.get("coordinates", []) if isinstance(payload, Mapping) else []
    if str(payload.get("type", "")).lower() == "multipolygon":
        return [part for polygon in coordinates for part in polygon]
    return coordinates if isinstance(coordinates, list) else []


def _normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_mode: str,
    analysis_year: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        longitude = _number(row.get("lo_crd") or row.get("경도"))
        latitude = _number(row.get("la_crd") or row.get("위도"))
        if longitude is None or latitude is None:
            continue
        polygon = _polygon_coordinates(
            row.get("geom_json") or row.get("다발지역폴리곤")
        )
        normalized.append(
            {
                "hotspot_id": str(
                    row.get("afos_fid") or row.get("사고다발지fid") or ""
                ).strip(),
                "analysis_year": analysis_year,
                "jurisdiction": str(
                    row.get("sido_sgg_nm") or row.get("시도시군구명") or ""
                ).strip(),
                "location_name": str(
                    row.get("spot_nm") or row.get("지점명") or ""
                ).strip(),
                "accident_count": _integer(
                    row.get("occrrnc_cnt") or row.get("사고건수")
                ),
                "casualty_count": _integer(
                    row.get("caslt_cnt") or row.get("사상자수")
                ),
                "fatality_count": _integer(
                    row.get("dth_dnv_cnt") or row.get("사망자수")
                ),
                "serious_injury_count": _integer(
                    row.get("se_dnv_cnt") or row.get("중상자수")
                ),
                "longitude": longitude,
                "latitude": latitude,
                "geometry_json": json.dumps(
                    polygon, ensure_ascii=False, separators=(",", ":")
                ),
                "source_mode": source_mode,
                "source_url": DATASET_PAGE,
            }
        )
    return sorted(
        normalized,
        key=lambda row: (-row["accident_count"], row["location_name"]),
    )


def normalize_official_csv(payload: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Decode the official CP949 CSV and retain the latest Jeju publication."""

    text = payload.decode("cp949")
    rows = list(csv.DictReader(io.StringIO(text)))
    jeju_rows = [
        row
        for row in rows
        if str(row.get("시도시군구명") or "").strip().startswith("제주")
    ]
    publication_years = [
        _integer(str(row.get("사고다발지id") or "")[:4])
        for row in jeju_rows
    ]
    latest_publication_year = max(publication_years, default=0)
    latest_rows = [
        row
        for row in jeju_rows
        if _integer(str(row.get("사고다발지id") or "")[:4])
        == latest_publication_year
    ]
    analysis_year = max(0, latest_publication_year - 1)
    normalized = _normalize_rows(
        latest_rows,
        source_mode="official_csv",
        analysis_year=analysis_year,
    )
    return normalized, {
        "source_row_count": len(rows),
        "jeju_row_count": len(jeju_rows),
        "latest_publication_year": latest_publication_year,
        "analysis_year": analysis_year,
        "output_row_count": len(normalized),
    }


def download_official_csv(*, timeout: float = 30.0) -> bytes:
    """Open the dataset page first because the provider download needs a session."""

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    headers = {"User-Agent": "Jeju-RoadOps-Accident-Hotspots/0.1"}
    opener.open(Request(DATASET_PAGE, headers=headers), timeout=timeout).read()
    response = opener.open(
        Request(CSV_ENDPOINT, headers={**headers, "Referer": DATASET_PAGE}),
        timeout=timeout,
    )
    return response.read()


def fetch_rest_rows(
    api_key: str,
    *,
    search_year: int,
    timeout: float = 20.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch both Jeju administrative cities without exposing the API key."""

    records: list[Mapping[str, Any]] = []
    result_codes: dict[str, str] = {}
    for gugun, name in JEJU_JURISDICTIONS:
        query = urlencode(
            {
                "authKey": api_key,
                "searchYearCd": search_year,
                "siDo": "50",
                "guGun": gugun,
                "type": "json",
                "numOfRows": 100,
                "pageNo": 1,
            }
        )
        with urlopen(
            Request(
                f"{REST_ENDPOINT}?{query}",
                headers={"User-Agent": "Jeju-RoadOps-Accident-Hotspots/0.1"},
            ),
            timeout=timeout,
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        result_codes[name] = str(payload.get("resultCode") or "unknown")
        items = payload.get("items", {}).get("item", [])
        if isinstance(items, Mapping):
            items = [items]
        if result_codes[name] == "00":
            records.extend(items)
    return _normalize_rows(
        records,
        source_mode="rest_api",
        analysis_year=search_year,
    ), {"result_codes": result_codes, "output_row_count": len(records)}


def collect_accident_hotspots(
    *,
    api_key: str | None,
    search_year: int,
    timeout: float = 30.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prefer REST and fall back to the provider's official complete CSV."""

    rest_report: dict[str, Any] = {"status": "not_attempted_missing_key"}
    if api_key:
        try:
            rows, details = fetch_rest_rows(
                api_key, search_year=search_year, timeout=timeout
            )
            rest_report = {"status": "available" if rows else "provider_rejected", **details}
            if rows:
                return rows, {
                    "status": "pass",
                    "selected_mode": "rest_api",
                    "rest": rest_report,
                    "csv": {"status": "not_needed"},
                }
        except Exception as exc:  # provider errors are reported without URLs or keys
            rest_report = {
                "status": "fetch_failed",
                "error_type": type(exc).__name__,
            }

    payload = download_official_csv(timeout=timeout)
    rows, csv_report = normalize_official_csv(payload)
    return rows, {
        "status": "pass" if rows else "fail",
        "selected_mode": "official_csv_fallback",
        "rest": rest_report,
        "csv": {"status": "available" if rows else "empty", **csv_report},
    }
