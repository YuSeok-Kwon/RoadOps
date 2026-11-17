import React, { useEffect, useMemo, useRef, useState } from "react";

import { Button, DataComponent, Switch } from "../../data-app-public.jsx";
import {
  appendAuditEntry,
  applyPlanAssignments,
  countWorkflowChanges,
  createApprovalRecord,
  createWorkflowState,
  recalculateWorkflow,
  validateWorkflow,
  workflowFingerprint,
} from "./workflow-policy.js";

const TAB_LABELS = {
  resources: "1 출동팀",
  tasks: "2 도로·우선순위",
  approval: "3 확인·확정",
  audit: "처리 기록",
};

const TEAM_SHORT_LABELS = {
  "team-east": "동부팀",
  "team-north": "북부팀",
  "team-west": "서부팀",
};

const RESOURCE_FIELD_LABELS = {
  available: "출동 가능 여부",
  personnelCount: "출동 인원",
  shiftMinutes: "가용 시간",
};

const TASK_FIELD_LABELS = {
  assignedTeamId: "담당팀",
  fixed: "팀 고정 여부",
  excluded: "점검 제외 여부",
};

const PRIORITY_OPTION_LABELS = {
  first: "가장 먼저",
  caution: "주의해서",
  normal: "일반 순서",
};

const ACKNOWLEDGEMENT_LABELS = {
  dataQuality: "데이터 품질 확인",
  travelEstimate: "이동시간 추정치 확인",
  fieldCheck: "현장 상황 재확인",
};

const AUDIT_ACTOR_LABELS = {
  "local-operator": "현재 사용자",
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

function ResourceStep({ state, onChange, onNext }) {
  return <div className="workflow-resource-list">
    {state.resources.map((resource) => <div className="workflow-resource-row" key={resource.teamId}>
      <div className="workflow-resource-title">
        <strong>{resource.teamName}</strong>
        <span>{resource.managingAgencyName} · {resource.vehicleId} · 정원 {resource.vehicleCapacity}명</span>
      </div>
      <Switch label="출동 가능" checked={resource.available} size="compact"
        onChange={(checked) => onChange(resource.teamId, "available", checked)} />
      <label>출동 인원<input type="number" min="1" max={resource.vehicleCapacity}
        value={resource.personnelCount}
        onChange={(event) => onChange(resource.teamId, "personnelCount", Number(event.target.value))} /></label>
      <label>가용 시간(분)<input type="number" min="1" step="5" value={resource.shiftMinutes}
        onChange={(event) => onChange(resource.teamId, "shiftMinutes", Number(event.target.value))} /></label>
    </div>)}
    <p className="workflow-inline-note">출동팀·인원·가용 시간을 바꾸면 이동 경로를 다시 계산해야 합니다.</p>
    <div className="workflow-step-actions">
      <Button variant="primary" onClick={onNext}>다음: 도로 배정</Button>
    </div>
  </div>;
}

function TaskStep({ state, onChange, onPriorityChange, onReasonChange, onReasonCommit, onNext }) {
  const priorityWeight = (task) => ({ first: 3, caution: 2, normal: 1 }[task.manualPriorityLevel || task.suggestedPriorityLevel] || 1);
  const sorted = [...state.tasks].sort((left, right) => priorityWeight(right) - priorityWeight(left)
    || right.priorityScore - left.priorityScore);
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
      <label className="workflow-priority-select">확인 순서
        <select value={task.manualPriorityLevel || ""} disabled={task.excluded}
          onChange={(event) => onPriorityChange(task.taskId, event.target.value || null)}>
          <option value="">자동 제안 유지</option>
          <option value="first">가장 먼저</option>
          <option value="caution">주의해서</option>
          <option value="normal">일반 순서</option>
        </select>
      </label>
      {task.manualPriorityLevel && <label className="workflow-priority-reason">조정 이유
        <input type="text" value={task.priorityReason} placeholder="현장 제보·민원·행사 등 5자 이상"
          onChange={(event) => onReasonChange(task.taskId, event.target.value)}
          onBlur={() => onReasonCommit(task.taskId)} />
      </label>}
      <Switch label="팀 고정" checked={task.fixed} disabled={task.excluded} size="compact"
        onChange={(checked) => onChange(task.taskId, "fixed", checked)} />
      {task.mandatory
        ? <span className="workflow-mandatory-tag">필수 점검</span>
        : <Switch label="점검 제외" checked={task.excluded} size="compact"
          onChange={(checked) => onChange(task.taskId, "excluded", checked)} />}
    </div>)}
    <p className="workflow-inline-note">확인 순서·담당팀·점검 제외를 바꾸면 팀 배분을 즉시 다시 계산합니다. 담당자 조정은 이유와 함께 처리 기록에 남습니다.</p>
    <div className="workflow-step-actions">
      <Button variant="primary" onClick={onNext}>다음: 확인·확정</Button>
    </div>
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
    ? "확정 완료"
    : validationFresh && validation.technicalValid
      ? "제약조건 통과"
      : validation.errors.length
        ? "확인 필요"
        : "확인 전";
  const activeTasks = state.tasks.filter((task) => !task.excluded);
  const approverRoles = [...new Set(activeTasks.map((task) => task.dispatchApproverRole).filter(Boolean))];
  const pendingHandoffs = activeTasks.flatMap((task) => task.handoffStatuses || [])
    .filter((handoff) => handoff.status === "pending");
  return <div className="workflow-approval-step">
    <div className="workflow-validation-head" data-status={approvalCurrent ? "approved" : validation.technicalValid ? "valid" : "blocked"}>
      <div><span>출동계획 상태</span><strong>{stateLabel}</strong></div>
      <span>{validation.errors.length} 오류 · {validation.warnings.length} 주의</span>
    </div>

    {validation.errors.length > 0 && <ul className="workflow-issue-list errors">
      {validation.errors.slice(0, 5).map((item) => <li key={`${item.code}-${item.target}`}>{item.message}</li>)}
    </ul>}
    <ul className="workflow-issue-list warnings">
      {validation.warnings.map((item) => <li key={item.code}>{item.message}</li>)}
    </ul>

    <div className="workflow-authority-summary">
      <div><span>최종 확인 직무</span><strong>{approverRoles.join(" / ") || "운영기관 확인 필요"}</strong></div>
      <div><span>경찰·소방 인계</span><strong>{pendingHandoffs.length ? `${pendingHandoffs.length}건 협조 요청 대기` : "현재 인계 요청 없음"}</strong></div>
    </div>

    <fieldset className="workflow-acknowledgements">
      <legend>출동 전 필수 확인</legend>
      <label><input type="checkbox" checked={state.acknowledgements.dataQuality}
        onChange={(event) => onAcknowledgement("dataQuality", event.target.checked)} />데이터 신선도와 품질 플래그를 확인했습니다.</label>
      <label><input type="checkbox" checked={state.acknowledgements.travelEstimate}
        onChange={(event) => onAcknowledgement("travelEstimate", event.target.checked)} />이동시간이 실시간 ETA가 아님을 확인했습니다.</label>
      <label><input type="checkbox" checked={state.acknowledgements.fieldCheck}
        onChange={(event) => onAcknowledgement("fieldCheck", event.target.checked)} />현장 지시 전 통제·기상 상황을 다시 확인합니다.</label>
    </fieldset>

    <div className="workflow-approval-fields">
      <label>최종 확인자<input type="text" value={state.approverName} placeholder="현재 당직·책임자 실명"
        onChange={(event) => onFieldChange("approverName", event.target.value)} /></label>
      <label>현장 확인 메모<textarea rows={2} value={state.approvalReason} placeholder="통제·기상·협조 요청 확인 내용"
        onChange={(event) => onFieldChange("approvalReason", event.target.value)} /></label>
    </div>

    <div className="workflow-approval-actions">
      <Button variant="secondary" onClick={onValidate}>제약조건 확인</Button>
      <Button variant="primary" disabled={!validationFresh || !validation.approvalReady || approvalCurrent}
        onClick={onApprove}>{approvalCurrent ? "확정 완료" : "출동계획 확정"}</Button>
    </div>
    {!validationFresh && <p className="workflow-action-hint">팀·업무 조건을 확인한 뒤 ‘제약조건 확인’을 먼저 누르세요.</p>}
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
      <div><strong>{row.action}</strong><p>{row.details}</p><small>{localDateTime(row.at)} · {AUDIT_ACTOR_LABELS[row.actor] || row.actor}</small></div>
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
    record("배분안 선택", `${planLabel(selectedPlan)} 배분안으로 전환했습니다.`);
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
    setState((current) => recalculateWorkflow({
      ...current,
      resources: current.resources.map((resource) => resource.teamId === teamId ? { ...resource, [field]: value } : resource),
    }, routes));
    setLastValidatedFingerprint(null);
    const teamLabel = TEAM_SHORT_LABELS[teamId] || teamId;
    const valueLabel = field === "available" ? (value ? "출동 가능" : "출동 불가")
      : field === "shiftMinutes" ? `${value}분` : `${value}명`;
    record("출동팀 조건 변경", `${teamLabel}의 ${RESOURCE_FIELD_LABELS[field] || field}을 '${valueLabel}'로 변경하고 배분을 다시 계산했습니다.`);
  };

  const updateTask = (taskId, field, value) => {
    setState((current) => recalculateWorkflow({
      ...current,
      tasks: current.tasks.map((task) => task.taskId === taskId ? { ...task, [field]: value } : task),
    }, routes));
    setLastValidatedFingerprint(null);
    const task = state.tasks.find((item) => item.taskId === taskId);
    const valueLabel = field === "assignedTeamId" ? (TEAM_SHORT_LABELS[value] || "미배정")
      : value ? "사용" : "사용 안 함";
    record("도로 조건 변경", `${task?.roadName || "선택 도로"}의 ${TASK_FIELD_LABELS[field] || field}을 '${valueLabel}'로 변경하고 배분을 다시 계산했습니다.`);
  };

  const updatePriority = (taskId, manualPriorityLevel) => {
    setState((current) => recalculateWorkflow({
      ...current,
      tasks: current.tasks.map((task) => task.taskId === taskId ? {
        ...task,
        manualPriorityLevel,
        priorityReason: manualPriorityLevel ? task.priorityReason : "",
      } : task),
    }, routes));
    setLastValidatedFingerprint(null);
    const task = state.tasks.find((item) => item.taskId === taskId);
    const priorityLabel = PRIORITY_OPTION_LABELS[manualPriorityLevel] || "자동 제안";
    record("확인 순서 조정", `${task?.roadName || "선택 도로"}의 확인 순서를 '${priorityLabel}' 단계로 바꾸고 팀 배분을 다시 계산했습니다.`);
  };

  const updatePriorityReason = (taskId, priorityReason) => {
    setState((current) => ({
      ...current,
      tasks: current.tasks.map((task) => task.taskId === taskId ? { ...task, priorityReason } : task),
    }));
    setLastValidatedFingerprint(null);
  };

  const commitPriorityReason = (taskId) => {
    const task = state.tasks.find((item) => item.taskId === taskId);
    const reason = task?.priorityReason?.trim();
    if (!reason) return;
    record("조정 이유 기록", `${task.roadName} 확인 순서 조정 이유: ${reason}`);
  };

  const updateAcknowledgement = (key, value) => {
    setState((current) => ({
      ...current,
      acknowledgements: { ...current.acknowledgements, [key]: value },
    }));
    setLastValidatedFingerprint(null);
    record("안전조건 확인", `${ACKNOWLEDGEMENT_LABELS[key] || "안전조건"}을 ${value ? "확인했습니다." : "확인 전으로 되돌렸습니다."}`);
  };

  const updateField = (field, value) => {
    setState((current) => ({ ...current, [field]: value }));
    setLastValidatedFingerprint(null);
  };

  const validate = () => {
    setLastValidatedFingerprint(fingerprint);
    record(
      validation.technicalValid ? "계획 검증 완료" : "계획 검증 실패",
      validation.technicalValid ? `${planLabel(state.planId)} 제약검사 통과` : `${validation.errors.length}개 오류 발견`,
    );
  };

  const approve = () => {
    if (!validationFresh || !validation.approvalReady) return;
    const recordAt = new Date().toISOString();
    const approved = createApprovalRecord(state, scenarioId, recordAt);
    setApprovalRecord(approved);
    record("출동계획 확정", `${approved.approverName} 책임자가 ${planLabel(state.planId)} 계획을 확정했습니다.`);
    setActiveTab("audit");
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
    queryIds={Object.keys(sourceRowsByQuery)} kind="custom" title="출동계획 확정"
    description="AI가 만든 배분안을 실제 현장 지시 전에 사람이 확인하는 단계입니다. 출동 가능팀 확인 → 도로별 담당팀 확인 → 안전조건 점검 → 책임자 확정"
    sourceRows={teams} displayRows={teams} sourceRowsByQuery={sourceRowsByQuery}
    className="workflow-panel-card">
    <div className="workflow-summary-bar">
      <span data-state={approvalCurrent ? "approved" : validation.errors.length ? "blocked" : "draft"}>
        {approvalCurrent ? "확정 완료" : validation.errors.length ? "조건 확인 필요" : "확정 전"}
      </span>
      <p>{planLabel(state.planId)} · 자원 변경 {changes.resources} · 업무 변경 {changes.tasks}</p>
    </div>
    <div className="workflow-tabs" role="tablist" aria-label="운영 계획 단계">
      {Object.entries(TAB_LABELS).map(([id, label]) => <button type="button" role="tab"
        aria-selected={activeTab === id} key={id} onClick={() => setActiveTab(id)}>{label}</button>)}
    </div>
    <div className="workflow-tab-panel" role="tabpanel">
      {activeTab === "resources" && <ResourceStep state={state} onChange={updateResource}
        onNext={() => setActiveTab("tasks")} />}
      {activeTab === "tasks" && <TaskStep state={state} onChange={updateTask}
        onPriorityChange={updatePriority} onReasonChange={updatePriorityReason}
        onReasonCommit={commitPriorityReason}
        onNext={() => setActiveTab("approval")} />}
      {activeTab === "approval" && <ApprovalStep state={state} validation={validation}
        validationFresh={validationFresh} approvalCurrent={approvalCurrent} approvalRecord={approvalRecord}
        onAcknowledgement={updateAcknowledgement} onFieldChange={updateField}
        onValidate={validate} onApprove={approve} />}
      {activeTab === "audit" && <AuditStep rows={auditLog} />}
    </div>
  </DataComponent>;
}
