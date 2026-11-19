"""Independently verify the frozen Sogil detour case with the Python router."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))
from roadops.quality import load_records  # noqa: E402
from roadops.travel_time import build_travel_time_matrix  # noqa: E402
from roadops.replanning import build_partial_replan  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-dir", type=Path, default=ROOT / "02_outputs/interim/molit_nodelink_jeju_20261014")
    args = parser.parse_args()
    case = json.loads((ROOT / "tests/fixtures/roadops_sogil_detour.json").read_text())
    matrix, matrix_report = build_travel_time_matrix(
        case["resources"], case["tasks"],
        load_records(args.network_dir / "jeju_nodes.csv"),
        load_records(args.network_dir / "jeju_links.csv"),
        closed_link_ids=case["closedLinkIds"],
    )
    assert matrix_report["status"] == "pass", matrix_report
    result, report = build_partial_replan(
        case["resources"], case["tasks"], {"alternatives": [case["base"]]}, matrix,
        {"scenario_type": "road_closure", "affected_link_ids": case["closedLinkIds"],
         "semantics": "what_if_not_observed_road_closure"},
        completed_task_ids=[row["task_id"] for row in case["base"]["assignments"][:case["completedCount"]]],
    )
    assert report["status"] == "pass", report
    routes = result["replanned_plan"]["assignments"]
    assert len(routes) == len(case["expectedAssignments"])
    for actual, expected in zip(routes, case["expectedAssignments"]):
        for key in ["task_id", "route_link_ids", "travel_minutes", "service_minutes", "cumulative_minutes"]:
            assert actual[key] == expected[key], (key, actual[key], expected[key])
    for route in routes[case["completedCount"]:]:
        assert not set(route["route_link_ids"]) & set(case["closedLinkIds"])
    print(json.dumps({"status": "pass", "task_ids": [row["task_id"] for row in routes],
                      "total_minutes": routes[-1]["cumulative_minutes"],
                      "time_basis": "preserved_completed_leg_plus_speed_limit_estimates"}))


if __name__ == "__main__":
    main()
