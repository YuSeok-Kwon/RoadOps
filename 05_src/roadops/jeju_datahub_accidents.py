"""Profile Jeju Data Hub road-geometry accident aggregates safely.

제주 데이터허브 도로 선형별 사고 집계를 안전하게 프로파일링합니다.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from math import cos, hypot, radians
from pathlib import Path
from typing import Any, Iterable, Mapping

from roadops.spatial import GeoPoint, normalize_link_id, parse_link_geometry_wkt


DATASET_ID = "1027"
DATASET_NAME_KO = "제주 도로 선형별 교통사고 현황"
DATASET_URL = "https://www.jejudatahub.net/data/view/data/1027"
SOURCE_FILE_NAME = "제주도로선형별교통사고현황.csv"
SOURCE_SHA256 = "7446d49533628e030ad33a685672b4b76f5bfbb9eb26313c748bdadaac739dd2"
SOURCE_PERIOD = (2018, 2020)

REQUIRED_COLUMNS = (
    "기준 연도",
    "도로선형 대분류",
    "도로선형 중분류",
    "도로선형 소분류",
    "사고 건수",
    "사망자 수",
    "부상자 수",
)
GEOMETRY_CLASS_MAP = {"커브,곡각": "curve", "직선": "straight"}

NORMALIZED_ACCIDENT_FIELDS = (
    "year",
    "geometry_large",
    "geometry_middle",
    "geometry_small",
    "hierarchy_level",
    "accident_count",
    "fatality_count",
    "injury_count",
)

GEOMETRY_PRIOR_FIELDS = (
    "geometry_proxy_class",
    "source_geometry_label",
    "period_start_year",
    "period_end_year",
    "source_year_rows",
    "source_accident_count",
    "source_fatality_count",
    "source_injury_count",
    "fatalities_per_100_accidents",
    "injuries_per_accident",
    "fatality_index_vs_straight",
)

LINK_GEOMETRY_PRIOR_FIELDS = (
    "link_id",
    "mapping_status",
    "geometry_proxy_class",
    "link_length_meters",
    "link_chord_meters",
    "link_sinuosity",
    "curve_threshold_sinuosity",
    "source_dataset_id",
    "source_geometry_label",
    "source_period_start_year",
    "source_period_end_year",
    "source_accident_count",
    "source_fatality_count",
    "source_injury_count",
    "fatalities_per_100_accidents",
    "injuries_per_accident",
    "fatality_index_vs_straight",
)


class DataQualityError(ValueError):
    """Raised when the pinned public dataset cannot be parsed safely."""


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any, *, field: str, row_number: int) -> int:
    text = _clean_text(value).replace(",", "")
    try:
        number = int(text)
    except ValueError as exc:
        raise DataQualityError(
            f"Invalid integer in {field} at source row {row_number}: {value!r}"
        ) from exc
    return number


def _hierarchy_level(middle: str, small: str) -> str:
    if middle == "합계" and small == "합계":
        return "top_total"
    if small == "합계":
        return "subtotal"
    return "leaf"


def load_accident_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and normalize the pinned UTF-8 CSV without losing source identity."""

    raw_bytes = path.read_bytes()
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        observed_columns = tuple(_clean_text(column) for column in reader.fieldnames or ())
        if observed_columns != REQUIRED_COLUMNS:
            raise DataQualityError(
                f"Unexpected columns: {observed_columns!r}; expected {REQUIRED_COLUMNS!r}"
            )
        rows: list[dict[str, Any]] = []
        for row_number, raw in enumerate(reader, start=2):
            year = _integer(raw["기준 연도"], field="기준 연도", row_number=row_number)
            large = _clean_text(raw["도로선형 대분류"])
            middle = _clean_text(raw["도로선형 중분류"])
            small = _clean_text(raw["도로선형 소분류"])
            rows.append(
                {
                    "year": year,
                    "geometry_large": large,
                    "geometry_middle": middle,
                    "geometry_small": small,
                    "hierarchy_level": _hierarchy_level(middle, small),
                    "accident_count": _integer(
                        raw["사고 건수"], field="사고 건수", row_number=row_number
                    ),
                    "fatality_count": _integer(
                        raw["사망자 수"], field="사망자 수", row_number=row_number
                    ),
                    "injury_count": _integer(
                        raw["부상자 수"], field="부상자 수", row_number=row_number
                    ),
                }
            )
    return rows, {
        "path": str(path),
        "sha256": source_hash,
        "pinned_sha256": SOURCE_SHA256,
        "hash_matches_pinned_source": source_hash == SOURCE_SHA256,
        "bytes": len(raw_bytes),
    }


def profile_accident_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Check grain, hierarchy reconciliation, domains, and usable scope."""

    observed = [dict(row) for row in rows]
    keys = [
        (
            int(row["year"]),
            str(row["geometry_large"]),
            str(row["geometry_middle"]),
            str(row["geometry_small"]),
        )
        for row in observed
    ]
    duplicate_keys = len(keys) - len(set(keys))
    negative_measure_rows = sum(
        any(int(row[column]) < 0 for column in ("accident_count", "fatality_count", "injury_count"))
        for row in observed
    )
    missing_dimension_rows = sum(
        any(not _clean_text(row[column]) for column in ("geometry_large", "geometry_middle", "geometry_small"))
        for row in observed
    )
    years = sorted({int(row["year"]) for row in observed})
    categories = sorted({str(row["geometry_large"]) for row in observed})

    grouped: defaultdict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observed:
        grouped[(int(row["year"]), str(row["geometry_large"]))].append(row)

    reconciliations: list[dict[str, Any]] = []
    for (year, category), group in sorted(grouped.items()):
        top_rows = [row for row in group if row["hierarchy_level"] == "top_total"]
        leaf_rows = [row for row in group if row["hierarchy_level"] == "leaf"]
        top = top_rows[0] if len(top_rows) == 1 else None
        differences: dict[str, int | None] = {}
        for column in ("accident_count", "fatality_count", "injury_count"):
            differences[column] = (
                int(top[column]) - sum(int(row[column]) for row in leaf_rows)
                if top is not None and leaf_rows
                else None
            )
        passed = len(top_rows) == 1 and bool(leaf_rows) and all(
            difference == 0 for difference in differences.values()
        )
        reconciliations.append(
            {
                "year": year,
                "geometry_large": category,
                "top_total_rows": len(top_rows),
                "leaf_rows": len(leaf_rows),
                "differences": differences,
                "passed": passed,
            }
        )

    checks = [
        {
            "check_id": "pinned_source_hash",
            "passed": bool(source_metadata.get("hash_matches_pinned_source")),
            "observed": source_metadata.get("sha256"),
            "expected": SOURCE_SHA256,
        },
        {
            "check_id": "composite_key_uniqueness",
            "passed": duplicate_keys == 0,
            "duplicate_rows": duplicate_keys,
        },
        {
            "check_id": "required_dimensions_complete",
            "passed": missing_dimension_rows == 0,
            "affected_rows": missing_dimension_rows,
        },
        {
            "check_id": "non_negative_measures",
            "passed": negative_measure_rows == 0,
            "affected_rows": negative_measure_rows,
        },
        {
            "check_id": "hierarchy_totals_reconcile",
            "passed": all(item["passed"] for item in reconciliations),
            "passed_groups": sum(item["passed"] for item in reconciliations),
            "total_groups": len(reconciliations),
        },
        {
            "check_id": "documented_period_coverage",
            "passed": years == list(range(SOURCE_PERIOD[0], SOURCE_PERIOD[1] + 1)),
            "observed_years": years,
            "expected_years": list(range(SOURCE_PERIOD[0], SOURCE_PERIOD[1] + 1)),
        },
    ]
    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    return {
        "schema_version": 1,
        "dataset": {
            "id": DATASET_ID,
            "name_ko": DATASET_NAME_KO,
            "url": DATASET_URL,
            "file_name": SOURCE_FILE_NAME,
            "source_provider": "TAAS 교통사고분석시스템",
            "portal_owner": "제주특별자치도 미래성장과",
            "portal_certified": True,
            "registered_at": "2021-12-01",
            "modified_at": "2021-12-01",
            "documented_collection_period": "2018-01-01/2020-12-31",
            "license": "not_shown_on_dataset_detail_page",
        },
        "source_file": dict(source_metadata),
        "grain": "one row per year and road-geometry hierarchy member",
        "row_count": len(observed),
        "column_count": len(NORMALIZED_ACCIDENT_FIELDS),
        "year_counts": dict(sorted(Counter(int(row["year"]) for row in observed).items())),
        "hierarchy_counts": dict(
            sorted(Counter(str(row["hierarchy_level"]) for row in observed).items())
        ),
        "geometry_large_counts": dict(
            sorted(Counter(str(row["geometry_large"]) for row in observed).items())
        ),
        "observed_years": years,
        "observed_geometry_categories": categories,
        "reconciliations": reconciliations,
        "checks": checks,
        "failed_checks": failed_checks,
        "status": "fail" if failed_checks else "pass_with_limitations",
        "limitations": [
            "The dataset has no road-length, traffic-volume, or vehicle-kilometre exposure denominator, so accident counts cannot estimate per-link accident incidence risk.",
            "The source covers 2018-2020 and is a structural historical prior, not a current road condition signal.",
            "The portal dataset is sourced from TAAS; do not add it independently to a TAAS link-risk feature without a double-counting rule.",
            "Mapping national road-link geometry to the portal's broad straight/curve classes is a RoadOps heuristic, not a provider field.",
        ],
    }


def build_geometry_severity_priors(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build conditional severity priors from top totals without double counting."""

    top_rows = [
        dict(row)
        for row in rows
        if row.get("hierarchy_level") == "top_total"
        and str(row.get("geometry_large")) in GEOMETRY_CLASS_MAP
    ]
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in top_rows:
        grouped[GEOMETRY_CLASS_MAP[str(row["geometry_large"])]].append(row)

    totals: dict[str, dict[str, Any]] = {}
    for geometry_class, group in sorted(grouped.items()):
        accidents = sum(int(row["accident_count"]) for row in group)
        fatalities = sum(int(row["fatality_count"]) for row in group)
        injuries = sum(int(row["injury_count"]) for row in group)
        if accidents <= 0:
            raise DataQualityError(f"No accident denominator for {geometry_class}")
        totals[geometry_class] = {
            "geometry_proxy_class": geometry_class,
            "source_geometry_label": next(
                label for label, value in GEOMETRY_CLASS_MAP.items() if value == geometry_class
            ),
            "period_start_year": min(int(row["year"]) for row in group),
            "period_end_year": max(int(row["year"]) for row in group),
            "source_year_rows": len(group),
            "source_accident_count": accidents,
            "source_fatality_count": fatalities,
            "source_injury_count": injuries,
            "fatalities_per_100_accidents": round(fatalities / accidents * 100, 6),
            "injuries_per_accident": round(injuries / accidents, 6),
        }

    straight_rate = totals.get("straight", {}).get("fatalities_per_100_accidents")
    if not straight_rate:
        raise DataQualityError("Straight-road fatality rate is required as the index baseline")
    for prior in totals.values():
        prior["fatality_index_vs_straight"] = round(
            float(prior["fatalities_per_100_accidents"]) / float(straight_rate), 6
        )
    return totals


def _distance_meters(start: GeoPoint, end: GeoPoint) -> float:
    mean_latitude = radians((start.latitude + end.latitude) / 2)
    return hypot(
        (start.longitude - end.longitude) * 111_320 * cos(mean_latitude),
        (start.latitude - end.latitude) * 110_540,
    )


def geometry_metrics(value: Any) -> dict[str, Any] | None:
    """Measure path length and endpoint sinuosity for a WGS84 road WKT."""

    parts = parse_link_geometry_wkt(value)
    if not parts:
        return None
    path_length = sum(
        _distance_meters(start, end)
        for part in parts
        for start, end in zip(part, part[1:])
    )
    chord_length = sum(_distance_meters(part[0], part[-1]) for part in parts)
    if path_length <= 0 or chord_length <= 0:
        return None
    return {
        "link_length_meters": round(path_length, 3),
        "link_chord_meters": round(chord_length, 3),
        "link_sinuosity": round(max(1.0, path_length / chord_length), 6),
    }


def build_link_geometry_priors(
    link_rows: Iterable[Mapping[str, Any]],
    severity_priors: Mapping[str, Mapping[str, Any]],
    *,
    curve_threshold_sinuosity: float = 1.02,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Map each unique reference link to a transparent straight/curve proxy."""

    if curve_threshold_sinuosity <= 1:
        raise ValueError("curve_threshold_sinuosity must be greater than 1")
    output: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    duplicate_link_rows = 0
    invalid_link_rows = 0
    invalid_geometry_rows = 0
    for raw in link_rows:
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        link_id = normalize_link_id(row.get("link_id"))
        if link_id is None:
            invalid_link_rows += 1
            continue
        if link_id in seen_links:
            duplicate_link_rows += 1
            continue
        seen_links.add(link_id)
        metrics = geometry_metrics(row.get("geometry_wkt"))
        if metrics is None:
            invalid_geometry_rows += 1
            output.append(
                {
                    **{field: None for field in LINK_GEOMETRY_PRIOR_FIELDS},
                    "link_id": link_id,
                    "mapping_status": "invalid_geometry",
                    "curve_threshold_sinuosity": curve_threshold_sinuosity,
                    "source_dataset_id": DATASET_ID,
                }
            )
            continue
        geometry_class = (
            "curve"
            if float(metrics["link_sinuosity"]) >= curve_threshold_sinuosity
            else "straight"
        )
        prior = severity_priors.get(geometry_class)
        status = "matched" if prior else "missing_source_category"
        output.append(
            {
                "link_id": link_id,
                "mapping_status": status,
                "geometry_proxy_class": geometry_class,
                **metrics,
                "curve_threshold_sinuosity": curve_threshold_sinuosity,
                "source_dataset_id": DATASET_ID,
                "source_geometry_label": prior.get("source_geometry_label") if prior else None,
                "source_period_start_year": prior.get("period_start_year") if prior else None,
                "source_period_end_year": prior.get("period_end_year") if prior else None,
                "source_accident_count": prior.get("source_accident_count") if prior else None,
                "source_fatality_count": prior.get("source_fatality_count") if prior else None,
                "source_injury_count": prior.get("source_injury_count") if prior else None,
                "fatalities_per_100_accidents": (
                    prior.get("fatalities_per_100_accidents") if prior else None
                ),
                "injuries_per_accident": prior.get("injuries_per_accident") if prior else None,
                "fatality_index_vs_straight": (
                    prior.get("fatality_index_vs_straight") if prior else None
                ),
            }
        )

    status_counts = Counter(str(row["mapping_status"]) for row in output)
    class_counts = Counter(
        str(row["geometry_proxy_class"])
        for row in output
        if row.get("geometry_proxy_class")
    )
    matched_rows = status_counts["matched"]
    checks = [
        {
            "check_id": "link_id_uniqueness",
            "passed": duplicate_link_rows == 0,
            "duplicate_rows": duplicate_link_rows,
        },
        {
            "check_id": "valid_link_ids",
            "passed": invalid_link_rows == 0,
            "invalid_rows": invalid_link_rows,
        },
        {
            "check_id": "geometry_mapping_complete",
            "passed": matched_rows == len(output),
            "matched_rows": matched_rows,
            "output_rows": len(output),
        },
    ]
    failed_checks = [check["check_id"] for check in checks if not check["passed"]]
    return output, {
        "input_link_rows": len(output) + invalid_link_rows + duplicate_link_rows,
        "output_link_rows": len(output),
        "unique_link_ids": len(seen_links),
        "duplicate_link_rows": duplicate_link_rows,
        "invalid_link_rows": invalid_link_rows,
        "invalid_geometry_rows": invalid_geometry_rows,
        "curve_threshold_sinuosity": curve_threshold_sinuosity,
        "mapping_status_counts": dict(sorted(status_counts.items())),
        "geometry_proxy_class_counts": dict(sorted(class_counts.items())),
        "matched_rate": round(matched_rows / len(output), 6) if output else None,
        "checks": checks,
        "failed_checks": failed_checks,
        "status": "fail" if failed_checks else "pass_with_limitations",
    }


def index_link_geometry_priors(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Index one derived geometry prior per link and expose duplicates."""

    index: dict[str, dict[str, Any]] = {}
    duplicate_rows = 0
    invalid_link_rows = 0
    for raw in rows:
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        link_id = normalize_link_id(row.get("link_id"))
        if link_id is None:
            invalid_link_rows += 1
            continue
        if link_id in index:
            duplicate_rows += 1
            continue
        index[link_id] = row
    return index, {
        "source_rows": len(index) + duplicate_rows + invalid_link_rows,
        "unique_link_rows": len(index),
        "duplicate_link_rows": duplicate_rows,
        "invalid_link_rows": invalid_link_rows,
    }
