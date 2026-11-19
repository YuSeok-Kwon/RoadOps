from roadops.safemap_response_layers import (
    normalize_jeju_facilities,
    web_mercator_to_wgs84,
)


def test_converts_web_mercator_coordinates_to_wgs84():
    longitude, latitude = web_mercator_to_wgs84(14093476.0, 3949000.0)

    assert 126.5 < longitude < 127.0
    assert 33.0 < latitude < 34.0


def test_normalizes_only_jeju_facilities():
    records = [
        {
            "objt_id": "jeju-1",
            "ctprvn_cd": "50",
            "fclty_nm": "제주동부경찰서",
            "fclty_ty": "경찰서",
            "rn_adres": "제주특별자치도 제주시 동광로 66",
            "telno": "064-000-0000",
            "x": "14093476.0",
            "y": "3949000.0",
        },
        {
            "objt_id": "seoul-1",
            "ctprvn_cd": "11",
            "fclty_nm": "서울 시설",
            "rn_adres": "서울특별시 종로구",
            "x": "14100000",
            "y": "4510000",
        },
    ]

    normalized = normalize_jeju_facilities(records, facility_kind="police")

    assert len(normalized) == 1
    assert normalized[0]["facility_name"] == "제주동부경찰서"
    assert normalized[0]["facility_kind"] == "police"
    assert normalized[0]["source_interface_id"] == "IF_0036"
    assert normalized[0]["handoff_role"] == "police"
