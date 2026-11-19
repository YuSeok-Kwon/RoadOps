const MAX_EXACT_TASKS = 10;
const HIGH_PRIORITY_SCORE = 50;

function numeric(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function subset(required, available) {
  const values = new Set(available || []);
  return (required || []).every((value) => values.has(value));
}

function taskCapable(team, task) {
  const equipment = [...(team.equipment || []), ...(team.vehicleEquipment || [])];
  if (!subset(task.requiredSkills, team.skills) || !subset(task.requiredEquipment, equipment)) return false;
  if (task.roadTeamDispatchEligible === false) return false;
  const supportedAgencies = new Set([team.managingAgencyId, ...(team.supportAgencyIds || [])].filter(Boolean));
  if (task.managingAgencyId && !supportedAgencies.has(task.managingAgencyId)) return false;
  const authorized = new Set(team.authorizedRoadJurisdictions || []);
  return !task.roadJurisdiction || authorized.has("*") || authorized.has(task.roadJurisdiction);
}

function objectivePriority(task) {
  const score = numeric(task.priorityScore);
  if (task.manualPriorityLevel === "first") return 200 + score;
  if (task.manualPriorityLevel === "caution") return 100 + score;
  if (task.manualPriorityLevel === "normal") return score * 0.1;
  return score;
}

function populationVariance(values) {
  if (!values.length) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  return values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / values.length;
}

function compareValues(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] < right[index]) return -1;
    if (left[index] > right[index]) return 1;
  }
  return 0;
}

function optionKey(option) {
  return `${option.teamId}:${option.taskIndices.join(",")}`;
}

function routeIndex(routeOptions) {
  return new Map(routeOptions.map((route) => [
    `${String(route.origin_id)}|${String(route.destination_task_id)}`,
    route,
  ]));
}

function sequenceOption(team, sequence, tasks, routes) {
  let originId = team.teamId;
  let travelMinutes = 0;
  let serviceMinutes = 0;
  let elapsedMinutes = 0;
  const legs = [];
  for (const taskIndex of sequence) {
    const task = tasks[taskIndex];
    const route = routes.get(`${originId}|${task.taskId}`);
    if (!route || route.travel_time_minutes == null || route.status !== "ok") return null;
    const travel = numeric(route.travel_time_minutes);
    const service = numeric(task.serviceMinutes, 15);
    travelMinutes += travel;
    serviceMinutes += service;
    elapsedMinutes += travel + service;
    if (elapsedMinutes > numeric(team.shiftMinutes) + 1e-9) return null;
    legs.push({ route, taskIndex, travel, service, cumulativeMinutes: elapsedMinutes });
    originId = task.taskId;
  }
  return {
    teamId: team.teamId,
    taskIndices: [...sequence],
    taskMask: sequence.reduce((mask, index) => mask | (1 << index), 0),
    travelMinutes,
    serviceMinutes,
    elapsedMinutes,
    legs,
  };
}

function teamOptions(team, tasks, routes, fixedForTeam, forbidden, maxTasks) {
  if (!team.available) return fixedForTeam.size ? [] : [sequenceOption(team, [], tasks, routes)];
  const eligible = tasks.map((task, index) => ({ task, index }))
    .filter(({ task, index }) => !forbidden.has(index) && taskCapable(team, task))
    .map(({ index }) => index);
  const byMask = new Map();
  const sequence = [];
  const used = new Set();

  function visit(targetSize) {
    if (sequence.length === targetSize) {
      if (![...fixedForTeam].every((index) => used.has(index))) return;
      const option = sequenceOption(team, sequence, tasks, routes);
      if (!option) return;
      const known = byMask.get(option.taskMask);
      const currentKey = [option.travelMinutes, option.elapsedMinutes, option.taskIndices.join(",")];
      const knownKey = known ? [known.travelMinutes, known.elapsedMinutes, known.taskIndices.join(",")] : null;
      if (!known || compareValues(currentKey, knownKey) < 0) byMask.set(option.taskMask, option);
      return;
    }
    for (const taskIndex of eligible) {
      if (used.has(taskIndex)) continue;
      used.add(taskIndex);
      sequence.push(taskIndex);
      visit(targetSize);
      sequence.pop();
      used.delete(taskIndex);
    }
  }

  const minimumSize = fixedForTeam.size;
  const maximumSize = Math.min(maxTasks, eligible.length);
  for (let size = minimumSize; size <= maximumSize; size += 1) visit(size);
  return [...byMask.values()].sort((left, right) => left.taskMask - right.taskMask
    || left.travelMinutes - right.travelMinutes
    || left.taskIndices.join(",").localeCompare(right.taskIndices.join(",")));
}

function candidate(options, tasks) {
  const taskMask = options.reduce((mask, option) => mask | option.taskMask, 0);
  const assignedIndices = tasks.map((_, index) => index).filter((index) => taskMask & (1 << index));
  const elapsed = options.map((option) => option.elapsedMinutes);
  const workloads = options.map((option) => option.taskIndices.length);
  return {
    options,
    taskMask,
    assignedIndices,
    assignedCount: assignedIndices.length,
    prioritySum: assignedIndices.reduce((sum, index) => sum + numeric(tasks[index].priorityScore), 0),
    objectivePrioritySum: assignedIndices.reduce((sum, index) => sum + objectivePriority(tasks[index]), 0),
    totalTravelMinutes: options.reduce((sum, option) => sum + option.travelMinutes, 0),
    totalServiceMinutes: options.reduce((sum, option) => sum + option.serviceMinutes, 0),
    maximumTeamElapsedMinutes: Math.max(0, ...elapsed),
    elapsedVariance: populationVariance(elapsed),
    workloadVariance: populationVariance(workloads),
    fingerprint: options.map(optionKey).join("|"),
  };
}

function safetyKey(value) {
  return [
    -value.objectivePrioritySum,
    -value.assignedCount,
    value.totalTravelMinutes,
    value.maximumTeamElapsedMinutes,
    value.elapsedVariance,
    value.fingerprint,
  ];
}

function balancedKey(value) {
  return [
    value.maximumTeamElapsedMinutes,
    value.elapsedVariance,
    value.workloadVariance,
    value.totalTravelMinutes,
    -value.objectivePrioritySum,
    -value.assignedCount,
    value.fingerprint,
  ];
}

function geometryIndex(routeLinks) {
  return new Map(routeLinks.map((row) => {
    let geometry = [];
    try { geometry = JSON.parse(row.geometry_json || "[]"); } catch { geometry = []; }
    return [String(row.link_id), Array.isArray(geometry) ? geometry : []];
  }));
}

function routeGeometry(route, geometries) {
  return (route.route_link_ids || []).flatMap((linkId) => geometries.get(String(linkId)) || []);
}

function serializeAlternative(candidateValue, alternativeId, objective, tasks, teams, geometries) {
  const assignments = [];
  const planRoutes = [];
  const workloadTaskCounts = {};
  candidateValue.options.forEach((option) => {
    workloadTaskCounts[option.teamId] = option.taskIndices.length;
    option.legs.forEach((leg, index) => {
      const task = tasks[leg.taskIndex];
      const row = {
        alternative_id: alternativeId,
        objective,
        team_id: option.teamId,
        sequence: index + 1,
        task_id: task.taskId,
        link_id: task.linkId,
        road_name: task.roadName,
        priority_score: numeric(task.priorityScore),
        travel_minutes: Number(leg.travel.toFixed(3)),
        service_minutes: Number(leg.service.toFixed(3)),
        cumulative_minutes: Number(leg.cumulativeMinutes.toFixed(3)),
        route_id: leg.route.route_id,
        origin_id: leg.route.origin_id,
        destination_task_id: leg.route.destination_task_id,
        route_link_ids: leg.route.route_link_ids || [],
        route_semantics: leg.route.route_semantics,
        route_link_count: (leg.route.route_link_ids || []).length,
        geometry_json: JSON.stringify(routeGeometry(leg.route, geometries)),
      };
      assignments.push(row);
      planRoutes.push(row);
    });
  });
  const totalPriority = tasks.reduce((sum, task) => sum + numeric(task.priorityScore), 0);
  const unassigned = tasks.filter((_, index) => !(candidateValue.taskMask & (1 << index)));
  const workloads = Object.values(workloadTaskCounts);
  const metrics = {
    alternative_id: alternativeId,
    objective,
    candidate_task_count: tasks.length,
    assigned_task_count: candidateValue.assignedCount,
    unassigned_task_count: unassigned.length,
    assigned_priority_sum: Number(candidateValue.prioritySum.toFixed(3)),
    candidate_priority_sum: Number(totalPriority.toFixed(3)),
    risk_weighted_coverage_ratio: totalPriority ? Number((candidateValue.prioritySum / totalPriority).toFixed(6)) : null,
    high_priority_unassigned_count: unassigned.filter((task) => numeric(task.priorityScore) >= HIGH_PRIORITY_SCORE).length,
    network_total_travel_minutes: Number(candidateValue.totalTravelMinutes.toFixed(3)),
    total_service_minutes: Number(candidateValue.totalServiceMinutes.toFixed(3)),
    maximum_team_elapsed_minutes: Number(candidateValue.maximumTeamElapsedMinutes.toFixed(3)),
    workload_task_counts: workloadTaskCounts,
    workload_count_range: workloads.length ? Math.max(...workloads) - Math.min(...workloads) : 0,
    workload_count_variance: Number(candidateValue.workloadVariance.toFixed(6)),
    elapsed_minutes_variance: Number(candidateValue.elapsedVariance.toFixed(6)),
    constraint_violation_count: 0,
    manual_priority_override_count: tasks.filter((task) => task.manualPriorityLevel).length,
  };
  return { alternativeId, assignments, planRoutes, metrics };
}

function fail(failureReason, message, details = {}) {
  return { status: "fail", failureReason, message, ...details, alternatives: [], planRoutes: [], planMetrics: [] };
}

export function optimizeAllocation({
  state,
  routeOptions = [],
  routeLinks = [],
  balancedMinSafetyRatio = 0.95,
}) {
  const tasks = state.tasks
    .filter((task) => !task.excluded && task.roadTeamDispatchEligible !== false)
    .sort((left, right) => left.taskId.localeCompare(right.taskId));
  if (tasks.length > MAX_EXACT_TASKS) {
    return fail("task_limit_exceeded", `정확 최적화는 최대 ${MAX_EXACT_TASKS}개 업무까지 지원합니다.`);
  }
  if (!routeOptions.length) return fail("route_matrix_missing", "검증된 이동경로 행렬을 찾을 수 없습니다.");
  const teams = state.resources.map((team) => ({ ...team }));
  const taskIndexById = new Map(tasks.map((task, index) => [task.taskId, index]));
  const mandatoryMask = tasks.reduce((mask, task, index) => task.mandatory ? mask | (1 << index) : mask, 0);
  const fixedByTask = new Map(tasks.flatMap((task, index) => task.fixed && task.assignedTeamId
    ? [[index, task.assignedTeamId]] : []));
  const routes = routeIndex(routeOptions);
  const optionsByTeam = new Map();
  for (const team of teams) {
    const fixedForTeam = new Set([...fixedByTask].filter(([, teamId]) => teamId === team.teamId).map(([index]) => index));
    const fixedForOther = new Set([...fixedByTask].filter(([, teamId]) => teamId !== team.teamId).map(([index]) => index));
    const options = teamOptions(team, tasks, routes, fixedForTeam, fixedForOther, numeric(team.maxTasks, 3));
    if (!options.length) return fail("team_has_no_route", `${team.teamName}의 고정 업무를 근무시간과 도로 경로 안에서 수행할 수 없습니다.`, { teamId: team.teamId });
    optionsByTeam.set(team.teamId, options);
  }

  const candidates = [];
  function combine(teamIndex, usedMask, selected) {
    if (teamIndex === teams.length) {
      if ((usedMask & mandatoryMask) === mandatoryMask) candidates.push(candidate([...selected], tasks));
      return;
    }
    for (const option of optionsByTeam.get(teams[teamIndex].teamId)) {
      if (option.taskMask & usedMask) continue;
      selected.push(option);
      combine(teamIndex + 1, usedMask | option.taskMask, selected);
      selected.pop();
    }
  }
  combine(0, 0, []);
  if (!candidates.length) return fail("no_feasible_plan", "필수 업무·고정팀·근무시간을 모두 만족하는 계획이 없습니다.");

  candidates.sort((left, right) => compareValues(safetyKey(left), safetyKey(right)));
  const safety = candidates[0];
  const minimumBalancedPriority = safety.objectivePrioritySum * balancedMinSafetyRatio;
  const balancedCandidates = candidates.filter((value) => value.objectivePrioritySum + 1e-9 >= minimumBalancedPriority);
  balancedCandidates.sort((left, right) => compareValues(balancedKey(left), balancedKey(right)));
  const balanced = balancedCandidates.find((value) => value.fingerprint !== safety.fingerprint) || balancedCandidates[0] || safety;
  const geometries = geometryIndex(routeLinks);
  const alternatives = [
    serializeAlternative(safety, "safety_first", "maximize_risk_coverage_then_minimize_network_travel_time", tasks, teams, geometries),
    serializeAlternative(balanced, "balanced_operations", "retain_safety_priority_then_balance_team_elapsed_time", tasks, teams, geometries),
  ];
  return {
    status: "pass",
    solver: "browser_exact_small_instance_v0.1",
    candidateCount: candidates.length,
    taskIndexById,
    alternatives,
    planRoutes: alternatives.flatMap((item) => item.planRoutes),
    planMetrics: alternatives.map((item) => item.metrics),
  };
}

export function optimizationInputFingerprint(state) {
  return JSON.stringify({
    scoringPolicy: state.scoringPolicy ?? null,
    resources: state.resources.map((resource) => ({
      teamId: resource.teamId,
      available: resource.available,
      personnelCount: resource.personnelCount,
      shiftMinutes: resource.shiftMinutes,
    })),
    tasks: state.tasks.map((task) => ({
      taskId: task.taskId,
      priorityScore: task.priorityScore,
      assignedTeamId: task.fixed ? task.assignedTeamId : null,
      excluded: task.excluded,
      fixed: task.fixed,
      manualPriorityLevel: task.manualPriorityLevel,
    })),
  });
}
