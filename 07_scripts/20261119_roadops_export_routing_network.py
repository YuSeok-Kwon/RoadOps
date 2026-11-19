"""Export the reviewed directed Jeju network for offline browser detours."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from roadops.quality import load_records  # noqa: E402
from roadops.travel_time import build_network_graph  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-dir", type=Path, default=ROOT / "02_outputs/interim/molit_nodelink_jeju_20261014")
    parser.add_argument("--output", type=Path, default=ROOT / "08_dashboard/roadops_map_v0_1/src/content/assets/routing-network.json")
    args = parser.parse_args()
    paths = [args.network_dir / "jeju_nodes.csv", args.network_dir / "jeju_links.csv"]
    nodes, links, _, report = build_network_graph(*(load_records(p) for p in paths))
    payload = {
        "schemaVersion": 1,
        "source": {
            "title": "국토교통부 표준노드링크 제주 도로망",
            "networkDate": "2026-10-14",
            "files": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
            "timeBasis": "speed_limit_or_default",
            "defaultSpeedKph": 30,
            "turnRestrictionsApplied": False,
            "report": report,
        },
        "nodeFields": ["id", "latitude", "longitude"],
        "linkFields": ["id", "start", "end", "meters", "minutes", "geometry"],
        "nodes": [[k, v.latitude, v.longitude] for k, v in sorted(nodes.items())],
        "links": [[k, v.start_node_id, v.end_node_id, v.length_meters, v.travel_minutes,
                   [[[p.longitude, p.latitude] for p in part] for part in v.geometry_parts]]
                  for k, v in sorted(links.items())],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"nodes": len(nodes), "links": len(links), "bytes": args.output.stat().st_size}))


if __name__ == "__main__":
    main()
