from __future__ import annotations

from roadops.jeju_datahub_accidents import (
    SOURCE_SHA256,
    build_geometry_severity_priors,
    build_link_geometry_priors,
    geometry_metrics,
    index_link_geometry_priors,
    load_accident_rows,
    profile_accident_rows,
)


def _row(
    *,
    year: int,
    large: str,
    level: str,
    accidents: int,
    fatalities: int,
    injuries: int,
):
    top = level == "top_total"
    return {
        "year": year,
        "geometry_large": large,
        "geometry_middle": "합계" if top else large,
        "geometry_small": "합계" if top else "평지",
        "hierarchy_level": level,
        "accident_count": accidents,
        "fatality_count": fatalities,
        "injury_count": injuries,
    }


def _valid_rows():
    rows = []
    values = {
        "커브,곡각": (100, 2, 120),
        "직선": (1000, 10, 1000),
        "기타구역": (10, 0, 12),
    }
    for year in (2018, 2019, 2020):
        for large, measures in values.items():
            rows.append(
                _row(
                    year=year,
                    large=large,
                    level="top_total",
                    accidents=measures[0],
                    fatalities=measures[1],
                    injuries=measures[2],
                )
            )
            rows.append(
                _row(
                    year=year,
                    large=large,
                    level="leaf",
                    accidents=measures[0],
                    fatalities=measures[1],
                    injuries=measures[2],
                )
            )
    return rows


def test_loader_normalizes_bom_whitespace_and_comma_numbers(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text(
        "\ufeff기준 연도,도로선형 대분류,도로선형 중분류,"
        "도로선형 소분류,사고 건수,사망자 수,부상자 수\n"
        '2020,"커브,곡각 ",합계,합계,"1,000",12,"1,500"\n',
        encoding="utf-8",
    )

    rows, metadata = load_accident_rows(path)

    assert metadata["bytes"] > 0
    assert rows == [
        {
            "year": 2020,
            "geometry_large": "커브,곡각",
            "geometry_middle": "합계",
            "geometry_small": "합계",
            "hierarchy_level": "top_total",
            "accident_count": 1000,
            "fatality_count": 12,
            "injury_count": 1500,
        }
    ]


def test_profile_reconciles_hierarchy_without_double_counting():
    report = profile_accident_rows(
        _valid_rows(),
        source_metadata={
            "sha256": SOURCE_SHA256,
            "hash_matches_pinned_source": True,
        },
    )

    assert report["status"] == "pass_with_limitations"
    assert report["failed_checks"] == []
    assert report["row_count"] == 18
    assert len(report["reconciliations"]) == 9
    assert all(item["passed"] for item in report["reconciliations"])


def test_profile_fails_duplicate_composite_grain():
    rows = _valid_rows()
    rows.append(dict(rows[0]))

    report = profile_accident_rows(
        rows,
        source_metadata={
            "sha256": SOURCE_SHA256,
            "hash_matches_pinned_source": True,
        },
    )

    assert report["status"] == "fail"
    assert "composite_key_uniqueness" in report["failed_checks"]


def test_severity_prior_uses_top_totals_and_straight_baseline():
    priors = build_geometry_severity_priors(_valid_rows())

    assert priors["curve"]["source_accident_count"] == 300
    assert priors["straight"]["source_accident_count"] == 3000
    assert priors["curve"]["fatalities_per_100_accidents"] == 2.0
    assert priors["straight"]["fatalities_per_100_accidents"] == 1.0
    assert priors["curve"]["fatality_index_vs_straight"] == 2.0
    assert priors["straight"]["fatality_index_vs_straight"] == 1.0


def test_geometry_metrics_distinguish_straight_and_curved_paths():
    straight = geometry_metrics("LINESTRING (126.0 33.0,126.01 33.0)")
    curved = geometry_metrics(
        "LINESTRING (126.0 33.0,126.005 33.005,126.01 33.0)"
    )

    assert straight is not None
    assert curved is not None
    assert straight["link_sinuosity"] == 1.0
    assert curved["link_sinuosity"] > 1.02


def test_link_prior_preserves_one_row_per_unique_link():
    priors = build_geometry_severity_priors(_valid_rows())
    rows, report = build_link_geometry_priors(
        [
            {
                "link_id": "4050000001",
                "geometry_wkt": "LINESTRING (126.0 33.0,126.01 33.0)",
            },
            {
                "link_id": "4050000002",
                "geometry_wkt": (
                    "LINESTRING (126.0 33.0,126.005 33.005,126.01 33.0)"
                ),
            },
        ],
        priors,
    )

    assert report["failed_checks"] == []
    assert report["mapping_status_counts"] == {"matched": 2}
    assert report["geometry_proxy_class_counts"] == {
        "curve": 1,
        "straight": 1,
    }
    assert rows[0]["fatality_index_vs_straight"] == 1.0
    assert rows[1]["fatality_index_vs_straight"] == 2.0


def test_link_prior_index_reports_duplicate_links():
    index, profile = index_link_geometry_priors(
        [
            {"link_id": "4050000001", "mapping_status": "matched"},
            {"link_id": "4050000001", "mapping_status": "matched"},
        ]
    )

    assert list(index) == ["4050000001"]
    assert profile["duplicate_link_rows"] == 1
