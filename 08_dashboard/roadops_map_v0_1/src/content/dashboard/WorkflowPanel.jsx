import React, { useEffect, useMemo, useRef, useState } from "react";

import { Button, DataComponent, Switch } from "../../data-app-public.jsx";
import {
  appendAuditEntry,
  applyPlanAssignments,
  countWorkflowChanges,
  createApprovalRecord,
  createWorkflowState,
  validateWorkflow,
  workflowFingerprint,
} from "./workflow-policy.js";

const TAB_LABELS = {
  resources: "1 자원",
  tasks: "2 업무",
  approval: "3 승인",
  audit: "감사 로그",
};

const TEAM_SHORT_LABELS = {
  "team-east": "동부팀",
  "team-north": "북부팀",
  "team-west": "서부팀",
};

function planLabel(planId) {
  return planId === "balanced_operations" ? "균형 운영" : "안전 우선";
}

function localDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function loadStoredSession(key) {
  if (!key || typeof localStorage === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(key) || "{}");
  } catch {
    return {};
  }
}

function ResourceStep({ state, onChange }) {
  return <div className="workflow-resource-list">
    {state.resources.map((resource) => <div className="workflow-resource-row" key={resource.teamId}>
      <div className="workflow-resource-title">
        <strong>{resource.teamName}</strong>
        <span>{resource.managingAgencyName} · {resource.vehicleId} · 정원 {resource.vehicleCapacity}명</span>
      </div>
      <Switch label="가용" checked={resource.available} size="compact"
        onChange={(checked) => onChange(resource.teamId, "available", checked)} />
      <label>인원<input type="number" min="1" max={resource.vehicleCapacity}
        value={resource.personnelCount}
        onChange={(event) => onChange(resource.teamId, "personnelCount", Number(event.target.value))} /></label>
      <label>근무분<input type="number" min="1" step="5" value={resource.shiftMinutes}
        onChange={(event) => onChange(resource.teamId, "shiftMinutes", Number(event.target.value))} /></label>
    </div>)}
    <p className="workflow-inline-note">자원 조건을 바꾸면 기존 이동경로는 자동 승인되지 않고 재계획 필요 상태로 전환됩니다.</p>
  </div>;
}

function TaskStep({ state, onChange }) {
  const sorted = [...state.tasks].sort((left, right) => right.priorityScore - left.priorityScore);
  return <div className="workflow-task-list">
    {sorted.map((task) => <div className="workflow-task-row" key={task.taskId} data-excluded={task.excluded || undefined}>
      <div className="workflow-task-title">
        <strong>{task.roadName}</strong>
        <span>{task.administrativeArea} · {task.priorityScore.toFixed(1)}점</span>
      </div>
      <label className="workflow-team-select">담당팀
        <select value={task.assignedTeamId || ""} disabled={task.excluded}
          onChange={(event) => onChange(task.taskId, "assignedTeamId", event.target.value || null)}>
          <option value="">미배정</option>
          {state.resources.map((resource) => <option key={resource.teamId} value={resource.teamId}>
            {TEAM_SHORT_LABELS[resource.teamId] || resource.teamName}
          </option>)}
        </select>
      </label>
      <Switch label="고정" checked={task.fixed} disabled={task.excluded} size="compact"
        onChange={(checked) => onChange(task.taskId, "fixed", checked)} />
      <Switch label={task.mandatory ? "필수" : "제외"} checked={task.excluded}
        disabled={task.mandatory} size="compact"
        onChange={(checked) => onChange(task.taskId, "excluded", checked)} />
    </div>)}
    <p className="workflow-inline-note">개별 담당팀 변경·업무 제외는 지도에서 해당 기존 경로를 숨기고, 새 경로가 계산될 때까지 승인을 차단합니다.</p>
  </div>;
}

function ApprovalStep({
  state,
  validation,
  validationFresh,
  approvalCurrent,
  approvalRecord,
  onAcknowledgement,
  onFieldChange,
  onValidate,
  onApprove,
}) {
  const stateLabel = approvalCurrent
    ? "승인 완료"
    : validationFresh && validation.technicalValid
      ? "검증 통과"
      : validation.errors.length
        ? "재계획 필요"
        : "검증 대기";
  const activeTasks = state.tasks.filter((task) => !task.excluded);
  const approverRoles = [...new Set(activeTasks.map((task) => task.dispatchApproverRole).filter(Boolean))];
  const pendingHandoffs = activeTasks.flatMap((task) => task.handoffStatuses || [])
    .filter((handoff) => handoff.status === "pending");
  return <div className="workflow-approval-step">
    <div className="workflow-validation-head" data-status={approvalCurrent ? "approved" : validation.technicalValid ? "valid" : "blocked"}>
      <div><span>현재 상태</span><strong>{stateLabel}</strong></div>
      <span>{validation.errors.length} 오류 · {validation.warnings.length} 주의</span>
    </div>

    {validation.errors.length > 0 && <ul className="workflow-issue-list errors">
      {validation.errors.slice(0, 5).map((item) => <li key={`${item.code}-${item.target}`}>{item.message}</li>)}
    </ul>}
    <ul className="workflow-issue-list warnings">
      {validation.warnings.map((item) => <li key={item.code}>{item.message}</li>)}
    </ul>

    <div className="workflow-authority-summary">
      <div><span>승인 직무</span><strong>{approverRoles.join(" / ") || "운영기관 확인 필요"}</strong></div>
      <div><span>경찰·소방 인계</span><strong>{pendingHandoffs.length ? `${pendingHandoffs.length}건 협조 요청 대기` : "현재 인계 요청 없음"}</strong></div>
    </div>

    <fieldset className="workflow-acknowledgements">
      <legend>현장 확인</legend>
      <label><input type="checkbox" checked={state.acknowledgements.dataQuality}
        onChange={(event) => onAcknowledgement("dataQuality", event.target.checked)} />데이터 신선도와 품질 플래그를 확인했습니다.</label>
      <label><input type="checkbox" checked={state.acknowledgements.travelEstimate}
        onChange={(event) => onAcknowledgement("travelEstimate", event.target.checked)} />이동시간이 실시간 ETA가 아님을 확인했습니다.</label>
      <label><input type="checkbox" checked={state.acknowledgements.fieldCheck}
        onChange={(event) => onAcknowledgement("fieldCheck", event.target.checked)} />현장 지시 전 통제·기상 상황을 다시 확인합니다.</label>
    </fieldset>

    <div className="workflow-approval-fields">
      <label>승인자 실명(운영기관 확인)<input type="text" value={state.approverName} placeholder="현재 당직·승인자 실명"
        onChange={(event) => onFieldChange("approverName", event.target.value)} /></label>
      <label>승인 사유<textarea rows={2} value={state.approvalReason} placeholder="현장 확인 내용과 승인 사유"
        onChange={(event) => onFieldChange("approvalReason", event.target.value)} /></label>
    </div>

    <div className="workflow-approval-actions">
      <Button variant="secondary" onClick={onValidate}>변경안 검증</Button>
      <Button variant="primary" disabled={!validationFresh || !validation.approvalReady || approvalCurrent}
        onClick={onApprove}>{approvalCurrent ? "승인 완료" : "계획 승인"}</Button>
    </div>
    {!validationFresh && <p className="workflow-action-hint">현재 입력값을 승인하려면 변경안 검증을 먼저 실행하세요.</p>}
    {approvalRecord && <div className="workflow-approval-record" data-current={approvalCurrent || undefined}>
      <span>{approvalCurrent ? "현재 계획 승인 기록" : "이전 계획 승인 기록"}</span>
      <strong>{approvalRecord.approverName} · {localDateTime(approvalRecord.approvedAt)}</strong>
      <code>{approvalRecord.workflowFingerprint}</code>
    </div>}
  </div>;
}

function AuditStep({ rows }) {
  if (!rows.length) return <p className="workflow-empty">아직 기록된 작업이 없습니다.</p>;
  return <ol className="workflow-audit-list">
    {[...rows].reverse().slice(0, 12).map((row) => <li key={row.eventId}>
      <span>{row.sequence}</span>
      <div><strong>{row.action}</strong><p>{row.details}</p><small>{localDateTime(row.at)} · {row.actor}</small></div>
    </li>)}
  </ol>;
}

export function WorkflowPanel({
  teams,
  tasks,
  governanceRows,
  routes,
  planMetrics,
  metadata,
  selectedPlan,
  scenarioId,
  onStateChange,
}) {
  const [activeTab, setActiveTab] = useState("resources");
  const [state, setState] = useState(/** @type {any} */ (null));
  const [lastValidatedFingerprint, setLastValidatedFingerprint] = useState(/** @type {any} */ (null));
  const [auditLog, setAuditLog] = useState(/** @type {any[]} */ ([]));
  const [approvalRecord, setApprovalRecord] = useState(/** @type {any} */ (null));
  const [storageReady, setStorageReady] = useState(false);
  const loadedStorageKey = useRef(/** @type {string | null} */ (null));
  const storageKey = metadata.generated_at
    ? `roadops:web1:${metadata.snapshot_version}:${metadata.generated_at}`
    : null;

  const record = (action, details) => {
    setAuditLog((current) => appendAuditEntry(current, { action, details }));
  };

  useEffect(() => {
    if (!state && teams.length && tasks.length) {
      setState(createWorkflowState({ teams, tasks, routes, planId: selectedPlan }));
    }
  }, [state, teams, tasks, routes, selectedPlan]);

  useEffect(() => {
    if (!storageKey || loadedStorageKey.current === storageKey) return;
    loadedStorageKey.current = storageKey;
    const stored = loadStoredSession(storageKey);
    setAuditLog(Array.isArray(stored.auditLog) ? stored.auditLog : []);
    setApprovalRecord(stored.approvalRecord || null);
    setLastValidatedFingerprint(stored.lastValidatedFingerprint || null);
    setStorageReady(true);
  }, [storageKey]);

  useEffect(() => {
    if (!storageReady || !storageKey || typeof localStorage === "undefined") return;
    localStorage.setItem(storageKey, JSON.stringify({ auditLog, approvalRecord, lastValidatedFingerprint }));
  }, [storageReady, storageKey, auditLog, approvalRecord, lastValidatedFingerprint]);

  useEffect(() => {
    if (!state || state.planId === selectedPlan) return;
    setState((current) => applyPlanAssignments(current, routes, selectedPlan));
    setLastValidatedFingerprint(null);
    record("plan_selected", `${planLabel(selectedPlan)} 대안으로 전환`);
  }, [selectedPlan, routes, state]);

  useEffect(() => {
    onStateChange?.(state);
  }, [state, onStateChange]);

  const validation = useMemo(() => state ? validateWorkflow({
    state,
    routes,
    planMetrics,
    metadata,
    scenarioId,
  }) : { errors: [], warnings: [], technicalValid: false, approvalReady: false },
  [state, routes, planMetrics, metadata, scenarioId]);
  const fingerprint = state ? workflowFingerprint(state, scenarioId) : null;
  const validationFresh = Boolean(fingerprint && fingerprint === lastValidatedFingerprint);
  const approvalCurrent = Boolean(fingerprint && approvalRecord?.workflowFingerprint === fingerprint);
  const changes = state ? countWorkflowChanges(state) : { resources: 0, tasks: 0 };

  const updateResource = (teamId, field, value) => {
    setState((current) => ({
      ...current,
      resources: current.resources.map((resource) => resource.teamId === teamId ? { ...resource, [field]: value } : resource),
    }));
    setLastValidatedFingerprint(null);
    record("resource_changed", `${teamId} ${field}=${value}`);
  };

  const updateTask = (taskId, field, value) => {
    setState((current) => ({
      ...current,
      tasks: current.tasks.map((task) => task.taskId === taskId ? { ...task, [field]: value } : task),
    }));
    setLastValidatedFingerprint(null);
    record("task_changed", `${taskId} ${field}=${value}`);
  };

  const updateAcknowledgement = (key, value) => {
    setState((current) => ({
      ...current,
      acknowledgements: { ...current.acknowledgements, [key]: value },
    }));
    setLastValidatedFingerprint(null);
    record("safety_acknowledged", `${key}=${value}`);
  };

  const updateField = (field, value) => {
    setState((current) => ({ ...current, [field]: value }));
    setLastValidatedFingerprint(null);
  };

  const validate = () => {
    setLastValidatedFingerprint(fingerprint);
    record(
      validation.technicalValid ? "plan_validated" : "plan_validation_failed",
      validation.technicalValid ? `${planLabel(state.planId)} 제약검사 통과` : `${validation.errors.length}개 오류 발견`,
    );
  };

  const approve = () => {
    if (!validationFresh || !validation.approvalReady) return;
    const recordAt = new Date().toISOString();
    const approved = createApprovalRecord(state, scenarioId, recordAt);
    setApprovalRecord(approved);
    record("plan_approved", `${approved.approverName}가 ${planLabel(state.planId)} 계획 승인`);
  };

  if (!state) return <div className="workflow-loading">운영 입력을 준비하고 있습니다.</div>;

  const sourceRowsByQuery = {
    teams,
    field_tasks: tasks,
    governance_authorities: governanceRows,
    plan_routes: routes,
    plan_metrics: planMetrics,
    map_metadata: [metadata],
  };
  return <DataComponent variant="plain" id="operations-workflow" queryId="teams"
    queryIds={Object.keys(sourceRowsByQuery)} kind="custom" title="운영 계획 승인"
    description="검증된 대안을 기준으로 자원과 업무 조건을 확인하고, 안전 확인 후 담당자가 승인합니다."
    sourceRows={teams} displayRows={teams} sourceRowsByQuery={sourceRowsByQuery}
    className="workflow-panel-card">
    <div className="workflow-summary-bar">
      <span data-state={approvalCurrent ? "approved" : validation.errors.length ? "blocked" : "draft"}>
        {approvalCurrent ? "승인 완료" : validation.errors.length ? "재계획 필요" : "승인 전"}
      </span>
      <p>{planLabel(state.planId)} · 자원 변경 {changes.resources} · 업무 변경 {changes.tasks}</p>
      <code>{fingerprint}</code>
    </div>
    <div className="workflow-tabs" role="tablist" aria-label="운영 계획 단계">
      {Object.entries(TAB_LABELS).map(([id, label]) => <button type="button" role="tab"
        aria-selected={activeTab === id} key={id} onClick={() => setActiveTab(id)}>{label}</button>)}
    </div>
    <div className="workflow-tab-panel" role="tabpanel">
      {activeTab === "resources" && <ResourceStep state={state} onChange={updateResource} />}
      {activeTab === "tasks" && <TaskStep state={state} onChange={updateTask} />}
      {activeTab === "approval" && <ApprovalStep state={state} validation={validation}
        validationFresh={validationFresh} approvalCurrent={approvalCurrent} approvalRecord={approvalRecord}
        onAcknowledgement={updateAcknowledgement} onFieldChange={updateField}
        onValidate={validate} onApprove={approve} />}
      {activeTab === "audit" && <AuditStep rows={auditLog} />}
    </div>
  </DataComponent>;
}
