#!/usr/bin/env python3
"""Prepare reproducible deck evidence and preserve the two original cover slides."""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05_src"))
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def prepare(source: Path, snapshot: Path, output: Path) -> None:
    from roadops.replanning import build_partial_replan

    output.mkdir(parents=True, exist_ok=True)
    media = output / "source-media"
    media.mkdir(exist_ok=True)
    with ZipFile(source) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/media/"):
                (media / Path(name).name).write_bytes(archive.read(name))
    frozen = json.loads(snapshot.read_text())
    assert frozen["generatedAt"] == "2026-11-19T17:40:14.240939+09:00"
    queries = frozen["queries"]
    ids = ["link:4050484600:h0", "link:4050429802:h0", "link:4060024900:h0"]
    tasks = [copy.deepcopy(next(t for t in queries["field_tasks"]["rows"] if t["task_id"] == i)) for i in ids]
    resources = json.loads((ROOT / "config/resource_scenarios/demo_three_teams_v0_1.json").read_text())
    resources["teams"] = [t for t in resources["teams"] if t["team_id"] == "team-north"]
    resources["vehicles"] = [v for v in resources["vehicles"] if v["vehicle_id"] == resources["teams"][0]["vehicle_id"]]
    resources["planning"]["planning_start_at"] = "2026-11-19T17:40:14+09:00"
    resources["teams"][0].update(shift_start_at="2026-11-19T17:40:14+09:00", shift_end_at="2026-11-19T19:40:14+09:00")
    resources["constraints"] = {"mandatory_link_ids": ["4060024900"], "excluded_link_ids": [], "fixed_assignments": [], "task_overrides": []}
    routes = queries["travel_route_options"]["rows"]
    route_index = {(r["origin_id"], r["destination_task_id"]): r for r in routes}
    elapsed, origin, assignments = 0.0, "team-north", []
    for sequence, task in enumerate(tasks, 1):
        route = route_index[(origin, task["task_id"])]
        elapsed += route["travel_time_minutes"] + task["service_minutes"]
        assignments.append({**task, "team_id": "team-north", "sequence": sequence,
            "origin_id": origin, "destination_task_id": task["task_id"],
            "travel_minutes": route["travel_time_minutes"], "distance_km": route["distance_km"],
            "cumulative_minutes": round(elapsed, 3), "route_link_ids": route["route_link_ids"],
            "route_status": "ok", "route_id": route["route_id"], "fixed_assignment": False})
        origin = task["task_id"]
    summary = {"team_id": "team-north", "available_minutes": 120, "assignment_count": 3,
        "task_ids": ids, "travel_minutes": round(sum(a["travel_minutes"] for a in assignments), 3),
        "service_minutes": 45, "elapsed_minutes": round(elapsed, 3), "remaining_minutes": round(120-elapsed, 3)}
    assert summary["elapsed_minutes"] == 101.182 and summary["travel_minutes"] == 56.182
    base = {"alternative_id": "safety_first", "assignments": assignments, "team_summaries": [summary],
        "unassigned_tasks": [], "constraint_violations": [],
        "metrics": {"constraint_violation_count": 0, "risk_weighted_coverage_ratio": 1,
            "network_total_travel_minutes": summary["travel_minutes"], "maximum_team_elapsed_minutes": summary["elapsed_minutes"],
            "unassigned_task_count": 0},
        "plan_fingerprint": hashlib.sha256(json.dumps(assignments, sort_keys=True).encode()).hexdigest()}
    closed = "4050430101"
    assert closed in assignments[1]["route_link_ids"]
    matrix = {"routes": copy.deepcopy(routes), "closed_link_ids": [closed],
        "route_semantics": "saved_ITS_speed_routes_with_injected_closure"}
    for route in matrix["routes"]:
        if closed in route["route_link_ids"]:
            route.update(status="unavailable", travel_time_minutes=None, failure_reason="closed_link_in_saved_route")
    scenario = {"scenario_type": "road_closure", "affected_link_ids": [closed],
        "semantics": "what_if_not_observed_road_closure", "reason_code": "road_closure_what_if_injected"}
    result, report = build_partial_replan(resources, tasks, {"alternatives": [base]}, matrix, scenario, completed_task_ids=[ids[0]])
    assert report["status"] == "pass", report
    assert result["change_diff"]["preserved_completed_task_ids"] == [ids[0]]
    assert result["replanned_plan"]["team_summaries"][0]["elapsed_minutes"] == 84.9
    assert [r["task_id"] for r in result["replanned_plan"]["unassigned_tasks"]] == [ids[1]]
    assert result["replanned_plan"]["constraint_violations"] == []
    evidence = {"snapshot_at": frozen["generatedAt"], "source_snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "method": "Use the same Yongdam team and three-task route as the UI capture. Mark the first task completed, then exclude cached routes crossing the injected closed link. Do not fabricate a new detour or observed incident.",
        "limitations": ["Separate local scenario execution, not a completed browser dispatch or automatically approved replan.",
            "No new road-network detour search. A task is withheld when available cached routes cross the closure.",
            "84.9 minutes includes the preserved completed visit. The decrease from 101.2 is due to one withheld visit, not an efficiency gain.",
            "Inherited engine wording about speed-limit-only times is generic; this input uses frozen UI ITS-speed route options with fallback speeds."],
        "resources": resources, "tasks": tasks, "base": base, "result": result, "report": report}
    (output / "continuous-replan.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(json.dumps({"status": "pass", "initial_minutes": 101.182, "replanned_minutes": 84.9, "withheld": 1}))


def merge(source: Path, candidate: Path, output: Path) -> None:
    """Keep the original package and replace only slides 3–17 and their new assets.

    Original slide 1/2 XML, relationships, fonts, layouts and media remain byte-identical.
    New chart/image/note dependencies get a separate OPC namespace.
    """
    with ZipFile(source) as z:
        original = {n: z.read(n) for n in z.namelist()}
    with ZipFile(candidate) as z:
        generated = {n: z.read(n) for n in z.namelist()}
    files = dict(original)
    types = etree.fromstring(original["[Content_Types].xml"])
    gen_types = etree.fromstring(generated["[Content_Types].xml"])
    override = {x.get("PartName").lstrip("/"): x.get("ContentType") for x in gen_types if x.tag.endswith("Override")}
    defaults = {x.get("Extension"): x.get("ContentType") for x in gen_types if x.tag.endswith("Default")}
    existing_types = {x.get("PartName") for x in types if x.tag.endswith("Override")}
    mapped = {f"ppt/slides/slide{i}.xml": f"ppt/slides/slide{i}.xml" for i in range(1, 18)}

    def rel_path(part):
        return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part)+".rels")

    def resolve(part, target):
        return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))

    def content_type(old, new):
        key = "/"+new
        if key not in existing_types:
            typ = override.get(old) or defaults.get(old.rsplit(".", 1)[-1])
            if typ:
                etree.SubElement(types, "{"+CT+"}Override", PartName=key, ContentType=typ)
                existing_types.add(key)

    def copy_part(old):
        if old in mapped:
            return mapped[old]
        new = "ppt/workflow_v04/"+old
        mapped[old] = new
        files[new] = generated[old]
        content_type(old, new)
        if rel_path(old) in generated:
            rels = etree.fromstring(generated[rel_path(old)])
            for rel in rels:
                if rel.get("TargetMode") == "External":
                    continue
                dest = copy_part(resolve(old, rel.get("Target")))
                rel.set("Target", posixpath.relpath(dest, posixpath.dirname(new)))
            files[rel_path(new)] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
        return new

    for i in range(3, 18):
        part = f"ppt/slides/slide{i}.xml"
        files[part] = generated[part]
        rels = etree.fromstring(generated[rel_path(part)])
        old_rels = etree.fromstring(original[rel_path(part)])
        old_layout = next(x.get("Target") for x in old_rels if x.get("Type").endswith("/slideLayout"))
        for rel in rels:
            if rel.get("TargetMode") == "External":
                continue
            if rel.get("Type").endswith("/slideLayout"):
                rel.set("Target", old_layout)
            else:
                rel.set("Target", posixpath.relpath(copy_part(resolve(part, rel.get("Target"))), posixpath.dirname(part)))
        files[rel_path(part)] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
    files["[Content_Types].xml"] = etree.tostring(types, xml_declaration=True, encoding="UTF-8", standalone=True)
    for i in [1, 2]:
        part = f"ppt/slides/slide{i}.xml"
        assert files[part] == original[part]
        assert files[rel_path(part)] == original[rel_path(part)]
    for name in original:
        if name.startswith(("ppt/media/", "ppt/fonts/", "ppt/theme/", "ppt/slideLayouts/", "ppt/slideMasters/")):
            assert files[name] == original[name]
    with ZipFile(output, "w", ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    with ZipFile(output) as z:
        assert z.testzip() is None
    print(json.dumps({"preserved_original_slides": [1, 2], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action == "prepare":
        prepare(*(Path(p) for p in args))
    elif action == "merge":
        merge(*(Path(p) for p in args))
    else:
        raise SystemExit("Use prepare SOURCE SNAPSHOT BUILD or merge SOURCE CANDIDATE OUTPUT")
