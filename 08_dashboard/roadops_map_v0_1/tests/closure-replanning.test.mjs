import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createWorkflowState } from "../src/content/dashboard/workflow-policy.js";
import { replanClosure } from "../src/content/dashboard/closure-replanning.js";
import { createRouter } from "../src/content/dashboard/network-routing.js";

const fixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/roadops_sogil_detour.json", import.meta.url)));
const network = JSON.parse(fs.readFileSync(new URL("../src/content/assets/routing-network.json", import.meta.url)));
function input() {
  const depot = { ...fixture.resources.teams[0], available_minutes: 120, max_tasks_per_team: 3,
    vehicle_personnel_capacity: 2, vehicle_equipment: fixture.resources.vehicles[0].equipment };
  const baseRoutes = fixture.base.assignments.map((row) => ({ ...structuredClone(row), alternative_id: "safety_first" }));
  return { network, depot, baseRoutes, taskRows: fixture.tasks,
    state: createWorkflowState({ teams: [depot], tasks: fixture.tasks, routes: baseRoutes }),
    completedCount: fixture.completedCount, closedLinkIds: fixture.closedLinkIds };
}

test("Sogil detour agrees with independent Python routing and preserves completed work", () => {
  const args = input();
  const before = JSON.stringify(args.state);
  assert.ok(args.baseRoutes[1].route_link_ids.includes(fixture.closedLinkIds[0]));
  const result = replanClosure(args);
  assert.equal(result.status, "pass");
  assert.equal(result.totalMinutes, 100.563);
  assert.equal(result.remainingMinutes, 60.77);
  assert.equal(result.spareMinutes, 19.437);
  assert.equal(result.unassigned.length, 0);
  assert.deepEqual(result.routes[0], { ...args.baseRoutes[0], replan_status: "completed_preserved" });
  result.routes.forEach((row, index) => {
    const expected = fixture.expectedAssignments[index];
    for (const key of ["task_id", "sequence", "travel_minutes", "service_minutes", "cumulative_minutes", "route_link_ids"]) {
      assert.deepEqual(row[key], expected[key], `${index}: ${key}`);
    }
  });
  for (const row of result.routes.slice(1)) {
    assert.ok(row.route_link_ids.length > 0);
    assert.ok(!row.route_link_ids.some((id) => fixture.closedLinkIds.includes(id)));
    assert.ok(JSON.parse(row.geometry_json).length > 0);
  }
  assert.equal(result.manualApprovalRequired, true);
  assert.equal(result.approvalStatus, "pending");
  assert.equal(result.timeBasis, "speed_limit_or_default");
  assert.equal(JSON.stringify(args.state), before);
});

test("unknown closure does not silently reuse the original route", () => {
  const result = replanClosure({ ...input(), closedLinkIds: ["unknown-link"] });
  assert.equal(result.status, "fail");
  assert.deepEqual(result.routes, []);
  assert.match(result.message, /없는 통제 구간/);
});

test("same-basis comparison reveals a real 1100-road detour and warns about overtime", () => {
  const result = replanClosure({ ...input(), closedLinkIds: ["4050000302"], elapsedMinutes: 39.8, preserveVisitOrder: true });
  assert.equal(result.status, "pass");
  assert.equal(result.comparison.beforeTotalMinutes, 100.57);
  assert.equal(result.totalMinutes, 125.613);
  assert.equal(result.comparison.additionalMinutes, 25.043);
  assert.equal(result.overtimeMinutes, 5.613);
  assert.equal(result.remainingMinutes, 85.813);
  assert.equal(result.comparison.changedLegCount, 1);
  assert.equal(result.previewOnly, true);
  assert.equal(result.approvalStatus, "review_required");
  assert.deepEqual(result.routes.map(row => row.task_id), fixture.base.assignments.map(row => row.task_id));
  assert.deepEqual(result.routes[0], result.comparison.beforeRoutes[0]);
  assert.ok(result.comparison.beforeRoutes[2].route_link_ids.includes("4050000302"));
  assert.ok(result.routes.slice(1).every(row => !row.route_link_ids.includes("4050000302")));
  result.routes.slice(1).forEach((row, i) => assert.equal(row.service_minutes, result.comparison.beforeRoutes[i + 1].service_minutes));
});

test("comparison does not attribute an unchanged route to an irrelevant closure", () => {
  const result = replanClosure({ ...input(), preserveVisitOrder: true });
  assert.equal(result.status, "pass");
  assert.equal(result.comparison.additionalMinutes, 0);
  assert.equal(result.comparison.changedLegCount, 0);
  assert.equal(result.totalMinutes, result.comparison.beforeTotalMinutes);
});

test("visit-preserving preview never fabricates access to a closed destination", () => {
  const result = replanClosure({ ...input(), preserveVisitOrder: true, closedLinkIds: ["4060024900"] });
  assert.equal(result.status, "fail");
  assert.deepEqual(result.routes, []);
  assert.match(result.message, /대상 도로 자체가 통제/);
  const args = input(); args.baseRoutes[1].service_minutes = null;
  assert.equal(replanClosure({ ...args, preserveVisitOrder: true }).status, "fail");
});

test("closed destination is withheld while the required Yerae visit remains", () => {
  const result = replanClosure({ ...input(), closedLinkIds: [...fixture.closedLinkIds, "4050429802"] });
  assert.equal(result.status, "pass");
  assert.deepEqual(result.routes.map((row) => row.link_id), ["4050484600", "4060024900"]);
  assert.equal(result.unassigned[0].link_id, "4050429802");
  assert.match(result.unassigned[0].reason, /대상 도로 자체가 통제/);
});

test("infeasible required visit fails instead of presenting an incomplete approved plan", () => {
  const result = replanClosure({ ...input(), closedLinkIds: [...fixture.closedLinkIds, "4060024900"] });
  assert.equal(result.status, "fail");
  assert.deepEqual(result.routes, []);
  assert.equal(result.completedRoutes[0].task_id, fixture.base.assignments[0].task_id);
});

test("remaining budget accounts for actual elapsed time, including completed work", () => {
  const result = replanClosure({ ...input(), elapsedMinutes: 60 });
  assert.equal(result.status, "pass");
  assert.equal(result.spentMinutes, 60);
  assert.ok(result.totalMinutes <= 120);
  assert.equal(result.unassigned.length, 1);
  assert.match(result.unassigned[0].reason, /남은 시간/);
  assert.equal(result.routes.at(-1).link_id, "4060024900");
  assert.equal(result.routes[0].cumulative_minutes, fixture.base.assignments[0].cumulative_minutes);
  assert.equal(result.routes.at(-1).cumulative_minutes, result.totalMinutes);
  assert.equal(replanClosure({ ...input(), elapsedMinutes: 119 }).status, "fail");
});

test("fixed team and mandatory constraints survive replanning", () => {
  const args = input();
  const sogil = args.state.tasks.find((task) => task.linkId === "4050429802");
  sogil.fixed = true;
  sogil.assignedTeamId = "team-west";
  assert.equal(replanClosure(args).status, "fail");
});

test("invalid progress, missing time, and resource changes invalidate the proposed routes", () => {
  for (const change of [{ completedCount: -1 }, { completedCount: 4 }, { elapsedMinutes: -1 }, { elapsedMinutes: NaN }, { closedLinkIds: [] }]) {
    const result = replanClosure({ ...input(), ...change });
    assert.equal(result.status, "fail");
    assert.deepEqual(result.routes, []);
  }
  const args = input(); args.baseRoutes[0].travel_minutes = null;
  assert.equal(replanClosure(args).status, "fail");
  const changed = input(); changed.state.resources[0].available = false;
  assert.equal(replanClosure(changed).status, "fail");
});

test("all completed visits stay intact; no fictitious new travel is added", () => {
  const args = input();
  const result = replanClosure({ ...args, completedCount: 3 });
  assert.equal(result.status, "pass");
  assert.equal(result.remainingMinutes, 0);
  assert.equal(result.routes.length, 3);
  assert.ok(result.routes.every((row) => row.replan_status === "completed_preserved"));
});

test("directed shortest path searches a new detour and never reverses a one-way road", () => {
  const tiny = { schemaVersion: 1, nodes: [["a", 33, 126], ["b", 33, 126.001], ["c", 33.001, 126.001], ["d", 33, 126.002]],
    links: [
      ["ab", "a", "b", 100, 1, [[[126, 33], [126.001, 33]]]],
      ["ac", "a", "c", 200, 2, [[[126, 33], [126.001, 33.001]]]],
      ["cb", "c", "b", 100, 1, [[[126.001, 33.001], [126.001, 33]]]],
      ["bd", "b", "d", 100, 1, [[[126.001, 33], [126.002, 33]]]],
    ] };
  const task = { task_id: "visit", link_id: "bd", longitude: 126.001, latitude: 33 };
  const origin = { node: "a", meters: 0, minutes: 0 };
  assert.deepEqual(createRouter(tiny).route("base", origin, task).route_link_ids, ["ab"]);
  const detour = createRouter(tiny, ["ab"]).route("base", origin, task);
  assert.deepEqual(detour.route_link_ids, ["ac", "cb"]);
  assert.equal(detour.travel_time_minutes, 3);
  assert.equal(createRouter(tiny, ["ab", "ac"]).route("base", origin, task).status, "unavailable");
  assert.equal(createRouter(tiny).route("base", { ...origin, node: "d" }, task).status, "unavailable");
});
