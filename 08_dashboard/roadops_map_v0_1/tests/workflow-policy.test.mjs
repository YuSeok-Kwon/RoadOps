import assert from "node:assert/strict";
import test from "node:test";

import {
  appendAuditEntry,
  applyPlanAssignments,
  countWorkflowChanges,
  createApprovalRecord,
  createWorkflowState,
  validateWorkflow,
  workflowFingerprint,
} from "../src/content/dashboard/workflow-policy.js";

const teams = [{
  team_id: "team-a",
  team_name: "A팀",
  vehicle_id: "car-a",
  vehicle_status: "available",
  vehicle_personnel_capacity: 2,
  personnel_count: 2,
  max_tasks_per_team: 2,
  shift_start_at: "2026-11-16T09:00:00+09:00",
  shift_end_at: "2026-11-16T11:00:00+09:00",
}];
const tasks = [{
  task_id: "task-1",
  link_id: "link-1",
  road_name: "평화로",
  priority_score: 50,
  mandatory: true,
  excluded: false,
}];
const routes = [
  { alternative_id: "safety_first", task_id: "task-1", team_id: "team-a" },
  { alternative_id: "balanced_operations", task_id: "task-1", team_id: "team-a" },
];
const planMetrics = [{ alternative_id: "safety_first", constraint_violation_count: 0 }];

function validState() {
  const state = createWorkflowState({ teams, tasks, routes, planId: "safety_first" });
  state.acknowledgements = { dataQuality: true, travelEstimate: true, fieldCheck: true };
  state.approverName = "홍길동";
  state.approvalReason = "현장 확인 후 승인";
  return state;
}

test("validated snapshot becomes approval-ready only after acknowledgements and identity", () => {
  const initial = createWorkflowState({ teams, tasks, routes, planId: "safety_first" });
  const pending = validateWorkflow({ state: initial, routes, planMetrics, metadata: { freshness_status: "stale_snapshot" } });
  assert.equal(pending.technicalValid, true);
  assert.equal(pending.approvalReady, false);
  assert.ok(pending.warnings.some((item) => item.code === "STALE_SNAPSHOT"));

  const result = validateWorkflow({ state: validState(), routes, planMetrics, metadata: { freshness_status: "stale_snapshot" } });
  assert.equal(result.approvalReady, true);
});

test("resource edits require backend replanning", () => {
  const state = validState();
  state.resources[0].personnelCount = 1;
  const result = validateWorkflow({ state, routes, planMetrics, metadata: {} });
  assert.equal(result.technicalValid, false);
  assert.ok(result.errors.some((item) => item.code === "RESOURCE_REPLAN_REQUIRED"));
  assert.deepEqual(countWorkflowChanges(state), { resources: 1, tasks: 0 });
});

test("mandatory task exclusion and route mismatch block approval", () => {
  const excluded = validState();
  excluded.tasks[0].excluded = true;
  const excludedResult = validateWorkflow({ state: excluded, routes, planMetrics, metadata: {} });
  assert.ok(excludedResult.errors.some((item) => item.code === "MANDATORY_TASK_EXCLUDED"));

  const reassigned = validState();
  reassigned.tasks[0].assignedTeamId = "team-b";
  const reassignedResult = validateWorkflow({ state: reassigned, routes, planMetrics, metadata: {} });
  assert.ok(reassignedResult.errors.some((item) => ["UNKNOWN_TEAM", "ROUTE_REPLAN_REQUIRED"].includes(item.code)));
});

test("switching to another validated plan resets assignment baselines", () => {
  const state = validState();
  state.tasks[0].fixed = true;
  const changed = applyPlanAssignments(state, routes, "balanced_operations");
  assert.equal(changed.planId, "balanced_operations");
  assert.equal(changed.tasks[0].assignedTeamId, "team-a");
  assert.equal(changed.tasks[0].fixed, false);
});

test("workflow fingerprint is deterministic and approval captures it", () => {
  const state = validState();
  const first = workflowFingerprint(state, "none");
  const second = workflowFingerprint({ ...state, tasks: [...state.tasks].reverse() }, "none");
  assert.equal(first, second);
  const approval = createApprovalRecord(state, "none", "2026-11-16T12:00:00+09:00");
  assert.equal(approval.workflowFingerprint, first);
  assert.equal(approval.approverName, "홍길동");
});

test("audit entries are ordered and retain action details", () => {
  const first = appendAuditEntry([], { action: "validated", details: "검증 통과", at: "2026-11-16T12:00:00+09:00" });
  const second = appendAuditEntry(first, { action: "approved", details: "현장 승인", at: "2026-11-16T12:01:00+09:00" });
  assert.equal(second[1].sequence, 2);
  assert.equal(second[1].eventId, "audit-0002");
  assert.equal(second[1].action, "approved");
});
