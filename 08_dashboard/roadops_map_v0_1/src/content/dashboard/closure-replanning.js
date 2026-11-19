import { computeDetourMatrix, createRouter } from "./network-routing.js";
import { optimizeAllocation } from "./web-optimizer.js";

const rounded = (value) => Number(value.toFixed(3));
const fail = (message) => ({ status: "fail", message, routes: [], manualApprovalRequired: true });

// A comparison of the same unfinished itinerary, not a time-feasible dispatch plan.
// Both sides share the same spent time, service times, road graph and edge costs.
function compareKeepingVisits({ network, sorted, raw, depot, completedCount, closed, spent, team }) {
  const calculate = (closures) => {
    const router = createRouter(network, closures);
    let cumulative = spent;
    const routes = sorted.slice(0, completedCount).map(row => ({ ...row, replan_status: "completed_preserved" }));
    for (let i = completedCount; i < sorted.length; i += 1) {
      const original = sorted[i];
      const task = raw.get(original.task_id);
      const origin = i ? router.taskPoint(raw.get(sorted[i - 1].task_id), true)
        : router.depotPoint(depot, sorted.map(row => raw.get(row.task_id)));
      const leg = router.route(i ? sorted[i - 1].task_id : depot.team_id, origin, task);
      if (leg.status !== "ok") throw new Error(leg.failure_reason);
      const service = Number(original.service_minutes);
      if (original.service_minutes == null || !Number.isFinite(service) || service < 0) throw new Error("점검 시간 정보가 없습니다.");
      cumulative += leg.travel_time_minutes + service;
      routes.push({ ...original, ...leg, travel_minutes: leg.travel_time_minutes, service_minutes: service,
        cumulative_minutes: rounded(cumulative), replan_status: "replanned",
        geometry_json: JSON.stringify(leg.route_link_ids.flatMap(id => router.links.get(id).geometry)) });
    }
    return { routes, total: rounded(cumulative), remaining: rounded(cumulative - spent) };
  };
  const before = calculate([]);
  const after = calculate(closed);
  return { status: "pass", routes: after.routes, unassigned: [], closedLinkIds: closed, completedCount,
    spentMinutes: rounded(spent), remainingMinutes: after.remaining, totalMinutes: after.total,
    spareMinutes: rounded(team.shiftMinutes - after.total), availableMinutes: team.shiftMinutes,
    overtimeMinutes: rounded(Math.max(0, after.total - team.shiftMinutes)), previewOnly: true,
    networkSource: network.source, timeBasis: "same_spent_and_service_plus_speed_limit_or_default",
    comparison: { beforeRoutes: before.routes, beforeTotalMinutes: before.total,
      beforeRemainingMinutes: before.remaining, additionalMinutes: rounded(after.total - before.total),
      changedLegCount: after.routes.slice(completedCount).filter((row, i) =>
        JSON.stringify(row.route_link_ids) !== JSON.stringify(before.routes[completedCount + i].route_link_ids)).length },
    closedRoads: network.links.filter(row => closed.includes(row[0])).map(row => ({ link_id: row[0], geometry_json: JSON.stringify(row[5]) })),
    manualApprovalRequired: true, approvalStatus: "review_required" };
}

// Replan the selected team's uncompleted visits, preserving the completed prefix.
export function replanClosure({ network, state, baseRoutes, taskRows, depot, completedCount = 0, closedLinkIds = [], elapsedMinutes = null, preserveVisitOrder = false }) {
  const sorted = [...baseRoutes].sort((a, b) => Number(a.sequence) - Number(b.sequence));
  if (!sorted.length || !depot || !state) return fail("먼저 출동계획을 만들어 주세요.");
  if (sorted.some((row, i) => row.team_id !== depot.team_id || Number(row.sequence) !== i + 1)
    || new Set(sorted.map((row) => row.task_id)).size !== sorted.length) return fail("선택팀의 방문 순서가 올바르지 않습니다.");
  if (!Number.isInteger(completedCount) || completedCount < 0 || completedCount > sorted.length) return fail("완료 지점은 방문 순서의 앞부분이어야 합니다.");
  const closed = [...new Set(closedLinkIds.map((id) => String(id).trim()).filter(Boolean))].sort();
  if (!closed.length) return fail("통제 구간을 입력해 주세요.");
  const team = state.resources.find((row) => row.teamId === depot.team_id);
  if (!team?.available || !Number.isInteger(team.personnelCount) || team.personnelCount < 1 || team.personnelCount > team.vehicleCapacity) return fail("팀의 출동 인원·차량 정원을 확인해 주세요.");
  if (!Number.isFinite(team.shiftMinutes) || team.shiftMinutes <= 0 || !Number.isInteger(team.maxTasks) || team.maxTasks < completedCount) return fail("가용 시간과 최대 점검 수를 확인해 주세요.");
  const completed = sorted.slice(0, completedCount);
  const completedMinutes = completed.reduce((sum, row) => sum + Number(row.travel_minutes) + Number(row.service_minutes), 0);
  const spent = elapsedMinutes == null ? completedMinutes : Number(elapsedMinutes);
  if (!Number.isFinite(spent) || spent < 0 || (spent > team.shiftMinutes && !preserveVisitOrder)) return fail("사용한 시간이 가용 시간을 넘거나 올바르지 않습니다.");
  if (completed.some((row) => [row.travel_minutes, row.service_minutes].some((value) => value == null || !Number.isFinite(Number(value)) || Number(value) < 0))) return fail("완료한 구간의 시간 정보가 없습니다.");
  const remainingIds = new Set(sorted.slice(completedCount).map((row) => row.task_id));
  const remainingTasks = state.tasks.filter((task) => remainingIds.has(task.taskId));
  if (remainingTasks.length !== remainingIds.size || remainingTasks.some((task) => task.excluded)) return fail("점검 대상이 달라졌습니다. 조건 수정에서 새 계획을 만들어 주세요.");
  if (remainingTasks.some((task) => task.fixed && task.assignedTeamId !== depot.team_id)) return fail("고정 담당팀이 달라졌습니다. 조건 수정에서 새 계획을 만들어 주세요.");
  const raw = new Map(taskRows.map((task) => [task.task_id, task]));
  if (sorted.some((row) => !raw.has(row.task_id))) return fail("점검 지점의 도로 정보가 없습니다.");
  try {
    if (preserveVisitOrder) return compareKeepingVisits({ network, sorted, raw, depot, completedCount, closed, spent, team });
    const matrix = computeDetourMatrix({ network, tasks: remainingTasks.map((task) => raw.get(task.taskId)), depot,
      originTask: completedCount ? raw.get(completed.at(-1).task_id) : null, closedLinkIds: closed });
    let next = [];
    if (remainingTasks.length) {
      const result = optimizeAllocation({ state: { ...state, resources: [{ ...team, shiftMinutes: team.shiftMinutes - spent, maxTasks: Math.max(0, team.maxTasks - completedCount) }], tasks: remainingTasks }, routeOptions: matrix.routes, routeLinks: matrix.routeLinks });
      if (result.status !== "pass") return { ...fail(result.message), completedRoutes: completed, routeOptions: matrix.routes };
      next = result.alternatives.find((a) => a.alternativeId === sorted[0].alternative_id)?.planRoutes || result.alternatives[0].planRoutes;
    }
    const routes = [
      ...completed.map((row) => ({ ...row, replan_status: "completed_preserved" })),
      ...next.map((row, i) => ({ ...row, sequence: completedCount + i + 1,
        cumulative_minutes: rounded(spent + row.cumulative_minutes), replan_status: "replanned" })),
    ];
    const assigned = new Set(next.map((row) => row.task_id));
    const unassigned = remainingTasks.filter((task) => !assigned.has(task.taskId)).map((task) => {
      const options = matrix.routes.filter((r) => r.destination_task_id === task.taskId);
      return { task_id: task.taskId, link_id: task.linkId, road_name: task.roadName,
        reason: options.some((r) => r.status === "ok") ? "남은 시간·필수 점검 조건 안에서 방문을 배정하지 못했습니다." : options[0]?.failure_reason || "통제 구간을 피하는 연결 경로가 없습니다." };
    });
    const remainingMinutes = next.reduce((sum, row) => sum + row.travel_minutes + row.service_minutes, 0);
    return { status: "pass", routes, unassigned, closedLinkIds: closed, completedCount, spentMinutes: rounded(spent),
      remainingMinutes: rounded(remainingMinutes), totalMinutes: rounded(spent + remainingMinutes),
      spareMinutes: rounded(team.shiftMinutes - spent - remainingMinutes), availableMinutes: team.shiftMinutes,
      routeOptions: matrix.routes, networkSource: network.source, timeBasis: "speed_limit_or_default",
      closedRoads: network.links.filter((row) => closed.includes(row[0])).map((row) => ({ link_id: row[0], geometry_json: JSON.stringify(row[5]) })),
      manualApprovalRequired: true, approvalStatus: "pending" };
  } catch (error) { return fail(error.message || "도로망 계산에 실패했습니다."); }
}
