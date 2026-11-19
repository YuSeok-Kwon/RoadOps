#!/usr/bin/env python3
"""Freeze presentation evidence without modifying the dashboard or operational outputs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))
from roadops.forecast_validation import validate_forecast_snapshots
from roadops.priority_policy import calculate_priority, validate_policy

DEST = ROOT / "04_docs/presentation/assets/roadops_submission_20261119"


def main():
    sources = {}

    def read(name):
        raw = (ROOT / name).read_bytes()
        sources[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    dashboard = read("08_dashboard/roadops_map_v0_1/src/data.json")
    queries = dashboard["queries"]
    risks = queries["risk_links"]["rows"]
    chosen = next(row for row in risks if str(row["link_id"]) == "4050005521" and row["horizon_hours"] == 0)
    policy = validate_policy(json.loads(chosen["scoring_policy_json"]))
    version = chosen["forecast_version"]
    evaluated = [(candidate, calculate_priority(candidate, policy)) for candidate in chosen["priority_candidates"]]
    candidate, result = max(evaluated, key=lambda pair: pair[1]["score"] if pair[1]["score"] is not None else -1)
    assert abs(result["score"] - chosen["priority_score"]) <= 0.001
    assert abs(sum(row["contribution"] or 0 for row in result["factors"]) - result["score"]) <= 0.001
    complete = calculate_priority(candidate, {**policy, "method": "complete"})

    snapshots = []
    for path in sorted((ROOT / "02_outputs/data/forecast_validation_v0_1/archive").glob("*.json")):
        snapshot = read(path.relative_to(ROOT).as_posix())
        selected = [row for row in snapshot["rows"] if row.get("forecast_version") == version]
        if selected and snapshot["generated_at"] <= dashboard["generatedAt"]:
            snapshots.append({**snapshot, "rows": selected})
    report, matched = validate_forecast_snapshots(snapshots, generated_at=datetime.fromisoformat(dashboard["generatedAt"]))
    legacy = read("02_outputs/data/allocation_evaluation_v0_1/allocation_evaluation.json")
    resilience = read("02_outputs/data/resilience_evaluation_v0_1/quality_report.json")
    replanning = read("02_outputs/data/partial_replanning_v0_1/replanning_scenarios.json")
    assert abs((datetime.fromisoformat(replanning["generated_at"]) - datetime.fromisoformat(dashboard["generatedAt"])).total_seconds()) < 300
    simplified_replans = []
    for scenario in replanning["scenario_results"]:
        simplified_replans.append({key: scenario[key] for key in ["scenario", "affected_team_ids", "completed_task_ids", "change_diff", "manual_approval_required"]})
    evidence = {
        "schema_version": 1,
        "presentation_revision": "v0.3",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "snapshot_at": dashboard["generatedAt"],
        "score_version": version,
        "policy_example": policy,
        "policy_example_semantics": "Editable initial setting used only for this frozen example; not a fixed scoring formula or accident-probability model.",
        "selected_road": {key: chosen.get(key) for key in ["link_id", "road_name", "location_label", "target_at", "generated_at", "quality_flags"]},
        "selected_road_input": candidate,
        "selected_road_result": result,
        "selected_road_complete_result": complete,
        "forecast_validation_current_version": report,
        "forecast_matched_current_version": matched,
        "forecast_snapshots_current_version": snapshots,
        "forecast_validation_combined_legacy_and_current": queries["forecast_validation"]["rows"],
        "legacy_allocation_evaluation_date": "2026-11-13",
        "legacy_allocation_evaluation": legacy,
        "resilience_evaluation_date": "2026-11-16T12:00:00+09:00",
        "resilience_evaluation": resilience,
        "replanning": {"generated_at": replanning["generated_at"], "scenarios": simplified_replans},
        "teams": queries["teams"]["rows"],
        "crime_map": [{key: value for key, value in row.items() if key != "data_url"} for row in queries["crime_caution_overlay"]["rows"]],
        "crime_statistics": queries["crime_statistics"]["rows"],
        "weather": queries["weather_forecast"]["rows"],
        "source_sha256": sources,
    }
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "implementation_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"snapshot_at": evidence["snapshot_at"], "score_version": version, "road_score": result["score"], "road_factors": [{key: row.get(key) for key in ["key", "weight", "value", "coverage", "contribution", "status"]} for row in result["factors"]], "forecast_samples": {row["horizon_hours"]: row["matched_points"] for row in report["metrics"] if row["horizon_hours"]}, "replanning": [{"scenario": row["scenario"]["scenario_type"], "affected": row["affected_team_ids"]} for row in simplified_replans]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
