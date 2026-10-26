#!/usr/bin/env python3
"""Run a deterministic RoadOps join smoke test with illustrative fixtures.

실제 성과 수치가 아닌 예시 fixture로 RoadOps 결합 규칙을 재현합니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.spatial import audit_event_link_join, build_road_links  # noqa: E402


def main() -> int:
    nodes = [
        {"node_id": "4080000001", "latitude": 33.3260, "longitude": 126.8327},
        {"node_id": "4080000002", "latitude": 33.3270, "longitude": 126.8337},
        {"node_id": "4080000003", "latitude": 33.3280, "longitude": 126.8347},
    ]
    link_rows = [
        {
            "link_id": "4050000001",
            "start_node_id": "4080000001",
            "end_node_id": "4080000002",
        },
        {
            "link_id": "4050000002",
            "start_node_id": "4080000002",
            "end_node_id": "4080000003",
        },
    ]
    events = [
        {"link_id": "4050000001", "latitude": 33.3264, "longitude": 126.8331},
        {"link_id": "9999999999", "latitude": 33.3275, "longitude": 126.8342},
        {"link_id": None, "latitude": 33.5500, "longitude": 126.2000},
    ]

    links, issues = build_road_links(link_rows, nodes)
    audit = audit_event_link_join(events, links, spatial_fallback_threshold_meters=100)
    result = {
        "data_kind": "illustrative_fixture_not_real_jeju_observations",
        "link_build_issue_count": len(issues),
        "join_audit": audit.to_dict(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
