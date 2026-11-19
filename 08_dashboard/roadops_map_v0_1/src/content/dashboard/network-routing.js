// Directed road routing. Units and midpoint projection match roadops.travel_time.
const round = (v) => Number(v.toFixed(3));
const radians = (v) => v * Math.PI / 180;
function distance(a, b) {
  const lat = radians(b[1] - a[1]);
  const lon = radians(b[0] - a[0]);
  const h = Math.sin(lat / 2) ** 2 + Math.cos(radians(a[1])) * Math.cos(radians(b[1])) * Math.sin(lon / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}

function project(point, parts) {
  let best = Infinity;
  let along = 0;
  let cumulative = 0;
  const xy = (p) => [(p[0] - point[0]) * 111320 * Math.cos(radians((p[1] + point[1]) / 2)), (p[1] - point[1]) * 110540];
  for (const part of parts) for (let i = 1; i < part.length; i += 1) {
    const a = xy(part[i - 1]); const b = xy(part[i]);
    const dx = b[0] - a[0]; const dy = b[1] - a[1];
    const square = dx * dx + dy * dy;
    const fraction = square ? Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / square)) : 0;
    const offset = Math.hypot(a[0] + fraction * dx, a[1] + fraction * dy);
    const length = distance(part[i - 1], part[i]);
    if (offset < best) { best = offset; along = cumulative + fraction * length; }
    cumulative += length;
  }
  return { along, offset: best };
}

class Heap {
  values = [];
  less(a, b) { return a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]); }
  push(v) {
    const a = this.values; a.push(v); let i = a.length - 1;
    while (i > 0) { const parent = (i - 1) >> 1; if (!this.less(v, a[parent])) break; a[i] = a[parent]; i = parent; }
    a[i] = v;
  }
  pop() {
    const a = this.values; const result = a[0]; const v = a.pop();
    if (a.length) {
      let i = 0;
      while (i * 2 + 1 < a.length) {
        let child = i * 2 + 1;
        if (child + 1 < a.length && this.less(a[child + 1], a[child])) child += 1;
        if (!this.less(a[child], v)) break;
        a[i] = a[child]; i = child;
      }
      a[i] = v;
    }
    return result;
  }
}

export function createRouter(network, closedLinkIds = []) {
  if (network?.schemaVersion !== 1 || !network.links?.length || !network.nodes?.length) throw new Error("계산에 필요한 도로망이 없습니다.");
  const nodes = new Map(network.nodes.map(([id, lat, lon]) => [id, [lon, lat]]));
  const links = new Map(network.links.map(([id, start, end, meters, minutes, geometry]) => [id, { id, start, end, meters, minutes, geometry }]));
  const closed = new Set(closedLinkIds.map(String));
  for (const id of closed) if (!links.has(id)) throw new Error(`도로망에 없는 통제 구간입니다: ${id}`);
  const adjacency = new Map();
  const reverse = new Map();
  for (const link of links.values()) {
    if (closed.has(link.id)) continue;
    if (!adjacency.has(link.start)) adjacency.set(link.start, []);
    adjacency.get(link.start).push(link);
    if (!reverse.has(link.end)) reverse.set(link.end, []);
    reverse.get(link.end).push(link.start);
  }
  const cache = new Map();
  function shortest(start) {
    if (cache.has(start)) return cache.get(start);
    const times = new Map([[start, 0]]); const previous = new Map(); const queue = new Heap(); queue.push([0, start]);
    while (queue.values.length) {
      const [time, node] = queue.pop();
      if (time > times.get(node) + 1e-12) continue;
      for (const edge of adjacency.get(node) || []) {
        const next = time + edge.minutes;
        if (!times.has(edge.end) || next < times.get(edge.end) - 1e-12) {
          times.set(edge.end, next); previous.set(edge.end, edge); queue.push([next, edge.end]);
        }
      }
    }
    const result = { times, previous }; cache.set(start, result); return result;
  }
  function taskPoint(task, origin) {
    const link = links.get(String(task.link_id));
    if (!link) return { failure: "점검 도로가 도로망에 없습니다." };
    if (closed.has(link.id)) return { failure: "점검 대상 도로 자체가 통제되어 있습니다." };
    if (task.latitude == null || task.longitude == null || !Number.isFinite(Number(task.latitude)) || !Number.isFinite(Number(task.longitude))) return { failure: "점검 지점의 좌표가 없습니다." };
    const location = project([Number(task.longitude), Number(task.latitude)], link.geometry);
    if (!Number.isFinite(location.offset)) return { failure: "점검 도로의 위치를 계산할 수 없습니다." };
    const meters = origin ? Math.max(0, link.meters - location.along) : location.along;
    return { node: origin ? link.end : link.start, link, meters, minutes: meters / link.meters * link.minutes };
  }
  function depotPoint(team, tasks) {
    if (team?.start_longitude == null || team?.start_latitude == null) return { failure: "출발 거점의 좌표가 없습니다." };
    const point = [Number(team.start_longitude), Number(team.start_latitude)];
    if (!point.every(Number.isFinite)) return { failure: "출발 거점의 좌표가 없습니다." };
    const reachable = new Set(tasks.map((t) => taskPoint(t, false)).filter((p) => !p.failure).map((p) => p.node));
    const pending = [...reachable];
    while (pending.length) for (const prev of reverse.get(pending.pop()) || []) if (!reachable.has(prev)) { reachable.add(prev); pending.push(prev); }
    let nearest = null; let connected = null;
    for (const [node, position] of nodes) {
      const meters = distance(point, position);
      if (!nearest || meters < nearest.meters) nearest = { node, meters };
      if (reachable.has(node) && (!connected || meters < connected.meters)) connected = { node, meters };
    }
    const result = connected && connected.meters <= 2000 && connected.meters <= nearest.meters + 250 ? connected : nearest;
    return result && result.meters <= 2000 ? { ...result, minutes: result.meters / 1000 / 20 * 60 } : { failure: "출발 거점이 도로망에서 너무 멉니다." };
  }
  function route(originId, origin, task) {
    const destination = taskPoint(task, false);
    const base = { origin_id: originId, destination_task_id: task.task_id, destination_link_id: task.link_id, source_mode: "browser_network_compute", route_semantics: "speed_limit_or_default", route_link_ids: [], status: "unavailable", travel_time_minutes: null };
    if (origin.failure || destination.failure) return { ...base, failure_reason: origin.failure || destination.failure };
    const { times, previous } = shortest(origin.node);
    if (!times.has(destination.node)) return { ...base, failure_reason: "통제 구간을 피하는 연결 경로가 없습니다." };
    const path = []; let cursor = destination.node;
    while (cursor !== origin.node) { const edge = previous.get(cursor); if (!edge) return { ...base, failure_reason: "경로 복원에 실패했습니다." }; path.push(edge); cursor = edge.start; }
    path.reverse();
    const ids = [...(origin.link && origin.meters > 0 ? [origin.link.id] : []), ...path.map((edge) => edge.id), ...(destination.meters > 0 ? [destination.link.id] : [])];
    if (ids.some((id) => closed.has(id))) throw new Error("계산 결과에 통제 구간이 포함됐습니다.");
    return { ...base, status: "ok", route_id: `detour:${[...closed].sort().join(",")}:${originId}:${task.task_id}`,
      travel_time_minutes: round(origin.minutes + times.get(destination.node) + destination.minutes),
      distance_km: round((origin.meters + path.reduce((n, e) => n + e.meters, 0) + destination.meters) / 1000),
      route_link_ids: ids, route_link_count: ids.length };
  }
  return { links, taskPoint, depotPoint, route };
}

export function computeDetourMatrix({ network, tasks, depot, originTask = null, closedLinkIds }) {
  const router = createRouter(network, closedLinkIds);
  const start = originTask ? router.taskPoint(originTask, true) : router.depotPoint(depot, tasks);
  const origins = [[String(depot.team_id), start], ...tasks.map((task) => [task.task_id, router.taskPoint(task, true)])];
  const routes = origins.flatMap(([id, origin]) => tasks.map((task) => router.route(id, origin, task)));
  const used = new Set(routes.flatMap((route) => route.route_link_ids));
  return { routes, routeLinks: [...used].map((id) => ({ link_id: id, geometry_json: JSON.stringify(router.links.get(id).geometry) })) };
}
