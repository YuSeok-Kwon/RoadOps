import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { createWorkflowState } from "../src/content/dashboard/workflow-policy.js";
import { optimizeAllocation } from "../src/content/dashboard/web-optimizer.js";

const snapshot = JSON.parse(fs.readFileSync(new URL("../src/data.json", import.meta.url), "utf8"));
const rows = (queryId) => snapshot.queries[queryId].rows;

function initialState() {
  return createWorkflowState({
    teams: rows("teams"),
    tasks: rows("field_tasks"),
    routes: rows("plan_routes"),
    planId: "safety_first",
  });
}

test("browser exact solver reproduces the reviewed Python baseline", () => {
  const result = optimizeAllocation({
    state: initialState(),
    routeOptions: rows("travel_route_options"),
    routeLinks: rows("travel_route_links"),
  });
  assert.equal(result.status, "pass");
  const routeProjection = (route) => ({
    alternative_id: route.alternative_id,
    team_id: route.team_id,
    sequence: route.sequence,
    task_id: route.task_id,
    travel_minutes: route.travel_minutes,
    service_minutes: route.service_minutes,
    cumulative_minutes: route.cumulative_minutes,
    route_link_count: route.route_link_count,
  });
  const routeOrder = (route) => `${route.alternative_id}:${route.team_id}:${route.sequence}`;
  const expectedRoutes = rows("plan_routes").map(routeProjection).sort((left, right) => routeOrder(left).localeCompare(routeOrder(right)));
  const actualRoutes = result.planRoutes.map(routeProjection).sort((left, right) => routeOrder(left).localeCompare(routeOrder(right)));
  assert.deepEqual(actualRoutes, expectedRoutes);
  const expected = rows("plan_metrics").map((metric) => ({
    alternative_id: metric.alternative_id,
    assigned_task_count: metric.assigned_task_count,
    assigned_priority_sum: metric.assigned_priority_sum,
    network_total_travel_minutes: metric.network_total_travel_minutes,
    maximum_team_elapsed_minutes: metric.maximum_team_elapsed_minutes,
    workload_count_variance: metric.workload_count_variance,
  }));
  const actual = result.planMetrics.map((metric) => ({
    alternative_id: metric.alternative_id,
    assigned_task_count: metric.assigned_task_count,
    assigned_priority_sum: metric.assigned_priority_sum,
    network_total_travel_minutes: metric.network_total_travel_minutes,
    maximum_team_elapsed_minutes: metric.maximum_team_elapsed_minutes,
    workload_count_variance: metric.workload_count_variance,
  }));
  assert.deepEqual(actual, expected);
  assert.ok(result.planRoutes.every((route) => JSON.parse(route.geometry_json).length > 0));
});

test("unavailable fixed team returns an explainable infeasible result", () => {
  const state = initialState();
  state.resources.find((team) => team.teamId === "team-east").available = false;
  const result = optimizeAllocation({
    state,
    routeOptions: rows("travel_route_options"),
    routeLinks: rows("travel_route_links"),
  });
  assert.equal(result.status, "fail");
  assert.equal(result.failureReason, "team_has_no_route");
  assert.match(result.message, /고정 업무/);
});

test("manual priority is included in a fresh feasible optimization", () => {
  const state = initialState();
  const task = state.tasks.find((item) => item.fixed && !item.excluded);
  task.manualPriorityLevel = "first";
  task.priorityReason = "현장 민원 다수 접수";
  const result = optimizeAllocation({
    state,
    routeOptions: rows("travel_route_options"),
    routeLinks: rows("travel_route_links"),
  });
  assert.equal(result.status, "pass");
  assert.equal(result.planMetrics[0].manual_priority_override_count, 1);
  assert.ok(result.planRoutes.some((route) => route.alternative_id === "safety_first" && route.task_id === task.taskId));
});
