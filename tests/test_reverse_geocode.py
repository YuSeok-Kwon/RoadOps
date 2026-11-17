from roadops.reverse_geocode import location_from_nominatim, location_from_sgis, midpoint


def test_midpoint_uses_central_shape_point():
    assert midpoint([[[126.1, 33.1], [126.2, 33.2], [126.3, 33.3]]]) == (33.2, 126.2)


def test_location_does_not_claim_parcel_when_house_number_missing():
    row = location_from_nominatim(
        {"place_id": 1, "display_name": "평화로, 광령리", "address": {"road": "평화로", "village": "광령리", "city": "제주시"}}
    )
    assert row["location_label"] == "제주시 광령리 평화로"
    assert row["address_precision"] == "road_or_locality"
    assert row["intersection_name"] is None


def test_location_marks_building_precision_only_with_number():
    row = location_from_nominatim(
        {"address": {"road": "중앙로", "house_number": "123", "city": "제주시"}}
    )
    assert row["address_precision"] == "parcel_or_building"
    assert row["lot_or_house_number"] == "123"


def test_location_from_sgis_combines_official_parcel_and_road_fields():
    row = location_from_sgis(
        {"errCd": 0, "result": [{"sgg_nm": "제주시", "emdong_nm": "애월읍", "main_no": "123", "sub_no": "4"}]},
        {"errCd": 0, "result": [{"road_nm": "평화로", "road_nm_main_no": "99", "road_nm_sub_no": "0"}]},
    )
    assert row["location_label"] == "제주시 애월읍 평화로 99"
    assert row["lot_or_house_number"] == "123-4"
    assert row["address_precision"] == "official_parcel"
    assert row["provider"] == "SGIS 국가데이터처"
