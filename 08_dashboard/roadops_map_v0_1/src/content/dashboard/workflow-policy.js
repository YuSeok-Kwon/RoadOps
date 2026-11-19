const ACKNOWLEDGEMENT_KEYS = ["dataQuality", "travelEstimate", "fieldCheck"];
const PRIORITY_WEIGHTS = { first: 3, caution: 2, normal: 1 };

function numeric(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function shiftMinutes(team) {
  if (Number.isFinite(Number(team.available_minutes))) return Number(team.available_minutes);
  const start = new Date(team.shift_start_at).getTime();
  const end = new Date(team.shift_end_at).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return Math.max(0, Math.round((end - start) / 60000));
}

function assignmentMap(routes, planId) {
  return new Map(
    routes
      .filter((row) => row.alternative_id === planId)
      .map((row) => [String(row.task_id), String(row.team_id)]),
  );
}

function suggestedPriorityLevel(riskLevel) {
  if (["critical", "high"].includes(String(riskLevel))) return "first";
  if (String(riskLevel) === "moderate") return "caution";
  return "normal";
}

function priorityWeight(task) {
  return PRIORITY_WEIGHTS[task.manualPriorityLevel || task.suggestedPriorityLevel] || 1;
}

export function createWorkflowState({ teams = [], tasks = [], routes = [], planId = "safety_first", scoringPolicy = null }) {
  const assignments = assignmentMap(routes, planId);
  return {
    planId,
    scoringPolicy,
    resources: teams.map((team) => {
      const personnelCount = numeric(team.personnel_count);
      const available = String(team.vehicle_status || "available") === "available";
      const duration = shiftMinutes(team);
      return {
        teamId: String(team.team_id),
        teamName: String(team.team_name || team.team_id),
        managingAgencyName: String(team.managing_agency_name || "기관 미확인"),
        vehicleId: String(team.vehicle_id || ""),
        vehicleCapacity: numeric(team.vehicle_personnel_capacity, personnelCount || 1),
        maxTasks: numeric(team.max_tasks_per_team, 3),
        available,
        personnelCount,
        shiftMinutes: duration,
        skills: Array.isArray(team.skills) ? team.skills : [],
        equipment: Array.isArray(team.equipment) ? team.equipment : [],
        vehicleEquipment: Array.isArray(team.vehicle_equipment) ? team.vehicle_equipment : [],
        managingAgencyId: String(team.managing_agency_id || ""),
        supportAgencyIds: Array.isArray(team.support_agency_ids) ? team.support_agency_ids : [],
        authorizedRoadJurisdictions: Array.isArray(team.authorized_road_jurisdictions) ? team.authorized_road_jurisdictions : [],
        baseline: { available, personnelCount, shiftMinutes: duration },
      };
    }),
    tasks: tasks.map((task) => {
      const assignedTeamId = assignments.get(String(task.task_id)) || task.fixed_team_id || null;
      const excluded = Boolean(task.excluded);
      const fixed = Boolean(task.fixed_team_id);
      return {
        taskId: String(task.task_id),
        linkId: String(task.link_id),
        inspectionPlan: task.inspection_plan || null,
        roadName: String(task.road_name || "도로명 미상"),
        priorityScore: numeric(task.priority_score),
        suggestedPriorityLevel: suggestedPriorityLevel(task.risk_level),
        manualPriorityLevel: null,
        priorityReason: "",
        mandatory: Boolean(task.mandatory),
        serviceMinutes: numeric(task.service_minutes, 15),
        requiredSkills: Array.isArray(task.required_skills) ? task.required_skills : [],
        requiredEquipment: Array.isArray(task.required_equipment) ? task.required_equipment : [],
        managingAgencyId: String(task.managing_agency_id || ""),
        roadTeamDispatchEligible: task.road_team_dispatch_eligible !== false,
        managingAgencyName: String(task.managing_agency_name || "기관 미확인"),
        administrativeArea: [task.administrative_city, task.administrative_unit].filter(Boolean).join(" ") || "구역 미확인",
        roadJurisdiction: String(task.road_jurisdiction || "관할 미확인"),
        authorityStatus: String(task.authority_status || "operator_default"),
        dispatchApproverRole: String(task.dispatch_approver_role || "운영기관 확인 필요"),
        dispatchApproverVerificationStatus: String(task.dispatch_approver_verification_status || "operator_defined"),
        handoffStatuses: Array.isArray(task.handoff_statuses) ? task.handoff_statuses : [],
        assignedTeamId: assignedTeamId ? String(assignedTeamId) : null,
        excluded,
        fixed,
        baseline: {
          assignedTeamId: assignedTeamId ? String(assignedTeamId) : null,
          excluded,
          fixed,
          manualPriorityLevel: null,
          priorityReason: "",
        },
      };
    }),
    acknowledgements: Object.fromEntries(ACKNOWLEDGEMENT_KEYS.map((key) => [key, false])),
    approverName: "",
    approvalReason: "",
  };
}

export function rebaseWorkflowState(fresh, previous) {
  if (!previous) return fresh;
  const resources = new Map(previous.resources.map((row) => [row.teamId, row]));
  const tasks = new Map(previous.tasks.map((row) => [row.taskId, row]));
  return { ...fresh,
    resources: fresh.resources.map((row) => {
      const prior = resources.get(row.teamId);
      return prior ? { ...row, available: prior.available, personnelCount: prior.personnelCount, shiftMinutes: prior.shiftMinutes } : row;
    }),
    tasks: fresh.tasks.map((row) => {
      const prior = tasks.get(row.taskId);
      return prior ? { ...row, assignedTeamId: prior.assignedTeamId, excluded: prior.excluded,
        fixed: prior.fixed, manualPriorityLevel: prior.manualPriorityLevel, priorityReason: prior.priorityReason } : row;
    }),
  };
}

export function applyPlanAssignments(state, routes, planId) {
  const assignments = assignmentMap(routes, planId);
  return {
    ...state,
    planId,
    tasks: state.tasks.map((task) => {
      if (task.excluded) return task;
      const assignedTeamId = assignments.get(task.taskId) || null;
      return {
        ...task,
        assignedTeamId,
        baseline: {
          ...task.baseline,
          assignedTeamId,
        },
      };
    }),
  };
}

export function recalculateWorkflow(state, routes = []) {
  const resources = state.resources.map((resource) => ({
    ...resource,
    baseline: {
      available: resource.available,
      personnelCount: resource.personnelCount,
      shiftMinutes: resource.shiftMinutes,
    },
  }));
  const resourcesById = new Map(resources.map((resource) => [resource.teamId, resource]));
  const load = new Map(resources.map((resource) => [resource.teamId, 0]));
  const routeTeamsByTask = new Map();
  routes.forEach((route) => {
    const taskId = String(route.task_id);
    if (!routeTeamsByTask.has(taskId)) routeTeamsByTask.set(taskId, new Set());
    routeTeamsByTask.get(taskId).add(String(route.team_id));
  });
  const activeTasks = [...state.tasks]
    .filter((task) => !task.excluded)
    .sort((left, right) => Number(right.fixed) - Number(left.fixed)
      || Number(right.mandatory) - Number(left.mandatory)
      || priorityWeight(right) - priorityWeight(left)
      || right.priorityScore - left.priorityScore
      || left.taskId.localeCompare(right.taskId));
  const assignments = new Map();

  activeTasks.forEach((task) => {
    const routeTeams = routeTeamsByTask.get(task.taskId);
    const current = resourcesById.get(task.assignedTeamId);
    const currentLoad = load.get(task.assignedTeamId) || 0;
    const currentUsable = current?.available && currentLoad < current.maxTasks
      && (!routeTeams?.size || routeTeams.has(task.assignedTeamId));
    if (task.fixed || currentUsable) {
      assignments.set(task.taskId, task.assignedTeamId);
      if (task.assignedTeamId) load.set(task.assignedTeamId, currentLoad + 1);
      return;
    }
    const candidate = resources
      .filter((resource) => resource.available
        && (load.get(resource.teamId) || 0) < resource.maxTasks
        && (!routeTeams?.size || routeTeams.has(resource.teamId)))
      .sort((left, right) => (load.get(left.teamId) || 0) - (load.get(right.teamId) || 0)
        || left.teamId.localeCompare(right.teamId))[0];
    assignments.set(task.taskId, candidate?.teamId || null);
    if (candidate) load.set(candidate.teamId, (load.get(candidate.teamId) || 0) + 1);
  });

  return {
    ...state,
    resources,
    tasks: state.tasks.map((task) => {
      const assignedTeamId = task.excluded ? task.assignedTeamId : assignments.get(task.taskId) || null;
      return {
        ...task,
        assignedTeamId,
        baseline: {
          ...task.baseline,
          assignedTeamId,
          excluded: task.excluded,
          fixed: task.fixed,
        },
      };
    }),
  };
}

function resourceChanged(resource) {
  return resource.available !== resource.baseline.available
    || resource.personnelCount !== resource.baseline.personnelCount
    || resource.shiftMinutes !== resource.baseline.shiftMinutes;
}

function taskChanged(task) {
  return task.assignedTeamId !== task.baseline.assignedTeamId
    || task.excluded !== task.baseline.excluded
    || task.fixed !== task.baseline.fixed
    || task.manualPriorityLevel !== task.baseline.manualPriorityLevel
    || task.priorityReason !== task.baseline.priorityReason;
}

export function countWorkflowChanges(state) {
  return {
    resources: state.resources.filter(resourceChanged).length,
    tasks: state.tasks.filter(taskChanged).length,
  };
}

function issue(code, message, target = null) {
  return { code, message, target };
}

export function validateWorkflow({
  state,
  routes = [],
  planMetrics = [],
  metadata = {},
  scenarioId = "none",
  optimizationStatus = "ready",
  optimizationMessage = "",
}) {
  const errors = [];
  const warnings = [];
  const resourcesById = new Map(state.resources.map((resource) => [resource.teamId, resource]));
  const assignedCounts = new Map();

  if (optimizationStatus === "calculating") {
    errors.push(issue("OPTIMIZATION_IN_PROGRESS", "변경한 조건으로 최적 경로를 계산하고 있습니다."));
  } else if (optimizationStatus === "failed") {
    errors.push(issue("OPTIMIZATION_FAILED", optimizationMessage || "변경한 조건을 만족하는 출동계획을 만들지 못했습니다."));
  }

  state.resources.forEach((resource) => {
    if (resource.personnelCount < 1 || resource.personnelCount > resource.vehicleCapacity) {
      errors.push(issue(
        "INVALID_PERSONNEL_COUNT",
        `${resource.teamName} 인원은 1명 이상, 차량 정원 ${resource.vehicleCapacity}명 이하여야 합니다.`,
        resource.teamId,
      ));
    }
    if (resource.shiftMinutes <= 0) {
      errors.push(issue("INVALID_SHIFT", `${resource.teamName} 근무시간이 0분 이하입니다.`, resource.teamId));
    }
  });

  state.tasks.forEach((task) => {
    if (task.manualPriorityLevel && task.priorityReason.trim().length < 5) {
      errors.push(issue(
        "PRIORITY_REASON_REQUIRED",
        `${task.roadName} 우선순위를 직접 조정한 이유를 5자 이상 입력해야 합니다.`,
        task.taskId,
      ));
    }
    if (task.mandatory && task.excluded) {
      errors.push(issue("MANDATORY_TASK_EXCLUDED", `${task.roadName} 필수 업무는 제외할 수 없습니다.`, task.taskId));
      return;
    }
    if (task.excluded) {
      return;
    }
    if (!task.assignedTeamId) {
      errors.push(issue("UNASSIGNED_TASK", `${task.roadName} 업무에 담당팀이 없습니다.`, task.taskId));
      return;
    }
    const resource = resourcesById.get(task.assignedTeamId);
    if (!resource) {
      errors.push(issue("UNKNOWN_TEAM", `${task.roadName} 담당팀을 찾을 수 없습니다.`, task.taskId));
      return;
    }
    if (!resource.available) {
      errors.push(issue("UNAVAILABLE_TEAM", `${resource.teamName}이 비가용 상태인데 업무가 배정돼 있습니다.`, task.taskId));
    }
    assignedCounts.set(task.assignedTeamId, (assignedCounts.get(task.assignedTeamId) || 0) + 1);
  });

  state.resources.forEach((resource) => {
    const count = assignedCounts.get(resource.teamId) || 0;
    if (count > resource.maxTasks) {
      errors.push(issue(
        "TEAM_TASK_CAPACITY_EXCEEDED",
        `${resource.teamName} 배정 ${count}건이 최대 ${resource.maxTasks}건을 초과했습니다.`,
        resource.teamId,
      ));
    }
  });

  const metric = planMetrics.find((row) => row.alternative_id === state.planId);
  if (!metric) {
    errors.push(issue("UNKNOWN_PLAN", "선택한 검증 계획의 지표를 찾을 수 없습니다."));
  } else if (numeric(metric.constraint_violation_count) > 0) {
    errors.push(issue("PLAN_CONSTRAINT_VIOLATION", "선택한 계획에 해결되지 않은 제약 위반이 있습니다."));
  }

  if ((/** @type {any} */ (metadata)).freshness_status !== "recent_snapshot") {
    warnings.push(issue("STALE_SNAPSHOT", "저장된 스냅샷이므로 현장 지시 전 최신 데이터를 다시 확인해야 합니다."));
  }
  if ((/** @type {any} */ (metadata)).live_eta_available) {
    warnings.push(issue("LIVE_ETA_PARTIAL_COVERAGE", "ITS 실시간 속도를 반영했으며, 미관측 도로는 제한속도 기준으로 계산했습니다."));
  } else {
    warnings.push(issue("FREE_FLOW_ESTIMATE", "이동시간은 실시간 ETA가 아닌 자유흐름 추정치입니다."));
  }
  if (state.tasks.some((task) => !task.excluded && task.dispatchApproverVerificationStatus === "operator_configuration_required")) {
    warnings.push(issue("APPROVER_CONFIGURATION_REQUIRED", "최종 확인 직무는 지정됐지만 현재 당직 책임자의 실명은 운영기관 확인이 필요합니다."));
  }
  if (scenarioId !== "none") {
    warnings.push(issue("WHAT_IF_SCENARIO", "선택한 도로 통제·폭우 상황은 실제 발생 사실이 아닌 비교용 가정입니다."));
  }

  const technicalValid = errors.length === 0;
  const acknowledgementsComplete = ACKNOWLEDGEMENT_KEYS.every((key) => state.acknowledgements[key]);
  const approverComplete = state.approverName.trim().length >= 2;
  const reasonComplete = state.approvalReason.trim().length >= 5;
  return {
    errors,
    warnings,
    technicalValid,
    acknowledgementsComplete,
    approverComplete,
    reasonComplete,
    approvalReady: technicalValid && acknowledgementsComplete && approverComplete && reasonComplete,
  };
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  }
  return value;
}

function fnv1a(value) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function workflowFingerprint(state, scenarioId = "none") {
  const payload = {
    planId: state.planId,
    scenarioId,
    scoringPolicy: state.scoringPolicy ?? null,
    resources: state.resources.map(({ baseline, ...resource }) => resource).sort((a, b) => a.teamId.localeCompare(b.teamId)),
    tasks: state.tasks.map(({ baseline, ...task }) => task).sort((a, b) => a.taskId.localeCompare(b.taskId)),
  };
  return `wf-${fnv1a(JSON.stringify(stableValue(payload)))}`;
}

export function appendAuditEntry(entries, { action, details, at = null, actor = "local-operator" }) {
  const sequence = entries.length + 1;
  return [
    ...entries,
    {
      eventId: `audit-${String(sequence).padStart(4, "0")}`,
      sequence,
      at: at || new Date().toISOString(),
      actor,
      action,
      details,
    },
  ];
}

export function createApprovalRecord(state, scenarioId, at) {
  return {
    approvalId: `approval-${workflowFingerprint(state, scenarioId).slice(3)}`,
    approvedAt: at || new Date().toISOString(),
    approverName: state.approverName.trim(),
    approverRole: state.tasks.find((task) => !task.excluded)?.dispatchApproverRole || null,
    approvalReason: state.approvalReason.trim(),
    planId: state.planId,
    scenarioId,
    scoringPolicy: state.scoringPolicy ?? null,
    workflowFingerprint: workflowFingerprint(state, scenarioId),
    inspectionPlans: state.tasks.filter(task => !task.excluded && task.inspectionPlan).map(task => task.inspectionPlan),
    status: "approved_for_demo_dispatch",
  };
}
