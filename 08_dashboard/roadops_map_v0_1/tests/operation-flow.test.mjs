import assert from "node:assert/strict";
import test from "node:test";

import {
  buildManualRoutes,
  distanceKm,
  historicalPlaces,
  nearbyRows,
  routeSummary,
  tasksForDepot,
} from "../src/content/dashboard/operation-flow.js";

const depots = [{ team_id: "team-a", start_longitude: 126.5, start_latitude: 33.5 }];
const tasks = [
  { task_id: "task-1", link_id: "1", longitude: 126.51, latitude: 33.5, priority_score: 60 },
  { task_id: "task-2", link_id: "2", longitude: 126.55, latitude: 33.5, priority_score: 30 },
];
const routes = [
  { alternative_id: "safety_first", team_id: "team-a", task_id: "task-1", travel_minutes: 8, service_minutes: 12 },
  { alternative_id: "safety_first", team_id: "team-a", task_id: "task-2", travel_minutes: 15, service_minutes: 10 },
];

test("finds depot candidates without preselecting a route", () => {
  assert.deepEqual(tasksForDepot({ tasks, routes, depotId: "team-a", planId: "safety_first" })
    .map((task) => task.task_id), ["task-1", "task-2"]);
  assert.deepEqual(tasksForDepot({ tasks, routes, depotId: null, planId: "safety_first" }), []);
  assert.deepEqual(tasksForDepot({ tasks, routes: [], depotId: "team-a", depot: depots[0], limit: 1 })
    .map((task) => task.task_id), ["task-1"]);
});

test("builds a manual route in the official's click order", () => {
  const routeOptions = [
    { origin_id: "team-a", destination_task_id: "task-2", status: "ok", travel_time_minutes: 7, route_link_ids: ["b"] },
    { origin_id: "task-2", destination_task_id: "task-1", status: "ok", travel_time_minutes: 4, route_link_ids: ["a"] },
  ];
  const routeLinks = [
    { link_id: "a", geometry_json: "[[[126.51,33.5],[126.52,33.5]]]" },
    { link_id: "b", geometry_json: "[[[126.5,33.5],[126.55,33.5]]]" },
  ];
  const result = buildManualRoutes({
    selectedTaskIds: ["task-2", "task-1"], tasks, routes, depotId: "team-a", planId: "safety_first",
    routeOptions, routeLinks,
  });
  assert.deepEqual(result.map((route) => [route.task_id, route.sequence]), [["task-2", 1], ["task-1", 2]]);
  assert.deepEqual(result.map((route) => route.travel_minutes), [7, 4]);
  assert.deepEqual(JSON.parse(result[1].geometry_json), [[[126.51, 33.5], [126.52, 33.5]]]);
  assert.deepEqual(routeSummary(result), { travelMinutes: 11, serviceMinutes: 22 });
});

test("sorts evidence by distance and labels similar-event places", () => {
  assert.ok(distanceKm(depots[0], tasks[0]) < distanceKm(depots[0], tasks[1]));
  assert.equal(nearbyRows(depots[0], tasks, 1)[0].task_id, "task-1");
  const history = historicalPlaces([{ observed_at: "now", event_link_ids: ["2"] }], tasks);
  assert.equal(history[0].matched_places[0].task_id, "task-2");
  const spatialHistory = historicalPlaces([{
    observed_at: "later",
    event_locations: [{ link_id: "provider-2", longitude: 126.5104, latitude: 33.5, event_codes: ["534"] }],
  }], tasks);
  assert.equal(spatialHistory[0].matched_places[0].task_id, "task-1");
  assert.equal(spatialHistory[0].matched_places[0].historical_link_id, "provider-2");
  assert.deepEqual(spatialHistory[0].matched_places[0].historical_event_codes, ["534"]);
});
