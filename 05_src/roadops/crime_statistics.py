"""Collect and normalize privacy-preserving Jeju crime statistics."""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Iterable, Mapping


DETAIL_PAGE = "https://www.data.go.kr/data/3074462/fileData.do"
DOWNLOAD_METADATA_URL = "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"
DOWNLOAD_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do"
PUBLIC_DATA_PK = "3074462"
PUBLIC_DATA_DETAIL_PK = "uddi:c8238237-68dd-485b-a6ac-9d6981b48871"
ANALYSIS_YEAR = 2025
CITY_COLUMNS = {"제주 제주시": "제주시", "제주 서귀포시": "서귀포시"}


def _count(value: Any) -> int:
    text = str(value or "0").strip().replace(",", "")
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def parse_crime_csv(content: bytes) -> list[dict[str, str]]:
    """Decode the official CP949 CSV and return source rows."""

    text = content.decode("cp949").lstrip("\ufeff")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def normalize_jeju_crime_statistics(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate non-identifying city-level totals and top detailed categories."""

    materialized = list(rows)
    result: list[dict[str, Any]] = []
    for column, city in CITY_COLUMNS.items():
        category_counts: defaultdict[str, int] = defaultdict(int)
        major_counts: defaultdict[str, int] = defaultdict(int)
        for row in materialized:
            count = _count(row.get(column))
            major = str(row.get("범죄대분류") or "기타").strip()
            detail = str(row.get("범죄중분류") or "기타").strip()
            category_counts[detail] += count
            major_counts[major] += count
        top_categories = sorted(
            (
                {"crime_category": category, "occurrence_count": count}
                for category, count in category_counts.items()
            ),
            key=lambda row: (row["occurrence_count"], row["crime_category"]),
            reverse=True,
        )[:5]
        result.append(
            {
                "administrative_city": city,
                "analysis_year": ANALYSIS_YEAR,
                "occurrence_count": sum(category_counts.values()),
                "crime_category_count": len(category_counts),
                "top_categories": top_categories,
                "major_categories": [
                    {"crime_group": category, "occurrence_count": count}
                    for category, count in sorted(
                        major_counts.items(), key=lambda item: (item[1], item[0]), reverse=True
                    )
                ],
                "spatial_grain": "administrative_city",
                "privacy_semantics": "aggregated_non_identifying_statistics",
                "map_hotspot_eligible": False,
            }
        )
    return result


def download_official_crime_csv(timeout_seconds: float = 30.0) -> tuple[bytes, dict[str, Any]]:
    """Resolve the current official attachment ID and download the source CSV."""

    form = urllib.parse.urlencode(
        {
            "publicDataDetailPk": PUBLIC_DATA_DETAIL_PK,
            "publicDataPk": PUBLIC_DATA_PK,
            "atchFileId": "",
            "fileDetailSn": "1",
            "publicDataTyCode": "PR0051",
        }
    ).encode("utf-8")
    request = urllib.request.Request(DOWNLOAD_METADATA_URL, data=form, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        metadata = json.load(response)
    if metadata.get("status") is not True or not metadata.get("atchFileId"):
        raise RuntimeError("official_crime_file_metadata_unavailable")
    data_name = str(metadata.get("dataSetFileDetailInfo", {}).get("dataNm") or "crime_statistics")
    query = urllib.parse.urlencode(
        {
            "atchFileId": metadata["atchFileId"],
            "fileDetailSn": metadata.get("fileDetailSn") or "1",
            "dataNm": data_name,
        }
    )
    with urllib.request.urlopen(f"{DOWNLOAD_URL}?{query}", timeout=timeout_seconds) as response:
        content = response.read()
    return content, {
        "status": "available",
        "official_page": DETAIL_PAGE,
        "public_data_pk": PUBLIC_DATA_PK,
        "public_data_detail_pk": PUBLIC_DATA_DETAIL_PK,
        "source_file_name": data_name,
        "source_bytes": len(content),
    }
