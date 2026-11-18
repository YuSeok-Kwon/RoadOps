function numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function distanceKm(origin, destination) {
  const originLongitude = numeric(origin?.start_longitude ?? origin?.longitude);
  const originLatitude = numeric(origin?.start_latitude ?? origin?.latitude);
  const destinationLongitude = numeric(destination?.longitude ?? destination?.start_longitude);
  const destinationLatitude = numeric(destination?.latitude ?? destination?.start_latitude);
  if ([originLongitude, originLatitude, destinationLongitude, destinationLatitude].some((value) => value == null)) {
    return Number.POSITIVE_INFINITY;
  }
  const radians = (degrees) => degrees * Math.PI / 180;
  const latitudeDelta = radians(destinationLatitude - originLatitude);
  const longitudeDelta = radians(destinationLongitude - originLongitude);
  const a = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(radians(originLatitude)) * Math.cos(radians(destinationLatitude))
    * Math.sin(longitudeDelta / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function tasksForDepot({ tasks, routes, depotId, depot, planId, limit = 6 }) {
  if (!depotId) return [];
  if (depot) {
    return tasks
      .filter((task) => !task.excluded && (!task.fixed_team_id || task.fixed_team_id === depotId))
      .map((task) => ({ ...task, depot_distance_km: distanceKm(depot, task) }))
      .filter((task) => Number.isFinite(task.depot_distance_km))
      .sort((left, right) => left.depot_distance_km - right.depot_distance_km)
      .slice(0, limit)
      .sort((left, right) => Number(right.priority_score || 0) - Number(left.priority_score || 0));
  }
  const assignedTaskIds = new Set(routes
    .filter((route) => route.team_id === depotId && (!planId || route.alternative_id === planId))
    .map((route) => String(route.task_id)));
  const candidates = tasks.filter((task) => assignedTaskIds.has(String(task.task_id)) && !task.excluded);
  const sorted = candidates.sort((left, right) => (
    Number(right.priority_score || 0) - Number(left.priority_score || 0)
  ));
  return sorted.slice(0, limit);
}

export function nearbyRows(origin, rows, limit = 3) {
  if (!origin) return [];
  return rows
    .map((row) => ({ ...row, distance_km: distanceKm(origin, row) }))
    .filter((row) => Number.isFinite(row.distance_km))
    .sort((left, right) => left.distance_km - right.distance_km)
    .slice(0, limit);
}

function routeGeometry(routeOption, routeLinksById) {
  const parts = [];
  for (const linkId of routeOption?.route_link_ids ?? []) {
    const source = routeLinksById.get(String(linkId));
    if (!source?.geometry_json) continue;
    try {
      const parsed = JSON.parse(source.geometry_json);
      if (Array.isArray(parsed)) parts.push(...parsed);
    } catch {
      // Keep the route usable even if one source link has malformed geometry.
    }
  }
  return parts.length ? JSON.stringify(parts) : null;
}

export function buildManualRoutes({
  selectedTaskIds,
  tasks,
  routes,
  depotId,
  planId,
  routeOptions = [],
  routeLinks = [],
}) {
  const tasksById = new Map(tasks.map((task) => [String(task.task_id), task]));
  const routeLinksById = new Map(routeLinks.map((row) => [String(row.link_id), row]));
  return selectedTaskIds.flatMap((taskId, index) => {
    const task = tasksById.get(String(taskId));
    if (!task) return [];
    const originId = index === 0 ? depotId : selectedTaskIds[index - 1];
    const routeOption = routeOptions.find((candidate) => candidate.origin_id === originId
      && candidate.destination_task_id === task.task_id && candidate.status === "ok");
    const route = routes.find((candidate) => candidate.team_id === depotId
      && candidate.task_id === task.task_id
      && (!planId || candidate.alternative_id === planId))
      ?? routes.find((candidate) => candidate.team_id === depotId && candidate.task_id === task.task_id);
    if (!route && !routeOption) return [];
    const geometryJson = routeGeometry(routeOption, routeLinksById);
    return [{
      ...route,
      alternative_id: "manual",
      team_id: depotId,
      task_id: task.task_id,
      link_id: task.link_id,
      road_name: task.road_name,
      sequence: index + 1,
      priority_score: task.priority_score,
      service_minutes: task.service_minutes ?? route?.service_minutes ?? 0,
      travel_minutes: routeOption?.travel_time_minutes ?? route?.travel_minutes ?? 0,
      distance_km: routeOption?.distance_km ?? route?.distance_km,
      route_link_count: routeOption?.route_link_count ?? route?.route_link_count,
      live_speed_coverage: routeOption?.live_speed_coverage ?? route?.live_speed_coverage,
      route_semantics: routeOption?.route_semantics ?? route?.route_semantics,
      geometry_json: geometryJson ?? route?.geometry_json,
    }];
  });
}

export function routeSummary(routes) {
  return routes.reduce((summary, route) => ({
    travelMinutes: summary.travelMinutes + Number(route.travel_minutes || 0),
    serviceMinutes: summary.serviceMinutes + Number(route.service_minutes || 0),
  }), { travelMinutes: 0, serviceMinutes: 0 });
}

export function historicalPlaces(rows, tasks, limit = 3) {
  const tasksByLink = new Map(tasks.map((task) => [String(task.link_id), task]));
  return rows.slice(0, limit).map((row) => {
    const places = (Array.isArray(row.event_link_ids) ? row.event_link_ids : [])
      .map((linkId) => tasksByLink.get(String(linkId)))
      .filter(Boolean);
    return { ...row, matched_places: places };
  });
}
