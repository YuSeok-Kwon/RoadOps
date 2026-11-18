import assert from "node:assert/strict";
import test from "node:test";
import { parseDriver, prioritySummary, scoreExplanation } from "../src/content/dashboard/score-explanation.js";

test("516 road explains the score with sensor, speed and accident evidence", () => {
  const row = {
    priority_score: 53.846, event_count: 1,
    risk_drivers: "structural:taas:2.692 | traffic:speed_to_limit_ratio:12.692 | weather_road:cits_visibility:38.462",
  };
  const result = scoreExplanation(row);
  assert.equal(result.available, true);
  assert.equal(result.drivers[0].label, "시야 확보 상태");
  assert.equal(result.remainder, null);
  assert.equal(prioritySummary(row), "시야 확보 상태 38.5점 · 통행속도 저하 12.7점");
});

test("a multi-event road uses the score's own drivers, not the union", () => {
  const row = {
    priority_score: 39.5, event_count: 2,
    risk_drivers: "event:active_road_event:24.500 | traffic:speed_to_limit_ratio:8.077 | weather_road:kma_wind_speed:7.692",
    score_basis_drivers: "event:active_road_event:24.500|traffic:speed_to_limit_ratio:8.250|weather_road:kma_wind_speed:5.000",
  };
  const result = scoreExplanation(row);
  assert.equal(result.available, true);
  assert.equal(result.drivers[1].contribution, 8.25);
  assert.equal(result.remainder, 1.75);
  assert.equal(scoreExplanation({ ...row, score_basis_drivers: undefined }).available, false);
});

test("missing and invalid evidence never becomes a zero-point explanation", () => {
  for (const value of ["", "bad", "Infinity"]) assert.equal(parseDriver(`traffic:occupancy_rate:${value}`).contribution, null);
  for (const priority_score of [null, undefined, "", false]) {
    assert.equal(scoreExplanation({ priority_score, event_count: 1, risk_drivers: "a:b:0" }).available, false);
  }
  assert.equal(scoreExplanation({ priority_score: 10, event_count: 1, risk_drivers: "a:b:11" }).available, false);
  assert.equal(scoreExplanation({ priority_score: 0, event_count: 1, risk_drivers: "a:b:0" }).available, true);
});

test("rounding and the model's 100-point cap are explicit", () => {
  const rounded = scoreExplanation({ priority_score: 23.077, event_count: 1,
    risk_drivers: "structural:taas:2.692|traffic:speed_to_limit_ratio:12.692|weather_road:kma_wind_speed:7.692" });
  assert.equal(rounded.available, true);
  assert.equal(rounded.remainder, null);
  const capped = scoreExplanation({ priority_score: 100, event_count: 1, risk_drivers: "a:b:95|gateway:airport_inflow_pressure:10" });
  assert.equal(capped.capAdjustment, 5);
});

test("changing the horizon changes the summary and missing evidence is explicit", () => {
  const current = { priority_score: 20, event_count: 1, risk_drivers: "traffic:speed_to_limit_ratio:20" };
  const future = { ...current, priority_score: 30, risk_drivers: "weather_road:kma_precipitation_type:30" };
  assert.match(prioritySummary(current), /통행속도 저하 20.0점/);
  assert.match(prioritySummary(future), /비·눈 영향 30.0점/);
  assert.match(prioritySummary({ ...current, risk_drivers: "" }), /세부 근거를 확인/);
});
