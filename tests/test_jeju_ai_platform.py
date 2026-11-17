from roadops.jeju_ai_platform import extract_records, normalize_platform_events


def test_extracts_and_normalizes_platform_events_without_credentials():
    records = extract_records(
        {
            "data": {
                "events": [
                    {
                        "detectId": "P-1",
                        "detectType": "pothole",
                        "detectedAt": "2026-11-17T20:00:00+09:00",
                        "lat": 33.5,
                        "lng": 126.5,
                        "processingStatus": "new",
                    }
                ]
            }
        }
    )
    output, quality = normalize_platform_events(records, fetched_at="2026-11-17T20:01:00+09:00")
    assert quality["normalized_record_count"] == 1
    assert output[0]["event_type_label"] == "포트홀"
    assert output[0]["integration_status"] == "awaiting_standard_link_spatial_match"


def test_rejects_missing_or_out_of_scope_platform_coordinates():
    output, quality = normalize_platform_events(
        [
            {"id": "A", "type": "icing"},
            {"id": "B", "type": "icing", "lat": 37.5, "lng": 127.0},
        ],
        fetched_at="2026-11-17T20:01:00+09:00",
    )
    assert output == []
    assert quality["rejected_counts"] == {
        "missing_coordinate": 1,
        "outside_jeju_bounds": 1,
    }
