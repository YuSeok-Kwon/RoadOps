#!/usr/bin/env python3
"""Extract Jeju CSVs from an official national node-link SHP archive.

공식 국가표준 노드링크 SHP 압축파일에서 제주 CSV를 추출합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.nodelink import extract_jeju_nodelink  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--extract-dir",
        type=Path,
        default=PROJECT_ROOT / "01_raw_data" / "external" / "molit_nodelink_extracted",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs" / "interim" / "molit_nodelink_jeju",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = extract_jeju_nodelink(
        args.archive,
        extract_dir=args.extract_dir,
        output_dir=args.output_dir,
    )
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
