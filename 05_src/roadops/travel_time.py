"""Build reproducible road-network travel-time matrices for RoadOps.

제주 방향성 노드·링크망으로 팀·현장 간 자유흐름 이동시간과 경로를 계산합니다.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, hypot, radians, sin, sqrt
from typing import Any, Iterable, Mapping

from roadops.resources import validate_resource_plan
from roadops.spatial import (
    GeoPoint,
    normalize_link_id,
    normalize_node_id,
    parse_link_geometry_wkt,
    parse_point,
)


TRAVEL_TIME_VERSION = "roadops-road-network-travel-time-v0.2"
ROUTE_SEMANTICS = "free_flow_speed_limit_estimate_not_live_eta"
LIVE_ROUTE_SEMANTICS = "its_live_speed_eta_with_speed_limit_fallback"


@dataclass(frozen=True)
class NetworkLink:
    link_id: str
    start_node_id: str
    end_node_id: str
    length_meters: float
    speed_kph: float
    travel_minutes: float
    speed_source: str
    geometry_parts: tuple[tuple[GeoPoint, ...], ...]


@dataclass(frozen=True)
class RouteOrigin:
    origin_id: str
    origin_type: str
    node_id: str | None
    connector_distance_meters: float | None
    connector_minutes: float | None
    origin_link_id: str | None = None
    origin_link_exit_meters: float = 0.0
    origin_link_exit_minutes: float = 0.0
    failure_reason: str | None = None


@dataclass(frozen=True)
class RouteDestination:
    task_id: str
    link_id: str
    node_id: str | None
    entry_distance_meters: float | None
    entry_minutes: float | None
    coordinate_offset_meters: float | None
    approach_only: bool
    failure_reason: str | None = None


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _haversine_meters(a: GeoPoint, b: GeoPoint) -> float:
    earth_radius_meters = 6_371_008.8
    lat_a = radians(a.latitude)
    lat_b = radians(b.latitude)
    delta_latitude = lat_b - lat_a
    delta_longitude = radians(b.longitude - a.longitude)
    haversine = sin(delta_latitude / 2) ** 2 + (
        cos(lat_a) * cos(lat_b) * sin(delta_longitude / 2) ** 2
    )
    return 2 * earth_radius_meters * asin(sqrt(haversine))


def _local_xy(point: GeoPoint, origin: GeoPoint) -> tuple[float, float]:
    mean_latitude = radians((point.latitude + origin.latitude) / 2)
    x = (point.longitude - origin.longitude) * 111_320 * cos(mean_latitude)
    y = (point.latitude - origin.latitude) * 110_540
    return x, y


def _geometry_length_meters(
    parts: tuple[tuple[GeoPoint, ...], ...],
) -> float:
    return sum(
        _haversine_meters(start, end)
        for part in parts
        for start, end in zip(part, part[1:])
    )


def _projection_on_geometry(
    point: GeoPoint,
    parts: tuple[tuple[GeoPoint, ...], ...],
) -> tuple[float, float]:
    """Return distance along geometry and perpendicular offset in meters."""

    best_offset: float | None = None
    best_along = 0.0
    cumulative = 0.0
    for part in parts:
        for start, end in zip(part, part[1:]):
            segment_length = _haversine_meters(start, end)
            ax, ay = _local_xy(start, point)
            bx, by = _local_xy(end, point)
            ab_x = bx - ax
            ab_y = by - ay
            length_squared = ab_x * ab_x + ab_y * ab_y
            if length_squared == 0:
                projection = 0.0
                offset = hypot(ax, ay)
            else:
                projection = max(
                    0.0,
                    min(1.0, -(ax * ab_x + ay * ab_y) / length_squared),
                )
                offset = hypot(
                    ax + projection * ab_x,
                    ay + projection * ab_y,
                )
            if best_offset is None or offset < best_offset:
                best_offset = offset
                best_along = cumulative + projection * segment_length
            cumulative += segment_length
    return best_along, best_offset if best_offset is not None else float("inf")


def _speed(value: Any, *, default_speed_kph: float) -> float:
    speed = _number(value)
    if speed is None or speed <= 0:
        return default_speed_kph
    return min(max(speed, 10.0), 110.0)


def _traffic_observed_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 14:
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S")
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def current_traffic_speeds_by_link(
    records: Iterable[Mapping[str, Any]],
    *,
    as_of: datetime,
    freshness_max_minutes: float = 30.0,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Select fresh positive ITS speeds without treating zero as measured movement."""

    if freshness_max_minutes <= 0:
        raise ValueError("freshness_max_minutes must be positive")
    selected: dict[str, tuple[datetime, float]] = {}
    counters: Counter[str] = Counter()
    source_row_count = 0
    for row in records:
        source_row_count += 1
        link_id = normalize_link_id(row.get("link_id"))
        observed_at = _traffic_observed_at(
            row.get("prcn_dt") or row.get("observed_at")
        )
        speed = _number(row.get("sped") if "sped" in row else row.get("speed_kph"))
        if link_id is None:
            counters["invalid_link"] += 1
            continue
        if observed_at is None:
            counters["invalid_timestamp"] += 1
            continue
        comparison_as_of = as_of
        if observed_at.tzinfo is None and comparison_as_of.tzinfo is not None:
            observed_at = observed_at.replace(tzinfo=comparison_as_of.tzinfo)
        elif observed_at.tzinfo is not None and comparison_as_of.tzinfo is None:
            comparison_as_of = comparison_as_of.replace(tzinfo=observed_at.tzinfo)
        elif observed_at.tzinfo is not None and comparison_as_of.tzinfo is not None:
            comparison_as_of = comparison_as_of.astimezone(observed_at.tzinfo)
        age_minutes = (comparison_as_of - observed_at).total_seconds() / 60
        if age_minutes < -5:
            counters["future_timestamp"] += 1
            continue
        if age_minutes > freshness_max_minutes:
            counters["stale"] += 1
            continue
        if speed is None or speed <= 0:
            counters["non_positive_speed"] += 1
            continue
        previous = selected.get(link_id)
        if previous is None or observed_at > previous[0]:
            selected[link_id] = (observed_at, min(max(speed, 5.0), 110.0))
    return (
        {link_id: value[1] for link_id, value in selected.items()},
        {
            "source_row_count": source_row_count,
            "fresh_speed_link_count": len(selected),
            "freshness_max_minutes": freshness_max_minutes,
            "excluded_counts": dict(sorted(counters.items())),
        },
    )


def build_network_graph(
    node_rows: Iterable[Mapping[str, Any]],
    link_rows: Iterable[Mapping[str, Any]],
    *,
    closed_link_ids: Iterable[str] = (),
    default_speed_kph: float = 30.0,
    observed_speed_by_link: Mapping[str, Any] | None = None,
) -> tuple[
    dict[str, GeoPoint],
    dict[str, NetworkLink],
    dict[str, list[NetworkLink]],
    dict[str, Any],
]:
    """Normalize a directed road graph and remove closed links from adjacency."""

    if default_speed_kph <= 0:
        raise ValueError("default_speed_kph must be positive")
    closed = {
        link_id
        for value in closed_link_ids
        if (link_id := normalize_link_id(value)) is not None
    }
    nodes: dict[str, GeoPoint] = {}
    issue_counts: Counter[str] = Counter()
    for row in node_rows:
        node_id = normalize_node_id(row.get("node_id"))
        point = parse_point(row.get("latitude"), row.get("longitude"))
        if node_id is None or point is None:
            issue_counts["invalid_node"] += 1
            continue
        if node_id in nodes:
            issue_counts["duplicate_node"] += 1
            continue
        nodes[node_id] = point

    links: dict[str, NetworkLink] = {}
    adjacency: defaultdict[str, list[NetworkLink]] = defaultdict(list)
    fallback_speed_count = 0
    observed_speed_count = 0
    observed_speeds = observed_speed_by_link or {}
    for row in link_rows:
        link_id = normalize_link_id(row.get("link_id"))
        start_node_id = normalize_node_id(row.get("start_node_id"))
        end_node_id = normalize_node_id(row.get("end_node_id"))
        if link_id is None or start_node_id is None or end_node_id is None:
            issue_counts["invalid_link_or_node_id"] += 1
            continue
        if link_id in links:
            issue_counts["duplicate_link"] += 1
            continue
        start = nodes.get(start_node_id)
        end = nodes.get(end_node_id)
        if start is None or end is None:
            issue_counts["missing_link_endpoint"] += 1
            continue
        geometry = parse_link_geometry_wkt(row.get("geometry_wkt"))
        if geometry is None:
            geometry = ((start, end),)
            issue_counts["geometry_endpoint_fallback"] += 1
        length = _geometry_length_meters(geometry)
        if length <= 0:
            issue_counts["zero_length_link"] += 1
            continue
        observed_speed = _number(observed_speeds.get(link_id))
        if observed_speed is not None and observed_speed > 0:
            speed = min(max(observed_speed, 5.0), 110.0)
            speed_source = "its_live_observation"
            observed_speed_count += 1
        else:
            raw_speed = _number(row.get("maximum_speed_limit"))
            if raw_speed is None or raw_speed <= 0:
                fallback_speed_count += 1
            speed = _speed(
                row.get("maximum_speed_limit"),
                default_speed_kph=default_speed_kph,
            )
            speed_source = "speed_limit_or_default"
        link = NetworkLink(
            link_id=link_id,
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            length_meters=length,
            speed_kph=speed,
            travel_minutes=(length / 1000) / speed * 60,
            speed_source=speed_source,
            geometry_parts=geometry,
        )
        links[link_id] = link
        if link_id not in closed:
            adjacency[start_node_id].append(link)

    for edges in adjacency.values():
        edges.sort(key=lambda edge: edge.link_id)
    report = {
        "node_count": len(nodes),
        "link_count": len(links),
        "routable_link_count": len(links) - len(closed & set(links)),
        "closed_link_count": len(closed),
        "known_closed_link_count": len(closed & set(links)),
        "unknown_closed_link_ids": sorted(closed - set(links)),
        "fallback_speed_link_count": fallback_speed_count,
        "observed_speed_link_count": observed_speed_count,
        "observed_speed_coverage": (
            round(observed_speed_count / len(links), 6) if links else 0.0
        ),
        "issue_counts": dict(sorted(issue_counts.items())),
    }
    return nodes, links, dict(adjacency), report


def _nearest_node(
    point: GeoPoint,
    nodes: Mapping[str, GeoPoint],
) -> tuple[str | None, float | None]:
    nearest_id: str | None = None
    nearest_distance: float | None = None
    for node_id, candidate in nodes.items():
        distance = _haversine_meters(point, candidate)
        if nearest_distance is None or distance < nearest_distance:
            nearest_id = node_id
            nearest_distance = distance
    return nearest_id, nearest_distance


def _nodes_reaching_destinations(
    adjacency: Mapping[str, list[NetworkLink]],
    destination_node_ids: Iterable[str],
) -> set[str]:
    """Return nodes that can reach at least one destination on the directed graph."""

    reverse_adjacency: defaultdict[str, list[str]] = defaultdict(list)
    for start_node_id, edges in adjacency.items():
        for edge in edges:
            reverse_adjacency[edge.end_node_id].append(start_node_id)

    reachable = {str(node_id) for node_id in destination_node_ids if node_id}
    pending = list(reachable)
    while pending:
        node_id = pending.pop()
        for predecessor in reverse_adjacency.get(node_id, ()):
            if predecessor in reachable:
                continue
            reachable.add(predecessor)
            pending.append(predecessor)
    return reachable


def _team_origins(
    resource_plan: Mapping[str, Any],
    nodes: Mapping[str, GeoPoint],
    *,
    destination_reachable_node_ids: set[str],
    max_snap_distance_meters: float,
    connector_speed_kph: float,
    connectivity_snap_tolerance_meters: float,
) -> list[RouteOrigin]:
    origins: list[RouteOrigin] = []
    reachable_nodes = {
        node_id: point
        for node_id, point in nodes.items()
        if node_id in destination_reachable_node_ids
    }
    for team in resource_plan["teams"]:
        point = parse_point(team["start_latitude"], team["start_longitude"])
        node_id, distance = _nearest_node(point, nodes) if point else (None, None)
        reachable_node_id, reachable_distance = (
            _nearest_node(point, reachable_nodes)
            if point and reachable_nodes
            else (None, None)
        )
        if (
            reachable_node_id is not None
            and reachable_distance is not None
            and reachable_distance <= max_snap_distance_meters
            and (
                distance is None
                or reachable_distance
                <= distance + connectivity_snap_tolerance_meters
            )
        ):
            node_id, distance = reachable_node_id, reachable_distance
        failure = None
        if node_id is None or distance is None:
            failure = "origin_network_node_missing"
        elif distance > max_snap_distance_meters:
            failure = "origin_snap_distance_exceeded"
        connector_minutes = (
            (distance / 1000) / connector_speed_kph * 60
            if distance is not None
            else None
        )
        origins.append(
            RouteOrigin(
                origin_id=str(team["team_id"]),
                origin_type="team_start",
                node_id=node_id,
                connector_distance_meters=distance,
                connector_minutes=connector_minutes,
                failure_reason=failure,
            )
        )
    return origins


def _task_location(
    task: Mapping[str, Any],
    link: NetworkLink,
) -> tuple[float, float] | None:
    point = parse_point(task.get("latitude"), task.get("longitude"))
    if point is None:
        return None
    return _projection_on_geometry(point, link.geometry_parts)


def _task_origins(
    tasks: Iterable[Mapping[str, Any]],
    links: Mapping[str, NetworkLink],
    closed_link_ids: set[str],
) -> list[RouteOrigin]:
    origins: list[RouteOrigin] = []
    for task in tasks:
        task_id = str(task["task_id"])
        link_id = normalize_link_id(task.get("link_id"))
        link = links.get(str(link_id)) if link_id else None
        location = _task_location(task, link) if link else None
        failure = None
        if link is None:
            failure = "origin_task_link_missing"
        elif location is None:
            failure = "origin_task_coordinate_missing"
        elif link.link_id in closed_link_ids:
            failure = "origin_task_link_closed"
        along = location[0] if location else 0.0
        exit_distance = max(0.0, link.length_meters - along) if link else 0.0
        exit_minutes = (
            (exit_distance / link.length_meters) * link.travel_minutes
            if link and link.length_meters > 0
            else 0.0
        )
        origins.append(
            RouteOrigin(
                origin_id=task_id,
                origin_type="field_task",
                node_id=link.end_node_id if link else None,
                connector_distance_meters=0.0,
                connector_minutes=0.0,
                origin_link_id=link.link_id if link else link_id,
                origin_link_exit_meters=exit_distance,
                origin_link_exit_minutes=exit_minutes,
                failure_reason=failure,
            )
        )
    return origins


def _destinations(
    tasks: Iterable[Mapping[str, Any]],
    links: Mapping[str, NetworkLink],
    closed_link_ids: set[str],
) -> list[RouteDestination]:
    destinations: list[RouteDestination] = []
    for task in tasks:
        task_id = str(task["task_id"])
        link_id = normalize_link_id(task.get("link_id"))
        link = links.get(str(link_id)) if link_id else None
        location = _task_location(task, link) if link else None
        failure = None
        if link is None:
            failure = "destination_link_missing"
        elif location is None:
            failure = "destination_coordinate_missing"
        approach_only = bool(link and link.link_id in closed_link_ids)
        along = location[0] if location else None
        offset = location[1] if location else None
        entry_distance = 0.0 if approach_only and along is not None else along
        entry_minutes = (
            (entry_distance / link.length_meters) * link.travel_minutes
            if link and entry_distance is not None and link.length_meters > 0
            else None
        )
        destinations.append(
            RouteDestination(
                task_id=task_id,
                link_id=link.link_id if link else str(link_id or ""),
                node_id=link.start_node_id if link else None,
                entry_distance_meters=entry_distance,
                entry_minutes=entry_minutes,
                coordinate_offset_meters=offset,
                approach_only=approach_only,
                failure_reason=failure,
            )
        )
    return destinations


def _dijkstra(
    start_node_id: str,
    adjacency: Mapping[str, list[NetworkLink]],
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, tuple[str, str]],
]:
    times = {start_node_id: 0.0}
    distances = {start_node_id: 0.0}
    predecessor: dict[str, tuple[str, str]] = {}
    queue = [(0.0, start_node_id)]
    while queue:
        elapsed, node_id = heapq.heappop(queue)
        if elapsed > times[node_id] + 1e-12:
            continue
        for link in adjacency.get(node_id, ()):
            candidate = elapsed + link.travel_minutes
            known = times.get(link.end_node_id)
            if known is None or candidate < known - 1e-12:
                times[link.end_node_id] = candidate
                distances[link.end_node_id] = (
                    distances[node_id] + link.length_meters
                )
                predecessor[link.end_node_id] = (node_id, link.link_id)
                heapq.heappush(queue, (candidate, link.end_node_id))
    return times, distances, predecessor


def _path_link_ids(
    start_node_id: str,
    destination_node_id: str,
    predecessor: Mapping[str, tuple[str, str]],
) -> list[str] | None:
    if start_node_id == destination_node_id:
        return []
    path: list[str] = []
    cursor = destination_node_id
    seen: set[str] = set()
    while cursor != start_node_id:
        if cursor in seen or cursor not in predecessor:
            return None
        seen.add(cursor)
        previous, link_id = predecessor[cursor]
        path.append(link_id)
        cursor = previous
    path.reverse()
    return path


def _route_id(origin_id: str, task_id: str) -> str:
    raw = f"{TRAVEL_TIME_VERSION}|{origin_id}|{task_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _failed_route(
    origin: RouteOrigin,
    destination: RouteDestination,
    reason: str,
    *,
    route_semantics: str,
) -> dict[str, Any]:
    return {
        "route_id": _route_id(origin.origin_id, destination.task_id),
        "origin_id": origin.origin_id,
        "origin_type": origin.origin_type,
        "destination_task_id": destination.task_id,
        "destination_link_id": destination.link_id,
        "status": "unavailable",
        "failure_reason": reason,
        "source_mode": "network_compute",
        "route_semantics": route_semantics,
        "travel_time_minutes": None,
        "distance_km": None,
        "network_travel_minutes": None,
        "network_distance_km": None,
        "origin_connector_minutes": origin.connector_minutes,
        "origin_connector_distance_meters": origin.connector_distance_meters,
        "origin_link_exit_minutes": origin.origin_link_exit_minutes,
        "destination_link_entry_minutes": destination.entry_minutes,
        "destination_coordinate_offset_meters": destination.coordinate_offset_meters,
        "origin_node_id": origin.node_id,
        "destination_node_id": destination.node_id,
        "destination_approach_only": destination.approach_only,
        "route_link_ids": [],
        "route_link_count": 0,
        "live_speed_link_count": 0,
        "live_speed_coverage": 0.0,
    }


def _build_route(
    origin: RouteOrigin,
    destination: RouteDestination,
    *,
    times: Mapping[str, float],
    distances: Mapping[str, float],
    predecessor: Mapping[str, tuple[str, str]],
    links: Mapping[str, NetworkLink],
    route_semantics: str,
) -> dict[str, Any]:
    if origin.origin_type == "field_task" and origin.origin_id == destination.task_id:
        route_links: list[str] = []
        network_minutes = 0.0
        network_distance = 0.0
        origin_exit_minutes = 0.0
        origin_exit_distance = 0.0
        destination_entry_minutes = 0.0
        destination_entry_distance = 0.0
    else:
        if origin.failure_reason:
            return _failed_route(
                origin,
                destination,
                origin.failure_reason,
                route_semantics=route_semantics,
            )
        if destination.failure_reason:
            return _failed_route(
                origin,
                destination,
                destination.failure_reason,
                route_semantics=route_semantics,
            )
        if origin.node_id is None or destination.node_id is None:
            return _failed_route(
                origin,
                destination,
                "route_endpoint_missing",
                route_semantics=route_semantics,
            )
        network_minutes = times.get(destination.node_id)
        network_distance = distances.get(destination.node_id)
        if network_minutes is None or network_distance is None:
            return _failed_route(
                origin,
                destination,
                "no_directed_network_path",
                route_semantics=route_semantics,
            )
        path = _path_link_ids(
            origin.node_id, destination.node_id, predecessor
        )
        if path is None:
            return _failed_route(
                origin,
                destination,
                "path_reconstruction_failed",
                route_semantics=route_semantics,
            )
        route_links = list(path)
        origin_exit_minutes = origin.origin_link_exit_minutes
        origin_exit_distance = origin.origin_link_exit_meters
        destination_entry_minutes = float(destination.entry_minutes or 0.0)
        destination_entry_distance = float(
            destination.entry_distance_meters or 0.0
        )
        if origin.origin_link_id and origin_exit_distance > 0:
            route_links.insert(0, origin.origin_link_id)
        if destination_entry_distance > 0:
            route_links.append(destination.link_id)

    connector_minutes = float(origin.connector_minutes or 0.0)
    connector_distance = float(origin.connector_distance_meters or 0.0)
    total_minutes = (
        connector_minutes
        + origin_exit_minutes
        + network_minutes
        + destination_entry_minutes
    )
    total_distance = (
        connector_distance
        + origin_exit_distance
        + network_distance
        + destination_entry_distance
    )
    counted_links = [links[link_id] for link_id in route_links if link_id in links]
    live_speed_link_count = sum(
        link.speed_source == "its_live_observation" for link in counted_links
    )
    live_speed_coverage = (
        live_speed_link_count / len(counted_links) if counted_links else 0.0
    )
    return {
        "route_id": _route_id(origin.origin_id, destination.task_id),
        "origin_id": origin.origin_id,
        "origin_type": origin.origin_type,
        "destination_task_id": destination.task_id,
        "destination_link_id": destination.link_id,
        "status": "ok_approach_only" if destination.approach_only else "ok",
        "failure_reason": None,
        "source_mode": "network_compute",
        "route_semantics": route_semantics,
        "travel_time_minutes": round(total_minutes, 3),
        "distance_km": round(total_distance / 1000, 3),
        "network_travel_minutes": round(network_minutes, 3),
        "network_distance_km": round(network_distance / 1000, 3),
        "origin_connector_minutes": round(connector_minutes, 3),
        "origin_connector_distance_meters": round(connector_distance, 3),
        "origin_link_exit_minutes": round(origin_exit_minutes, 3),
        "destination_link_entry_minutes": round(
            destination_entry_minutes, 3
        ),
        "destination_coordinate_offset_meters": (
            round(destination.coordinate_offset_meters, 3)
            if destination.coordinate_offset_meters is not None
            else None
        ),
        "origin_node_id": origin.node_id,
        "destination_node_id": destination.node_id,
        "destination_approach_only": destination.approach_only,
        "route_link_ids": route_links,
        "route_link_count": len(route_links),
        "live_speed_link_count": live_speed_link_count,
        "live_speed_coverage": round(live_speed_coverage, 6),
    }


def _quality_report(
    result: Mapping[str, Any],
    *,
    resource_validation: Mapping[str, Any],
    graph_report: Mapping[str, Any],
) -> dict[str, Any]:
    rows = list(result.get("routes", []))
    failed_checks: list[str] = []
    expected_route_count = int(result.get("origin_count", 0)) * int(
        result.get("destination_count", 0)
    )
    if len(rows) != expected_route_count:
        failed_checks.append("route_matrix_completeness")
    if int(graph_report.get("node_count", 0)) == 0 or int(
        graph_report.get("link_count", 0)
    ) == 0:
        failed_checks.append("network_graph_empty")
    route_ids = [row.get("route_id") for row in rows]
    if len(route_ids) != len(set(route_ids)):
        failed_checks.append("route_id_uniqueness")
    closed = set(result.get("closed_link_ids", []))
    traversed_closed = [
        row["route_id"]
        for row in rows
        if set(row.get("route_link_ids", [])) & closed
    ]
    if traversed_closed:
        failed_checks.append("closed_link_traversal")
    if any(
        row.get("travel_time_minutes") is not None
        and float(row["travel_time_minutes"]) < 0
        for row in rows
    ):
        failed_checks.append("negative_travel_time")
    status_counts = Counter(str(row.get("status")) for row in rows)
    unavailable_count = status_counts.get("unavailable", 0)
    graph_limitation_count = sum(
        int(value) for value in graph_report.get("issue_counts", {}).values()
    ) + len(graph_report.get("unknown_closed_link_ids", []))
    status = (
        "fail"
        if failed_checks
        else (
            "pass_with_limitations"
            if unavailable_count or graph_limitation_count
            else "pass"
        )
    )
    return {
        "schema_version": 1,
        "status": status,
        "travel_time_version": TRAVEL_TIME_VERSION,
        "route_semantics": result.get("route_semantics", ROUTE_SEMANTICS),
        "resource_validation": dict(resource_validation),
        "graph": dict(graph_report),
        "origin_count": int(result.get("origin_count", 0)),
        "destination_count": int(result.get("destination_count", 0)),
        "expected_route_count": expected_route_count,
        "route_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "source_mode_counts": dict(
            sorted(Counter(str(row.get("source_mode")) for row in rows).items())
        ),
        "closed_link_traversal_count": len(traversed_closed),
        "failed_checks": failed_checks,
    }


def build_travel_time_matrix(
    resource_payload: Mapping[str, Any],
    field_tasks: Iterable[Mapping[str, Any]],
    node_rows: Iterable[Mapping[str, Any]],
    link_rows: Iterable[Mapping[str, Any]],
    *,
    closed_link_ids: Iterable[str] = (),
    include_excluded_tasks: bool = False,
    default_speed_kph: float = 30.0,
    connector_speed_kph: float = 20.0,
    max_snap_distance_meters: float = 2_000.0,
    connectivity_snap_tolerance_meters: float = 250.0,
    observed_speed_by_link: Mapping[str, Any] | None = None,
    traffic_profile: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build team/task-to-task route times on the directed Jeju road graph."""

    if connector_speed_kph <= 0:
        raise ValueError("connector_speed_kph must be positive")
    if max_snap_distance_meters < 0:
        raise ValueError("max_snap_distance_meters must be non-negative")
    if connectivity_snap_tolerance_meters < 0:
        raise ValueError("connectivity_snap_tolerance_meters must be non-negative")
    resource_plan, resource_report = validate_resource_plan(resource_payload)
    if resource_report["status"] == "fail":
        result = {
            "schema_version": 1,
            "travel_time_version": TRAVEL_TIME_VERSION,
            "status": "fail",
            "failure_reason": "resource_input_validation_failed",
            "routes": [],
        }
        report = {
            "schema_version": 1,
            "status": "fail",
            "resource_validation": resource_report,
            "failed_checks": ["resource_input_validation"],
        }
        return result, report

    tasks = [
        dict(task)
        for task in field_tasks
        if include_excluded_tasks or not bool(task.get("excluded"))
    ]
    tasks.sort(key=lambda task: str(task["task_id"]))
    closed = {
        link_id
        for value in closed_link_ids
        if (link_id := normalize_link_id(value)) is not None
    }
    nodes, links, adjacency, graph_report = build_network_graph(
        node_rows,
        link_rows,
        closed_link_ids=closed,
        default_speed_kph=default_speed_kph,
        observed_speed_by_link=observed_speed_by_link,
    )
    route_semantics = (
        LIVE_ROUTE_SEMANTICS
        if int(graph_report.get("observed_speed_link_count", 0)) > 0
        else ROUTE_SEMANTICS
    )
    destinations = _destinations(tasks, links, closed)
    destination_reachable_node_ids = _nodes_reaching_destinations(
        adjacency,
        (
            destination.node_id
            for destination in destinations
            if destination.node_id is not None
            and destination.failure_reason is None
        ),
    )
    origins = _team_origins(
        resource_plan,
        nodes,
        destination_reachable_node_ids=destination_reachable_node_ids,
        max_snap_distance_meters=max_snap_distance_meters,
        connector_speed_kph=connector_speed_kph,
        connectivity_snap_tolerance_meters=connectivity_snap_tolerance_meters,
    ) + _task_origins(tasks, links, closed)
    routes: list[dict[str, Any]] = []
    for origin in origins:
        if origin.node_id is not None and origin.failure_reason is None:
            times, distances, predecessor = _dijkstra(origin.node_id, adjacency)
        else:
            times, distances, predecessor = {}, {}, {}
        for destination in destinations:
            routes.append(
                _build_route(
                    origin,
                    destination,
                    times=times,
                    distances=distances,
                    predecessor=predecessor,
                    links=links,
                    route_semantics=route_semantics,
                )
            )
    routes.sort(key=lambda row: (row["origin_id"], row["destination_task_id"]))
    timestamp = generated_at.isoformat() if generated_at else None
    result = {
        "schema_version": 1,
        "travel_time_version": TRAVEL_TIME_VERSION,
        "scenario_id": resource_plan["scenario_id"],
        "generated_at": timestamp,
        "status": "pending_quality_check",
        "route_semantics": route_semantics,
        "execution": {
            "mode": "network_compute",
            "cache_key": None,
            "computed_at": timestamp,
        },
        "parameters": {
            "default_speed_kph": default_speed_kph,
            "connector_speed_kph": connector_speed_kph,
            "max_snap_distance_meters": max_snap_distance_meters,
            "connectivity_snap_tolerance_meters": (
                connectivity_snap_tolerance_meters
            ),
            "directed_graph": True,
            "turn_restrictions_applied": False,
            "traffic_profile": dict(traffic_profile or {}),
        },
        "limitations": [
            *(
                ["unobserved_links_use_speed_limit_or_default_fallback"]
                if route_semantics == LIVE_ROUTE_SEMANTICS
                else ["speed_limits_are_free_flow_estimates_not_live_traffic_eta"]
            ),
            "turn_restrictions_are_not_applied_in_v0.2",
            "team_start_snap_prefers_a_nearby_node_that_reaches_a_task",
            "team_start_connector_is_a_straight_line_estimate",
        ],
        "closed_link_ids": sorted(closed),
        "origin_count": len(origins),
        "destination_count": len(destinations),
        "routes": routes,
    }
    report = _quality_report(
        result,
        resource_validation=resource_report,
        graph_report=graph_report,
    )
    result["status"] = report["status"]
    return result, report


def travel_matrix_cache_key(
    *,
    resource_payload: Mapping[str, Any],
    field_tasks: Iterable[Mapping[str, Any]],
    network_identity: Mapping[str, Any],
    closed_link_ids: Iterable[str],
    parameters: Mapping[str, Any],
) -> str:
    """Hash every input that can change a route matrix."""

    payload = {
        "travel_time_version": TRAVEL_TIME_VERSION,
        "resource_payload": resource_payload,
        "field_tasks": sorted(
            [dict(task) for task in field_tasks],
            key=lambda task: str(task.get("task_id")),
        ),
        "network_identity": dict(network_identity),
        "closed_link_ids": sorted(
            link_id
            for value in closed_link_ids
            if (link_id := normalize_link_id(value)) is not None
        ),
        "parameters": dict(parameters),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def replay_cached_travel_matrix(
    cached_result: Mapping[str, Any],
    *,
    cache_key: str,
    resource_validation: Mapping[str, Any],
    graph_report: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a cached matrix with the same route schema and explicit provenance."""

    result = json.loads(json.dumps(cached_result, ensure_ascii=False))
    result["execution"] = {
        **dict(result.get("execution", {})),
        "mode": "cache_replay",
        "cache_key": cache_key,
    }
    for row in result.get("routes", []):
        row["source_mode"] = "cache_replay"
    report = _quality_report(
        result,
        resource_validation=resource_validation,
        graph_report=graph_report,
    )
    result["status"] = report["status"]
    return result, report


def recheck_allocation_plans(
    allocation_plans: Iterable[Mapping[str, Any]],
    travel_matrix: Mapping[str, Any],
    resource_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Recalculate baseline plan feasibility with network travel times."""

    route_index = {
        (str(row["origin_id"]), str(row["destination_task_id"])): row
        for row in travel_matrix.get("routes", [])
    }
    planning_start = datetime.fromisoformat(
        str(resource_plan["planning"]["planning_start_at"])
    )
    available_minutes: dict[str, float] = {}
    for team in resource_plan["teams"]:
        shift_start = datetime.fromisoformat(str(team["shift_start_at"]))
        shift_end = datetime.fromisoformat(str(team["shift_end_at"]))
        available_minutes[str(team["team_id"])] = (
            shift_end - max(planning_start, shift_start)
        ).total_seconds() / 60

    results: list[dict[str, Any]] = []
    for plan in allocation_plans:
        assignments_by_team: defaultdict[str, list[Mapping[str, Any]]] = (
            defaultdict(list)
        )
        for assignment in plan.get("assignments", []):
            assignments_by_team[str(assignment["team_id"])].append(assignment)
        team_results: list[dict[str, Any]] = []
        unavailable_routes = 0
        for team_id in sorted(available_minutes):
            assignments = sorted(
                assignments_by_team.get(team_id, []),
                key=lambda row: int(row["sequence"]),
            )
            origin_id = team_id
            travel_minutes = 0.0
            service_minutes = 0.0
            failed_legs: list[dict[str, Any]] = []
            for assignment in assignments:
                task_id = str(assignment["task_id"])
                route = route_index.get((origin_id, task_id))
                if route is None or route.get("travel_time_minutes") is None:
                    unavailable_routes += 1
                    failed_legs.append(
                        {
                            "origin_id": origin_id,
                            "destination_task_id": task_id,
                            "reason": (
                                route.get("failure_reason")
                                if route is not None
                                else "route_row_missing"
                            ),
                        }
                    )
                else:
                    travel_minutes += float(route["travel_time_minutes"])
                service_minutes += float(assignment["service_minutes"])
                origin_id = task_id
            elapsed = travel_minutes + service_minutes
            available = available_minutes[team_id]
            team_results.append(
                {
                    "team_id": team_id,
                    "assignment_count": len(assignments),
                    "travel_minutes": round(travel_minutes, 3),
                    "service_minutes": round(service_minutes, 3),
                    "elapsed_minutes": round(elapsed, 3),
                    "available_minutes": round(available, 3),
                    "shift_exceeded_minutes": (
                        round(max(0.0, elapsed - available), 3)
                        if not failed_legs
                        else None
                    ),
                    "failed_legs": failed_legs,
                }
            )
        exceeded = [
            row["team_id"]
            for row in team_results
            if row["shift_exceeded_minutes"] is not None
            and row["shift_exceeded_minutes"] > 0
        ]
        results.append(
            {
                "strategy": plan.get("strategy"),
                "original_travel_time_semantics": "straight_line_constant_speed",
                "original_total_estimated_travel_minutes": plan.get(
                    "metrics", {}
                ).get("total_estimated_travel_minutes"),
                "network_total_travel_minutes": round(
                    sum(row["travel_minutes"] for row in team_results), 3
                ),
                "maximum_team_elapsed_minutes": round(
                    max(
                        (row["elapsed_minutes"] for row in team_results),
                        default=0.0,
                    ),
                    3,
                ),
                "shift_exceeded_team_ids": exceeded,
                "shift_exceeded_team_count": len(exceeded),
                "unavailable_route_leg_count": unavailable_routes,
                "team_results": team_results,
            }
        )
    return results
