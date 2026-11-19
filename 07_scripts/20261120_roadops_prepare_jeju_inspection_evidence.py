#!/usr/bin/env python3
"""Build audited Hub inspection evidence from downloaded official CSV files."""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))
from roadops.jeju_inspection_evidence import build_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Directory containing surface.csv, hotspots_hub.csv, steep_slopes.csv, natural_hazards.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "demo/jeju_inspection_evidence_v0_1.json")
    parser.add_argument("--retrieved-at", default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
                        help="Official CSV retrieval date (YYYY-MM-DD)")
    args = parser.parse_args()
    result = build_evidence(*(args.input_dir / name for name in (
        "surface.csv", "hotspots_hub.csv", "steep_slopes.csv", "natural_hazards.csv")))
    datetime.strptime(args.retrieved_at, "%Y-%m-%d")
    result["retrieved_at"] = args.retrieved_at
    result["source_notes"] = {
        "891": "제주데이터허브 첨부 CSV 전체 96행. 2005–2020년, 빈값은 결측으로 유지.",
        "863": "허브 공개 미리보기 CSV 36행(2017–2022). API 총 42행과 범위가 달라 전체 API 수집으로 표시하지 않음.",
        "435_436": "허브가 연결한 공공데이터포털의 2026-06-30 기준 최신 원본. 좌표 없음. 해제 지구 제외; 사업 완료와 지정 해제 구분.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["quality"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
