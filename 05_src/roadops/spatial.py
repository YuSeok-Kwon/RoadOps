"""Spatial join utilities for Jeju road links and live events.

제주 도로 링크와 실시간 이벤트를 결합하기 위한 공간 유틸리티입니다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, hypot, log, pi, radians, sin, tan
import re
from typing import Any, Iterable, Mapping


JEJU_BOUNDS = {
    "min_latitude": 32.9,
    "max_latitude": 34.1,
    "min_longitude": 125.8,
    "max_longitude": 127.3,
}


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 point expressed as latitude and longitude."""

    latitude: float
    longitude: float


@dataclass(frozen=True)
class RoadLink:
    """A road link reconstructed from its start and end nodes."""

    link_id: str
    start_node_id: str
    end_node_id: str
    start: GeoPoint
    end: GeoPoint
    geometry_parts: tuple[tuple[GeoPoint, ...], ...] = ()


@dataclass(frozen=True)
class EventMatch:
    """How one live event was associated with a road link."""

    event_index: int
    source_link_id_raw: str | None
    source_link_id: str | None
    matched_link_id: str | None
    method: str
    distance_meters: float | None
    nearest_candidate_link_id: str | None = None
    nearest_candidate_distance_meters: float | None = None
    second_nearest_link_id: str | None = None
    second_nearest_distance_meters: float | None = None
    distance_margin_meters: float | None = None
    candidate_count_within_threshold: int | None = None
    coordinate_consistent: bool | None = None
    reason: str | None = None


@dataclass(frozen=True)
class JoinAudit:
    """Inspectable coverage metrics for an event-to-link join."""

    total_events: int
    exact_matches: int
    spatial_matches: int
    ambiguous_events: int
    unmatched_events: int
    invalid_events: int
    coordinate_conflicts: int
    matches: tuple[EventMatch, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["exact_match_rate"] = (
            self.exact_matches / self.total_events if self.total_events else None
        )
        result["combined_match_rate"] = (
            (self.exact_matches + self.spatial_matches) / self.total_events
            if self.total_events
            else None
        )
        result["scoring_eligible_events"] = (
            self.exact_matches + self.spatial_matches - self.coordinate_conflicts
        )
        result["scoring_eligible_rate"] = (
            result["scoring_eligible_events"] / self.total_events
            if self.total_events
            else None
        )
        return result


_WKT_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_WKT_PAIR = re.compile(rf"^\s*({_WKT_NUMBER})\s+({_WKT_NUMBER})(?:\s+{_WKT_NUMBER})?\s*$")


def normalize_link_id(value: Any) -> str | None:
    """Return a valid ten-digit standard link ID without guessing missing digits."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        text = str(int(value))
    else:
        text = str(value).strip()
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
    return text if len(text) == 10 and text.isdigit() else None


def normalize_node_id(value: Any) -> str | None:
    """Normalize a ten-digit road node ID using the link-ID policy."""

    return normalize_link_id(value)


def parse_point(latitude: Any, longitude: Any) -> GeoPoint | None:
    """Parse a coordinate only when it is numeric and inside broad Jeju bounds."""

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None

    if not (
        JEJU_BOUNDS["min_latitude"] <= lat <= JEJU_BOUNDS["max_latitude"]
        and JEJU_BOUNDS["min_longitude"] <= lon <= JEJU_BOUNDS["max_longitude"]
    ):
        return None
    return GeoPoint(latitude=lat, longitude=lon)


def _parse_wkt_coordinate_sequence(value: str) -> tuple[GeoPoint, ...] | None:
    points: list[GeoPoint] = []
    for token in value.split(","):
        match = _WKT_PAIR.match(token)
        if match is None:
            return None
        point = parse_point(match.group(2), match.group(1))
        if point is None:
            return None
        points.append(point)
    return tuple(points) if len(points) >= 2 else None


def parse_link_geometry_wkt(
    value: Any,
) -> tuple[tuple[GeoPoint, ...], ...] | None:
    """Parse a 2D/3D LINESTRING or MULTILINESTRING in WGS84 order."""

    text = str(value or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper.startswith("LINESTRING"):
        body = text[len("LINESTRING") :].strip()
        if not (body.startswith("(") and body.endswith(")")):
            return None
        sequence = _parse_wkt_coordinate_sequence(body[1:-1])
        return (sequence,) if sequence is not None else None
    if not upper.startswith("MULTILINESTRING"):
        return None

    body = text[len("MULTILINESTRING") :].strip()
    if not (body.startswith("(") and body.endswith(")")):
        return None
    body = body[1:-1].strip()
    groups: list[str] = []
    depth = 0
    start: int | None = None
    for index, character in enumerate(body):
        if character == "(":
            if depth == 0:
                start = index + 1
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0 and start is not None:
                groups.append(body[start:index])
                start = None
        elif depth == 0 and character not in {",", " ", "\t", "\r", "\n"}:
            return None
    if depth != 0 or not groups:
        return None
    parts = [_parse_wkt_coordinate_sequence(group) for group in groups]
    if any(part is None for part in parts):
        return None
    return tuple(part for part in parts if part is not None)


def build_road_links(
    link_rows: Iterable[Mapping[str, Any]],
    node_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, RoadLink], list[dict[str, Any]]]:
    """Build link geometries and return every rejected record as an issue."""

    nodes: dict[str, GeoPoint] = {}
    issues: list[dict[str, Any]] = []

    for row_index, row in enumerate(node_rows):
        node_id = normalize_node_id(row.get("node_id"))
        point = parse_point(row.get("latitude"), row.get("longitude"))
        if node_id is None or point is None:
            issues.append(
                {
                    "record_type": "node",
                    "row_index": row_index,
                    "reason": "invalid_node_id_or_coordinate",
                }
            )
            continue
        if node_id in nodes:
            issues.append(
                {
                    "record_type": "node",
                    "row_index": row_index,
                    "reason": "duplicate_node_id",
                    "node_id": node_id,
                }
            )
            continue
        nodes[node_id] = point

    links: dict[str, RoadLink] = {}
    for row_index, row in enumerate(link_rows):
        link_id = normalize_link_id(row.get("link_id"))
        start_node_id = normalize_node_id(row.get("start_node_id"))
        end_node_id = normalize_node_id(row.get("end_node_id"))
        if link_id is None or start_node_id is None or end_node_id is None:
            issues.append(
                {
                    "record_type": "link",
                    "row_index": row_index,
                    "reason": "invalid_link_or_node_id",
                }
            )
            continue
        if link_id in links:
            issues.append(
                {
                    "record_type": "link",
                    "row_index": row_index,
                    "reason": "duplicate_link_id",
                    "link_id": link_id,
                }
            )
            continue
        start = nodes.get(start_node_id)
        end = nodes.get(end_node_id)
        if start is None or end is None:
            issues.append(
                {
                    "record_type": "link",
                    "row_index": row_index,
                    "reason": "missing_start_or_end_node",
                    "link_id": link_id,
                }
            )
            continue
        geometry_raw = row.get("geometry_wkt")
        geometry_parts = parse_link_geometry_wkt(geometry_raw)
        if geometry_raw not in (None, "") and geometry_parts is None:
            issues.append(
                {
                    "record_type": "link",
                    "row_index": row_index,
                    "reason": "invalid_geometry_wkt_fallback_to_endpoints",
                    "link_id": link_id,
                }
            )
        if geometry_parts is None:
            geometry_parts = ((start, end),)
        links[link_id] = RoadLink(
            link_id=link_id,
            start_node_id=start_node_id,
            end_node_id=end_node_id,
            start=start,
            end=end,
            geometry_parts=geometry_parts,
        )
    return links, issues


def _local_xy(point: GeoPoint, origin: GeoPoint) -> tuple[float, float]:
    """Project a nearby WGS84 point to local meters for distance checks."""

    mean_latitude = radians((point.latitude + origin.latitude) / 2)
    x = (point.longitude - origin.longitude) * 111_320 * cos(mean_latitude)
    y = (point.latitude - origin.latitude) * 110_540
    return x, y


def point_to_link_distance_meters(point: GeoPoint, link: RoadLink) -> float:
    """Calculate the shortest local distance to every segment of a road geometry."""

    nearest_distance: float | None = None
    geometry_parts = link.geometry_parts or ((link.start, link.end),)
    for part in geometry_parts:
        for start, end in zip(part, part[1:]):
            ax, ay = _local_xy(start, point)
            bx, by = _local_xy(end, point)
            ab_x = bx - ax
            ab_y = by - ay
            length_squared = ab_x * ab_x + ab_y * ab_y
            if length_squared == 0:
                distance = hypot(ax, ay)
            else:
                projection = max(
                    0.0,
                    min(1.0, -(ax * ab_x + ay * ab_y) / length_squared),
                )
                nearest_x = ax + projection * ab_x
                nearest_y = ay + projection * ab_y
                distance = hypot(nearest_x, nearest_y)
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
    if nearest_distance is None:
        return min(
            hypot(*_local_xy(link.start, point)),
            hypot(*_local_xy(link.end, point)),
        )
    return nearest_distance


def _raw_link_id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _coordinate_value_supplied(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _round_distance(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _nearest_link_candidates(
    point: GeoPoint,
    links: Mapping[str, RoadLink],
    *,
    threshold_meters: float,
) -> tuple[
    RoadLink | None,
    float | None,
    RoadLink | None,
    float | None,
    int,
]:
    nearest_link: RoadLink | None = None
    nearest_distance: float | None = None
    second_nearest_link: RoadLink | None = None
    second_nearest_distance: float | None = None
    candidate_count = 0
    for link in links.values():
        distance = point_to_link_distance_meters(point, link)
        if distance <= threshold_meters:
            candidate_count += 1
        if nearest_distance is None or distance < nearest_distance:
            second_nearest_link = nearest_link
            second_nearest_distance = nearest_distance
            nearest_link = link
            nearest_distance = distance
        elif second_nearest_distance is None or distance < second_nearest_distance:
            second_nearest_link = link
            second_nearest_distance = distance
    return (
        nearest_link,
        nearest_distance,
        second_nearest_link,
        second_nearest_distance,
        candidate_count,
    )


def audit_event_link_join(
    events: Iterable[Mapping[str, Any]],
    links: Mapping[str, RoadLink],
    *,
    spatial_fallback_threshold_meters: float = 30.0,
    spatial_fallback_min_margin_meters: float = 5.0,
    exact_coordinate_threshold_meters: float = 30.0,
) -> JoinAudit:
    """Join by ID first, then apply distance and ambiguity gates to coordinates."""

    if spatial_fallback_threshold_meters < 0:
        raise ValueError("spatial_fallback_threshold_meters must be non-negative")
    if spatial_fallback_min_margin_meters < 0:
        raise ValueError("spatial_fallback_min_margin_meters must be non-negative")
    if exact_coordinate_threshold_meters < 0:
        raise ValueError("exact_coordinate_threshold_meters must be non-negative")

    matches: list[EventMatch] = []
    exact_matches = 0
    spatial_matches = 0
    ambiguous_events = 0
    unmatched_events = 0
    invalid_events = 0
    coordinate_conflicts = 0

    for event_index, event in enumerate(events):
        source_link_id_raw = _raw_link_id(event.get("link_id"))
        source_link_id = normalize_link_id(source_link_id_raw)
        point = parse_point(event.get("latitude"), event.get("longitude"))
        coordinate_supplied = _coordinate_value_supplied(
            event.get("latitude")
        ) or _coordinate_value_supplied(event.get("longitude"))
        if source_link_id is not None and source_link_id in links:
            exact_matches += 1
            coordinate_distance = (
                point_to_link_distance_meters(point, links[source_link_id])
                if point is not None
                else None
            )
            coordinate_consistent = (
                coordinate_distance <= exact_coordinate_threshold_meters
                if coordinate_distance is not None
                else False
                if coordinate_supplied
                else None
            )
            if coordinate_consistent is False:
                coordinate_conflicts += 1
            candidate_details = (
                _nearest_link_candidates(
                    point,
                    links,
                    threshold_meters=spatial_fallback_threshold_meters,
                )
                if coordinate_consistent is False and point is not None
                else (None, None, None, None, 0)
            )
            (
                nearest_candidate,
                nearest_candidate_distance,
                second_candidate,
                second_candidate_distance,
                candidate_count,
            ) = candidate_details
            distance_margin = (
                second_candidate_distance - nearest_candidate_distance
                if nearest_candidate_distance is not None
                and second_candidate_distance is not None
                else None
            )
            matches.append(
                EventMatch(
                    event_index=event_index,
                    source_link_id_raw=source_link_id_raw,
                    source_link_id=source_link_id,
                    matched_link_id=source_link_id,
                    method="exact_link_id",
                    distance_meters=_round_distance(coordinate_distance),
                    nearest_candidate_link_id=(
                        nearest_candidate.link_id
                        if nearest_candidate is not None
                        else None
                    ),
                    nearest_candidate_distance_meters=_round_distance(
                        nearest_candidate_distance
                    ),
                    second_nearest_link_id=(
                        second_candidate.link_id
                        if second_candidate is not None
                        else None
                    ),
                    second_nearest_distance_meters=_round_distance(
                        second_candidate_distance
                    ),
                    distance_margin_meters=_round_distance(distance_margin),
                    candidate_count_within_threshold=(
                        candidate_count if coordinate_consistent is False else None
                    ),
                    coordinate_consistent=coordinate_consistent,
                    reason=(
                        "coordinate_exceeds_exact_link_threshold"
                        if coordinate_consistent is False
                        and coordinate_distance is not None
                        else "invalid_coordinate_for_exact_link"
                        if coordinate_consistent is False
                        else "coordinate_unavailable_for_validation"
                        if coordinate_consistent is None
                        else None
                    ),
                )
            )
            continue

        if point is None:
            invalid_events += 1
            matches.append(
                EventMatch(
                    event_index=event_index,
                    source_link_id_raw=source_link_id_raw,
                    source_link_id=source_link_id,
                    matched_link_id=None,
                    method="invalid",
                    distance_meters=None,
                    reason="missing_or_invalid_coordinate",
                )
            )
            continue

        (
            nearest_link,
            nearest_distance,
            second_nearest_link,
            second_nearest_distance,
            candidate_count,
        ) = _nearest_link_candidates(
            point,
            links,
            threshold_meters=spatial_fallback_threshold_meters,
        )

        distance_margin = (
            second_nearest_distance - nearest_distance
            if nearest_distance is not None and second_nearest_distance is not None
            else None
        )

        if (
            nearest_link is not None
            and nearest_distance is not None
            and nearest_distance <= spatial_fallback_threshold_meters
        ):
            if (
                distance_margin is not None
                and distance_margin < spatial_fallback_min_margin_meters
            ):
                ambiguous_events += 1
                matches.append(
                    EventMatch(
                        event_index=event_index,
                        source_link_id_raw=source_link_id_raw,
                        source_link_id=source_link_id,
                        matched_link_id=None,
                        method="ambiguous",
                        distance_meters=_round_distance(nearest_distance),
                        nearest_candidate_link_id=nearest_link.link_id,
                        nearest_candidate_distance_meters=_round_distance(
                            nearest_distance
                        ),
                        second_nearest_link_id=(
                            second_nearest_link.link_id
                            if second_nearest_link is not None
                            else None
                        ),
                        second_nearest_distance_meters=_round_distance(
                            second_nearest_distance
                        ),
                        distance_margin_meters=_round_distance(distance_margin),
                        candidate_count_within_threshold=candidate_count,
                        coordinate_consistent=None,
                        reason="nearest_candidates_inside_minimum_margin",
                    )
                )
            else:
                spatial_matches += 1
                matches.append(
                    EventMatch(
                        event_index=event_index,
                        source_link_id_raw=source_link_id_raw,
                        source_link_id=source_link_id,
                        matched_link_id=nearest_link.link_id,
                        method="spatial_fallback",
                        distance_meters=_round_distance(nearest_distance),
                        nearest_candidate_link_id=nearest_link.link_id,
                        nearest_candidate_distance_meters=_round_distance(
                            nearest_distance
                        ),
                        second_nearest_link_id=(
                            second_nearest_link.link_id
                            if second_nearest_link is not None
                            else None
                        ),
                        second_nearest_distance_meters=_round_distance(
                            second_nearest_distance
                        ),
                        distance_margin_meters=_round_distance(distance_margin),
                        candidate_count_within_threshold=candidate_count,
                        coordinate_consistent=True,
                        reason="source_link_id_missing_or_unmatched",
                    )
                )
        else:
            unmatched_events += 1
            matches.append(
                EventMatch(
                    event_index=event_index,
                    source_link_id_raw=source_link_id_raw,
                    source_link_id=source_link_id,
                    matched_link_id=None,
                    method="unmatched",
                    distance_meters=_round_distance(nearest_distance),
                    nearest_candidate_link_id=(
                        nearest_link.link_id if nearest_link is not None else None
                    ),
                    nearest_candidate_distance_meters=_round_distance(
                        nearest_distance
                    ),
                    second_nearest_link_id=(
                        second_nearest_link.link_id
                        if second_nearest_link is not None
                        else None
                    ),
                    second_nearest_distance_meters=_round_distance(
                        second_nearest_distance
                    ),
                    distance_margin_meters=_round_distance(distance_margin),
                    candidate_count_within_threshold=candidate_count,
                    reason="no_link_within_spatial_threshold",
                )
            )

    return JoinAudit(
        total_events=len(matches),
        exact_matches=exact_matches,
        spatial_matches=spatial_matches,
        ambiguous_events=ambiguous_events,
        unmatched_events=unmatched_events,
        invalid_events=invalid_events,
        coordinate_conflicts=coordinate_conflicts,
        matches=tuple(matches),
    )


def taas_linestring(link: RoadLink) -> str:
    """Format a road link for the TAAS detailed-link risk endpoint."""

    return (
        "LineString("
        f"{link.start.longitude:.8f} {link.start.latitude:.8f},"
        f"{link.end.longitude:.8f} {link.end.latitude:.8f}"
        ")"
    )


def kma_grid_from_wgs84(latitude: float, longitude: float) -> tuple[int, int]:
    """Convert WGS84 coordinates to the KMA 5 km forecast grid."""

    re = 6371.00877 / 5.0
    slat1 = 30.0 * pi / 180.0
    slat2 = 60.0 * pi / 180.0
    olon = 126.0 * pi / 180.0
    olat = 38.0 * pi / 180.0
    xo = 43.0
    yo = 136.0

    sn = log(cos(slat1) / cos(slat2)) / log(
        tan(pi * 0.25 + slat2 * 0.5) / tan(pi * 0.25 + slat1 * 0.5)
    )
    sf = tan(pi * 0.25 + slat1 * 0.5)
    sf = pow(sf, sn) * cos(slat1) / sn
    ro = tan(pi * 0.25 + olat * 0.5)
    ro = re * sf / pow(ro, sn)

    ra = tan(pi * 0.25 + latitude * pi / 360.0)
    ra = re * sf / pow(ra, sn)
    theta = longitude * pi / 180.0 - olon
    if theta > pi:
        theta -= 2.0 * pi
    if theta < -pi:
        theta += 2.0 * pi
    theta *= sn

    x = int(ra * sin(theta) + xo + 0.5)
    y = int(ro - ra * cos(theta) + yo + 0.5)
    return x, y
