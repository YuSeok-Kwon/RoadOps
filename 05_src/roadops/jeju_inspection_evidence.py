"""Normalize Jeju Hub evidence without converting aggregates into road probabilities.

노면 집계와 행정지역 재해 자료를 현장 점검 근거로 정규화합니다.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter
from pathlib import Path
from typing import Any

HUB = "https://jejudatahub.net/data/view/data/"
SURFACES = ("건조", "젖음/습기", "서리/결빙", "적설", "해빙", "기타")


def read_public_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV encoding is neither UTF-8 nor CP949")
    return [{str(k).strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(io.StringIO(text))]


def count(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = int(str(value).replace(",", ""))
    if parsed < 0:
        raise ValueError("Negative count")
    return parsed


def normalize_surface(rows: list[dict]) -> tuple[list[dict], dict]:
    normalized, keys = [], set()
    for row in rows:
        year, state = int(row["기준 연도"]), row["노면 상태"]
        if not 1900 <= year <= 2100 or state not in SURFACES or (year, state) in keys:
            raise ValueError("Invalid or duplicate year/surface")
        keys.add((year, state))
        values = {key: count(row[column]) for key, column in (
            ("accident_count", "사고 건수"), ("injury_count", "부상자 수"), ("fatality_count", "사망자 수"))}
        normalized.append({"year": year, "surface": state, **values,
                           "complete": all(value is not None for value in values.values()),
                           "source_dataset_id": "891", "source_url": HUB + "891"})
    years = sorted({row["year"] for row in normalized})
    return normalized, {"rows": len(normalized), "years": years,
                        "incomplete_rows": sum(not r["complete"] for r in normalized),
                        "grain": "year × surface", "exposure_denominator": "unavailable"}


def normalize_hub_hotspots(rows: list[dict]) -> list[dict]:
    result, keys = [], set()
    for row in rows:
        year = int(row["연도"])
        lat, lon = float(row["위도"]), float(row["경도"])
        if not 33 <= lat <= 34.1 or not 126 <= lon <= 127.1:
            raise ValueError("Hotspot outside Jeju coordinate bounds")
        name = row["발생 지점"]
        key = (year, name, lat, lon)
        if key in keys:
            continue
        keys.add(key)
        identity = hashlib.sha256(repr(key).encode()).hexdigest()[:12]
        values = {field: count(row[col]) for field, col in (
            ("accident_count", "발생 건수"), ("casualty_count", "사상자 수"),
            ("fatality_count", "사망자 수"), ("serious_injury_count", "중상자 수"))}
        if any(value is None for value in values.values()):
            raise ValueError("Incomplete hotspot counts")
        result.append({"hotspot_id": "hub863-" + identity, "analysis_year": year,
                       "jurisdiction": row["시도 시군구"], "location_name": name,
                       "latitude": lat, "longitude": lon, **values,
                       "geometry_json": "[]", "source_mode": "hub_public_preview_csv",
                       "source_label": "제주데이터허브 · TAAS 원천", "source_dataset_id": "863",
                       "source_url": HUB + "863", "collected_at": row.get("데이터 수집 일시"),
                       "coverage_note": "공개 CSV에 포함된 2017–2022년 36개 연도별 선정지점; 전체 사고가 아님"})
    return result


def merge_hotspots(taas: list[dict], hub: list[dict]) -> list[dict]:
    """Keep year-specific evidence; never sum two copies of the same source event."""
    result = []
    for row in taas + hub:
        row = dict(row)
        row.setdefault("source_label", "TAAS 한국도로교통공단")
        duplicate = next((other for other in result
            if other.get("analysis_year") == row.get("analysis_year")
            and abs(float(other["latitude"]) - float(row["latitude"])) < .00001
            and abs(float(other["longitude"]) - float(row["longitude"])) < .00001
            and other.get("accident_count") == row.get("accident_count")), None)
        if duplicate:
            duplicate.setdefault("corroborating_sources", []).append(row.get("source_url"))
        else:
            result.append(row)
    return sorted(result, key=lambda r: (-int(r["analysis_year"]), r["hotspot_id"]))


def normalize_hazards(rows: list[dict], *, kind: str) -> list[dict]:
    result = []
    for index, row in enumerate(rows):
        slope = kind == "steep_slope"
        name = row["지역명" if slope else "지구명"]
        work = row["추진상황" if slope else "완료여부"]
        remarks = row.get("비고", "")
        # Completion of works is not equivalent to cancellation of designation.
        status = "released" if "해제" in remarks else "works_completed" if "완료" in work else "review_required"
        dataset = "436" if slope else "435"
        result.append({"hazard_id": f"hub{dataset}-{index + 1}", "kind": kind,
            "name": name, "location": row["위치"], "hazard_type": "붕괴위험" if slope else row["유형"],
            "grade": row["등급" if slope else "위험등급"], "works_status": work,
            "designation_status": status, "remarks": remarks,
            "as_of": row["데이터기준일자"], "location_precision": "administrative_area_only",
            "latitude": None, "longitude": None, "automatic_road_closure": False,
            "source_dataset_id": dataset, "source_url": HUB + dataset,
            "download_source_url": "https://www.data.go.kr/data/" + ("15056033" if slope else "15056032") + "/fileData.do"})
    return result


def build_evidence(surface: Path, hotspots: Path, slopes: Path, hazards: Path) -> dict:
    surface_rows, surface_quality = normalize_surface(read_public_csv(surface))
    hub_rows = normalize_hub_hotspots(read_public_csv(hotspots))
    hazard_rows = normalize_hazards(read_public_csv(slopes), kind="steep_slope") + normalize_hazards(read_public_csv(hazards), kind="natural_hazard")
    return {"schema_version": 1, "surface_accidents": surface_rows,
            "hub_accident_hotspots": hub_rows, "designated_hazards": hazard_rows,
            "quality": {"surface": surface_quality, "hub_hotspots": {"rows": len(hub_rows), "years": sorted({r['analysis_year'] for r in hub_rows}), "scope": "public_preview_csv"},
                        "hazards": dict(Counter(r['designation_status'] for r in hazard_rows)),
                        "hazard_location_precision": "administrative_area_only"},
            "files": {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in (surface, hotspots, slopes, hazards)}}
