import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DEFAULT_POLICY, policyError, calculatePriority, applyPriorityPolicy, normalizeWeights, parsePolicy } from "../src/content/dashboard/priority-policy.js";
import { prioritySummary, scoreExplanation } from "../src/content/dashboard/score-explanation.js";
import { createWorkflowState, workflowFingerprint, createApprovalRecord, rebaseWorkflowState } from "../src/content/dashboard/workflow-policy.js";
import { optimizationInputFingerprint } from "../src/content/dashboard/web-optimizer.js";
const policy = (weights) => ({ ...DEFAULT_POLICY, weights: Object.fromEntries(Object.keys(DEFAULT_POLICY.weights).map((key) => [key, weights[key] ?? 0])) });
const inputs = (values) => ({ factors: Object.entries(values).map(([key, value]) => ({ key, label: key, value, coverage: value == null ? 0 : 1, status: "available", description: "test" })) });

test("browser and batch defaults use the same operator policy", () => {
  assert.deepEqual(DEFAULT_POLICY, JSON.parse(readFileSync(new URL("../../../config/scoring/operator_priority_v0_2.json", import.meta.url))));
});
test("weights, missing data, zero and complete-evidence selection", () => {
  const config = policy({ event: 60, traffic: 40 });
  assert.equal(calculatePriority(inputs({ event: 50, traffic: 100 }), config).score, 70);
  assert.equal(calculatePriority(inputs({ event: 50, traffic: null }), config).score, 50);
  assert.equal(calculatePriority(inputs({ event: 50, traffic: 0 }), config).score, 30);
  assert.equal(calculatePriority(inputs({ event: null, traffic: 100 }), config).score, null);
  assert.equal(calculatePriority(inputs({ event: 50, traffic: null }), { ...config, method: "complete" }).score, null);
  assert.equal(calculatePriority({ ...inputs({ event: 100 }), blocked: true }, policy({ event: 100 })).score, null);
  assert.ok(policyError(policy({ event: -1, traffic: 101 })));
  assert.ok(policyError(policy({ event: NaN })));
  assert.ok(policyError(policy({ city_safety: 100 })));
  assert.equal(parsePolicy("broken"), null);
  assert.equal(policyError(normalizeWeights(policy({ event: 27, traffic: 7 }))), null);
});
test("score representative changes with weights and AI receives the same score", () => {
  const rows = [{ link_id: "a", event_count: 2, priority_candidates: [
    { ...inputs({ event: 90, traffic: 10 }), event_id: "first" },
    { ...inputs({ event: 20, traffic: 80 }), event_id: "second" },
  ] }];
  const first = applyPriorityPolicy(rows, policy({ event: 100 }))[0];
  const second = applyPriorityPolicy(rows, policy({ traffic: 100 }))[0];
  assert.equal(first.score_basis_event_id, "first");
  assert.equal(second.score_basis_event_id, "second");
  assert.equal(second.priority_score, 80);
  assert.equal(scoreExplanation(second).drivers[0].contribution, 80);
  assert.match(prioritySummary(second), /80.0점/);
  const state = createWorkflowState({ tasks: [{ ...second, task_id: "task" }] });
  assert.equal(state.tasks[0].priorityScore, second.priority_score);
  assert.equal(rows[0].priority_score, undefined);
});
test("accident overlap is conditional on including structural risk", () => {
  const raw = inputs({ structural: 60, accident_hotspot: 80, event: 10 });
  assert.equal(calculatePriority(raw, policy({ structural: 50, accident_hotspot: 50 })).score, 40);
  assert.equal(calculatePriority(raw, policy({ event: 50, accident_hotspot: 50 })).score, 45);
});

test("a changed policy invalidates approval even when numerical scores tie", () => {
  const state = createWorkflowState({ tasks: [], scoringPolicy: policy({ event: 100 }) });
  const changed = { ...state, scoringPolicy: policy({ traffic: 100 }) };
  assert.notEqual(workflowFingerprint(state), workflowFingerprint(changed));
  assert.deepEqual(createApprovalRecord({ ...state, approverName: "담당자", approvalReason: "검토" }).scoringPolicy, state.scoringPolicy);
});

test("rescoring preserves operator constraints but resets acknowledgement", () => {
  const previous = createWorkflowState({ teams: [{team_id: "team", available_minutes: 120}], tasks: [{task_id: "task", priority_score: 10}] });
  previous.resources[0].shiftMinutes = 90;
  previous.tasks[0].manualPriorityLevel = "first";
  previous.tasks[0].priorityReason = "현장 확인";
  previous.acknowledgements.dataQuality = true;
  const fresh = createWorkflowState({ teams: [{team_id: "team", available_minutes: 120}], tasks: [{task_id: "task", priority_score: 80}] });
  const result = rebaseWorkflowState(fresh, previous);
  assert.equal(result.resources[0].shiftMinutes, 90);
  assert.equal(result.tasks[0].priorityScore, 80);
  assert.equal(result.tasks[0].priorityReason, "현장 확인");
  assert.equal(result.acknowledgements.dataQuality, false);
  assert.notEqual(optimizationInputFingerprint(previous), optimizationInputFingerprint(result));
});
