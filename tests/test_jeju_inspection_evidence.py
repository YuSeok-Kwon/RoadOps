import unittest
from roadops.jeju_inspection_evidence import normalize_surface, normalize_hazards, normalize_hub_hotspots, merge_hotspots


class JejuInspectionEvidenceTests(unittest.TestCase):
    def test_missing_is_not_zero_and_duplicates_rejected(self):
        row = {"기준 연도": "2020", "노면 상태": "해빙", "사고 건수": "", "부상자 수": "", "사망자 수": ""}
        rows, quality = normalize_surface([row])
        self.assertIsNone(rows[0]["accident_count"])
        self.assertEqual(quality["incomplete_rows"], 1)
        with self.assertRaises(ValueError): normalize_surface([row, row])
        with self.assertRaises(ValueError): normalize_surface([{**row, "사고 건수": "-1"}])

    def test_completion_does_not_mean_release(self):
        row = {"지구명": "검토지구", "위치": "애월읍", "완료여부": "완료", "유형": "침수위험", "위험등급": "나", "비고": "", "데이터기준일자": "2026-06-30"}
        rows = normalize_hazards([row, {**row, "비고": "23.5.10.해제"}], kind="natural_hazard")
        self.assertEqual([r["designation_status"] for r in rows], ["works_completed", "released"])
        self.assertTrue(all(r["latitude"] is None and not r["automatic_road_closure"] for r in rows))

    def test_dedup_does_not_sum_same_year_or_destroy_history(self):
        row = {"hotspot_id": "taas-1", "analysis_year": 2022, "latitude": 33.5, "longitude": 126.5, "accident_count": 12}
        combined = merge_hotspots([row], [{**row, "hotspot_id": "hub-1", "source_url": "hub"}, {**row, "analysis_year": 2021, "hotspot_id": "hub-2"}])
        self.assertEqual(len(combined), 2)
        self.assertEqual(combined[0]["accident_count"], 12)
        self.assertEqual(combined[0]["corroborating_sources"], ["hub"])

    def test_swapped_coordinates_fail(self):
        with self.assertRaises(ValueError):
            normalize_hub_hotspots([{"연도": "2022", "위도": "126.5", "경도": "33.5"}])


if __name__ == "__main__": unittest.main()
