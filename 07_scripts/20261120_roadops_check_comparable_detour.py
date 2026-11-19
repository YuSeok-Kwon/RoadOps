"""Verify both remaining itineraries against the independent Python CSV router."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))
from roadops.quality import load_records  # noqa: E402
from roadops.travel_time import build_travel_time_matrix  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-dir", type=Path, default=ROOT / "02_outputs/interim/molit_nodelink_jeju_20261014")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "999_Temporary/roadops_detour_1213_20261120")
    args = parser.parse_args()
    case = json.loads((ROOT / "tests/fixtures/roadops_sogil_detour.json").read_text())
    web = json.loads((args.build_dir / "verified-result.json").read_text())
    nodes = load_records(args.network_dir / "jeju_nodes.csv")
    links = load_records(args.network_dir / "jeju_links.csv")
    legs = []
    for stage, closures, assignments, total in [
        ("before", [], web["comparison"]["beforeRoutes"], 100.570),
        ("after", ["4050000302"], web["routes"], 125.613),
    ]:
        matrix, report = build_travel_time_matrix(case["resources"], case["tasks"], nodes, links, closed_link_ids=closures)
        assert report["status"] == "pass", report
        accumulated = 39.8  # Identical declared simulation input, not an observed duration.
        for previous, assignment in zip(assignments, assignments[1:]):
            route = next(r for r in matrix["routes"] if r["origin_id"] == previous["task_id"] and r["destination_task_id"] == assignment["task_id"])
            assert route["status"] == "ok", route
            assert route["route_link_ids"] == assignment["route_link_ids"]
            assert route["travel_time_minutes"] == assignment["travel_minutes"]
            assert assignment["service_minutes"] == 15
            assert not set(closures).intersection(route["route_link_ids"])
            accumulated += route["travel_time_minutes"] + 15
            legs.append({"stage": stage, "task": assignment["task_id"], "minutes": route["travel_time_minutes"], "linkCount": len(route["route_link_ids"])})
        assert round(accumulated, 3) == total
        (args.build_dir / f"python-{stage}.json").write_text(json.dumps(matrix, ensure_ascii=False))
    assert "4050000302" in web["comparison"]["beforeRoutes"][2]["route_link_ids"]
    assert round(web["totalMinutes"] - web["comparison"]["beforeTotalMinutes"], 3) == 25.043
    assert round(web["totalMinutes"] - 120, 3) == 5.613
    result = {"status": "pass", "basis": "Independent Python CSV and JavaScript browser routers agree on every remaining route link and time", "legs": legs}
    (args.build_dir / "independent-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
