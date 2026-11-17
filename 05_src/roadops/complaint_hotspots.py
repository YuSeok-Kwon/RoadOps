"""Privacy-preserving ingestion for Jeju road-complaint hotspot exports."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
from typing import Any, Iterable, Mapping


FIELD_ALIASES = {
    "complaint_id": ("complaint_id", "민원번호", "접수번호"),
    "received_at": ("received_at", "접수일시", "접수일", "신고일시"),
    "category": ("category", "민원유형", "민원분류", "신고유형"),
    "latitude": ("latitude", "lat", "위도"),
    "longitude": ("longitude", "lon", "lng", "경도"),
    "status": ("status", "처리상태", "상태"),
    "responsible_agency": ("responsible_agency", "담당기관", "처리기관"),
}

PROHIBITED_TOKENS = (
    "name",
    "phone",
    "mobile",
    "email",
    "address_detail",
    "description",
    "content",
    "신고자",
    "성명",
    "연락처",
    "전화",
    "이메일",
    "민원내용",
    "상세내용",
)

JEJU_BOUNDS = {
    "latitude_min": 33.0,
    "latitude_max": 34.0,
    "longitude_min": 126.0,
    "longitude_max": 127.2,
}


def _pick(row: Mapping[str, Any], field: str) -> Any:
    for alias in FIELD_ALIASES[field]:
        value = row.get(alias)
        if value not in (None, ""):
            return value
    return None


def validate_export_fields(fieldnames: Iterable[str]) -> list[str]:
    """Reject raw exports that include personal or free-text complaint fields."""

    unsafe = []
    for field in fieldnames:
        lowered = str(field).strip().lower()
        if any(token in lowered for token in PROHIBITED_TOKENS):
            unsafe.append(str(field))
    return sorted(set(unsafe))


def _parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _month(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(".", "-").replace("/", "-")
    try:
        return datetime.fromisoformat(normalized).strftime("%Y-%m")
    except ValueError:
        return normalized[:7] if len(normalized) >= 7 else None


def aggregate_complaint_hotspots(
    rows: Iterable[Mapping[str, Any]],
    *,
    grid_degrees: float = 0.005,
    minimum_count: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate complaint points into coarse, k-anonymous map cells.

    Exact complaint coordinates and complaint IDs are deliberately discarded.
    A 0.005-degree cell is roughly 500 m north-south in Jeju.
    """

    materialized = [dict(row) for row in rows]
    unsafe_fields = validate_export_fields(
        {field for row in materialized for field in row.keys()}
    )
    if unsafe_fields:
        raise ValueError(f"unsafe_personal_or_free_text_fields:{','.join(unsafe_fields)}")

    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    rejected = Counter()
    for row in materialized:
        latitude = _parse_float(_pick(row, "latitude"))
        longitude = _parse_float(_pick(row, "longitude"))
        if latitude is None or longitude is None:
            rejected["missing_or_invalid_coordinate"] += 1
            continue
        if not (
            JEJU_BOUNDS["latitude_min"] <= latitude <= JEJU_BOUNDS["latitude_max"]
            and JEJU_BOUNDS["longitude_min"] <= longitude <= JEJU_BOUNDS["longitude_max"]
        ):
            rejected["outside_jeju_bounds"] += 1
            continue
        grid_key = (int(latitude / grid_degrees), int(longitude / grid_degrees))
        grouped[grid_key].append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "category": str(_pick(row, "category") or "분류 미지정").strip(),
                "received_month": _month(_pick(row, "received_at")),
                "status": str(_pick(row, "status") or "").strip() or None,
                "responsible_agency": str(_pick(row, "responsible_agency") or "").strip() or None,
            }
        )

    records = []
    suppressed_count = 0
    for grid_key, items in sorted(grouped.items()):
        if len(items) < minimum_count:
            suppressed_count += len(items)
            continue
        categories = Counter(item["category"] for item in items)
        agencies = Counter(item["responsible_agency"] for item in items if item["responsible_agency"])
        months = sorted({item["received_month"] for item in items if item["received_month"]})
        center_latitude = (grid_key[0] + 0.5) * grid_degrees
        center_longitude = (grid_key[1] + 0.5) * grid_degrees
        anonymous_id = hashlib.sha256(
            f"{grid_key[0]}:{grid_key[1]}:{grid_degrees}".encode("utf-8")
        ).hexdigest()[:12]
        records.append(
            {
                "hotspot_id": f"complaint-grid-{anonymous_id}",
                "latitude": round(center_latitude, 6),
                "longitude": round(center_longitude, 6),
                "complaint_count": len(items),
                "top_categories": [
                    {"category": category, "count": count}
                    for category, count in categories.most_common(3)
                ],
                "top_responsible_agency": agencies.most_common(1)[0][0] if agencies else None,
                "period_start_month": months[0] if months else None,
                "period_end_month": months[-1] if months else None,
                "spatial_precision": "approximately_500m_grid",
                "privacy_rule": f"minimum_{minimum_count}_complaints_per_cell",
            }
        )

    records.sort(key=lambda row: (-row["complaint_count"], row["hotspot_id"]))
    return records, {
        "status": "ready" if records else "no_publishable_hotspots",
        "source_row_count": len(materialized),
        "usable_row_count": sum(len(items) for items in grouped.values()),
        "published_hotspot_count": len(records),
        "published_complaint_count": sum(row["complaint_count"] for row in records),
        "suppressed_complaint_count": suppressed_count,
        "rejected_counts": dict(sorted(rejected.items())),
        "grid_degrees": grid_degrees,
        "minimum_count": minimum_count,
        "exact_coordinates_retained": False,
        "complaint_ids_retained": False,
    }
