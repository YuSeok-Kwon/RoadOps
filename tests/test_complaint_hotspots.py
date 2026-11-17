import pytest

from roadops.complaint_hotspots import aggregate_complaint_hotspots


def test_aggregates_complaints_without_retaining_exact_points_or_ids():
    rows = [
        {
            "접수번호": f"C-{index}",
            "접수일시": "2026-11-17 10:00:00",
            "민원유형": "포트홀",
            "위도": f"{33.5001 + index * 0.0001}",
            "경도": f"{126.5001 + index * 0.0001}",
            "처리상태": "접수",
        }
        for index in range(3)
    ]

    records, quality = aggregate_complaint_hotspots(rows)

    assert quality["status"] == "ready"
    assert quality["exact_coordinates_retained"] is False
    assert records[0]["complaint_count"] == 3
    assert "complaint_id" not in records[0]
    assert records[0]["latitude"] != float(rows[0]["위도"])


def test_suppresses_cells_below_minimum_count():
    records, quality = aggregate_complaint_hotspots(
        [
            {"latitude": 33.5, "longitude": 126.5, "category": "낙하물"},
            {"latitude": 33.5001, "longitude": 126.5001, "category": "낙하물"},
        ]
    )
    assert records == []
    assert quality["suppressed_complaint_count"] == 2


def test_rejects_personal_or_free_text_columns_before_processing():
    with pytest.raises(ValueError, match="unsafe_personal_or_free_text_fields"):
        aggregate_complaint_hotspots(
            [
                {
                    "latitude": 33.5,
                    "longitude": 126.5,
                    "신고자성명": "홍길동",
                }
            ]
        )
