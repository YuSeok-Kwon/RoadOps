from roadops.crime_statistics import normalize_jeju_crime_statistics, parse_crime_csv


def test_parse_official_cp949_csv():
    content = "범죄대분류,범죄중분류,제주 제주시,제주 서귀포시\n강력범죄,강도,20,1\n".encode("cp949")
    rows = parse_crime_csv(content)
    assert rows[0]["제주 제주시"] == "20"


def test_normalize_keeps_city_grain_and_prevents_hotspot_claim():
    records = normalize_jeju_crime_statistics(
        [
            {"범죄대분류": "강력범죄", "범죄중분류": "강도", "제주 제주시": "20", "제주 서귀포시": "1"},
            {"범죄대분류": "폭력범죄", "범죄중분류": "폭행", "제주 제주시": "100", "제주 서귀포시": "30"},
        ]
    )
    jeju = next(row for row in records if row["administrative_city"] == "제주시")
    assert jeju["occurrence_count"] == 120
    assert jeju["map_hotspot_eligible"] is False
    assert jeju["top_categories"][0]["crime_category"] == "폭행"
