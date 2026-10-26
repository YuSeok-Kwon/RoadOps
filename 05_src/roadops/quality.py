"""Data-quality checks for RoadOps road-network inputs.

RoadOps 도로망 입력의 키, 좌표, 중복, 참조 무결성을 점검합니다.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from roadops.probe import extract_records
from roadops.spatial import build_road_links, normalize_link_id, normalize_node_id, parse_point


@dataclass(frozen=True)
class RoadNetworkThresholds:
    """Minimum acceptable rates for the first real-data gate."""

    id_validity_min: float = 0.99
    coordinate_validity_min: float = 0.99
    uniqueness_min: float = 1.0
    referential_integrity_min: float = 1.0
    geometry_build_min: float = 0.99
    self_loop_free_min: float = 1.0
    attribute_validity_min: float = 0.95
    source_geometry_validity_min: float = 0.99
    largest_component_share_min: float = 0.95


@dataclass(frozen=True)
class QualityCheck:
    """One inspectable quality rule and its observed result."""

    check_id: str
    dimension: str
    severity: str
    numerator: int
    denominator: int
    observed_rate: float | None
    minimum_rate: float
    passed: bool
    meaning: str


def _canonicalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in row.items()}


def _pick(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _rate_check(
    *,
    check_id: str,
    dimension: str,
    severity: str,
    numerator: int,
    denominator: int,
    minimum_rate: float,
    meaning: str,
) -> QualityCheck:
    rate = numerator / denominator if denominator else None
    return QualityCheck(
        check_id=check_id,
        dimension=dimension,
        severity=severity,
        numerator=numerator,
        denominator=denominator,
        observed_rate=round(rate, 6) if rate is not None else None,
        minimum_rate=minimum_rate,
        passed=rate is not None and rate >= minimum_rate,
        meaning=meaning,
    )


def _append_issue(
    issues: list[dict[str, Any]],
    issue_counts: Counter[str],
    *,
    issue: str,
    dataset: str,
    row_index: int | None = None,
    sample_limit: int,
    **identifiers: Any,
) -> None:
    issue_counts[issue] += 1
    if len(issues) >= sample_limit:
        return
    sample = {"dataset": dataset, "issue": issue}
    if row_index is not None:
        sample["row_index"] = row_index
    sample.update({key: value for key, value in identifiers.items() if value is not None})
    issues.append(sample)


def _parse_number(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number


def _valid_source_geometry(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return (
        text.startswith("LINESTRING (") or text.startswith("MULTILINESTRING (")
    ) and text.endswith(")")


def _component_sizes(
    node_ids: set[str], links: Iterable[Mapping[str, str | None]]
) -> list[int]:
    adjacency: defaultdict[str, set[str]] = defaultdict(set)
    for link in links:
        start = link.get("start_node_id")
        end = link.get("end_node_id")
        if start in node_ids and end in node_ids and start != end:
            adjacency[start].add(end)
            adjacency[end].add(start)

    seen: set[str] = set()
    sizes: list[int] = []
    for start in node_ids:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        size = 0
        while queue:
            node_id = queue.popleft()
            size += 1
            for neighbor in adjacency.get(node_id, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def profile_road_network(
    link_rows: Iterable[Mapping[str, Any]],
    node_rows: Iterable[Mapping[str, Any]],
    *,
    thresholds: RoadNetworkThresholds | None = None,
    issue_sample_limit: int = 25,
) -> dict[str, Any]:
    """Profile the road-network grain and enforce the first join-readiness gates."""

    if issue_sample_limit < 0:
        raise ValueError("issue_sample_limit must be non-negative")

    rules = thresholds or RoadNetworkThresholds()
    links = [_canonicalize_row(row) for row in link_rows]
    nodes = [_canonicalize_row(row) for row in node_rows]
    issues: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()

    valid_node_ids: list[str] = []
    valid_node_coordinates = 0
    normalized_nodes: list[dict[str, Any]] = []
    for row_index, row in enumerate(nodes):
        raw_node_id = _pick(row, "node_id")
        node_id = normalize_node_id(raw_node_id)
        latitude = _pick(row, "latitude", "lat")
        longitude = _pick(row, "longitude", "lon", "lng")
        point = parse_point(latitude, longitude)
        if node_id is None:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_node_id",
                dataset="nodes",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                raw_node_id=str(raw_node_id) if raw_node_id is not None else None,
            )
        else:
            valid_node_ids.append(node_id)
        if point is None:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_node_coordinate",
                dataset="nodes",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                node_id=node_id,
            )
        else:
            valid_node_coordinates += 1
        normalized_nodes.append(
            {
                "node_id": node_id,
                "latitude": point.latitude if point else None,
                "longitude": point.longitude if point else None,
            }
        )

    node_id_counts = Counter(valid_node_ids)
    duplicate_node_ids = {key: count for key, count in node_id_counts.items() if count > 1}
    duplicate_node_excess = sum(count - 1 for count in duplicate_node_ids.values())
    for node_id, count in sorted(duplicate_node_ids.items()):
        _append_issue(
            issues,
            issue_counts,
            issue="duplicate_node_id",
            dataset="nodes",
            sample_limit=issue_sample_limit,
            node_id=node_id,
            occurrence_count=count,
        )

    known_node_ids = set(valid_node_ids)
    valid_link_ids: list[str] = []
    valid_endpoint_rows = 0
    endpoint_reference_count = 0
    matched_endpoint_reference_count = 0
    self_loop_count = 0
    descriptive_road_names = 0
    valid_lane_counts = 0
    valid_speed_limits = 0
    valid_source_geometries = 0
    normalized_links: list[dict[str, Any]] = []
    for row_index, row in enumerate(links):
        raw_link_id = _pick(row, "link_id")
        raw_start = _pick(row, "start_node_id", "f_node", "from_node_id")
        raw_end = _pick(row, "end_node_id", "t_node", "to_node_id")
        link_id = normalize_link_id(raw_link_id)
        start_node_id = normalize_node_id(raw_start)
        end_node_id = normalize_node_id(raw_end)

        if link_id is None:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_link_id",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                raw_link_id=str(raw_link_id) if raw_link_id is not None else None,
            )
        else:
            valid_link_ids.append(link_id)

        if start_node_id is None or end_node_id is None:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_endpoint_node_id",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                link_id=link_id,
            )
        else:
            valid_endpoint_rows += 1
            endpoint_reference_count += 2
            for role, node_id in (("start", start_node_id), ("end", end_node_id)):
                if node_id in known_node_ids:
                    matched_endpoint_reference_count += 1
                else:
                    _append_issue(
                        issues,
                        issue_counts,
                        issue="orphan_endpoint_node",
                        dataset="links",
                        row_index=row_index,
                        sample_limit=issue_sample_limit,
                        link_id=link_id,
                        endpoint_role=role,
                        node_id=node_id,
                    )
            if start_node_id == end_node_id:
                self_loop_count += 1
                _append_issue(
                    issues,
                    issue_counts,
                    issue="self_loop_link",
                    dataset="links",
                    row_index=row_index,
                    sample_limit=issue_sample_limit,
                    link_id=link_id,
                    node_id=start_node_id,
                )

        road_name = str(_pick(row, "road_name") or "").strip()
        if road_name and road_name != "-":
            descriptive_road_names += 1
        else:
            _append_issue(
                issues,
                issue_counts,
                issue="missing_descriptive_road_name",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                link_id=link_id,
            )

        lane_count = _parse_number(_pick(row, "lane_count", "lanes"))
        if lane_count is not None and lane_count.is_integer() and 1 <= lane_count <= 20:
            valid_lane_counts += 1
        else:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_lane_count",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                link_id=link_id,
            )

        speed_limit = _parse_number(
            _pick(row, "maximum_speed_limit", "maximum_speed", "max_spd")
        )
        if speed_limit is not None and 0 < speed_limit <= 200:
            valid_speed_limits += 1
        else:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_maximum_speed_limit",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                link_id=link_id,
            )

        if _valid_source_geometry(_pick(row, "geometry_wkt", "geometry")):
            valid_source_geometries += 1
        else:
            _append_issue(
                issues,
                issue_counts,
                issue="invalid_source_geometry",
                dataset="links",
                row_index=row_index,
                sample_limit=issue_sample_limit,
                link_id=link_id,
            )

        normalized_links.append(
            {
                "link_id": link_id,
                "start_node_id": start_node_id,
                "end_node_id": end_node_id,
            }
        )

    link_id_counts = Counter(valid_link_ids)
    duplicate_link_ids = {key: count for key, count in link_id_counts.items() if count > 1}
    duplicate_link_excess = sum(count - 1 for count in duplicate_link_ids.values())
    for link_id, count in sorted(duplicate_link_ids.items()):
        _append_issue(
            issues,
            issue_counts,
            issue="duplicate_link_id",
            dataset="links",
            sample_limit=issue_sample_limit,
            link_id=link_id,
            occurrence_count=count,
        )

    built_links, _ = build_road_links(normalized_links, normalized_nodes)
    component_sizes = _component_sizes(set(node_id_counts), normalized_links)
    largest_component_nodes = component_sizes[0] if component_sizes else 0
    checks = [
        _rate_check(
            check_id="node_id_validity",
            dimension="validity",
            severity="critical",
            numerator=len(valid_node_ids),
            denominator=len(nodes),
            minimum_rate=rules.id_validity_min,
            meaning="Rows with a valid ten-digit node_id.",
        ),
        _rate_check(
            check_id="node_id_uniqueness",
            dimension="uniqueness",
            severity="critical",
            numerator=len(node_id_counts),
            denominator=len(valid_node_ids),
            minimum_rate=rules.uniqueness_min,
            meaning="Valid node IDs that are unique.",
        ),
        _rate_check(
            check_id="node_coordinate_validity",
            dimension="validity",
            severity="high",
            numerator=valid_node_coordinates,
            denominator=len(nodes),
            minimum_rate=rules.coordinate_validity_min,
            meaning="Node rows with numeric WGS84 coordinates inside broad Jeju bounds.",
        ),
        _rate_check(
            check_id="link_id_validity",
            dimension="validity",
            severity="critical",
            numerator=len(valid_link_ids),
            denominator=len(links),
            minimum_rate=rules.id_validity_min,
            meaning="Rows with a valid ten-digit link_id.",
        ),
        _rate_check(
            check_id="link_id_uniqueness",
            dimension="uniqueness",
            severity="critical",
            numerator=len(link_id_counts),
            denominator=len(valid_link_ids),
            minimum_rate=rules.uniqueness_min,
            meaning="Valid link IDs that are unique.",
        ),
        _rate_check(
            check_id="link_endpoint_id_validity",
            dimension="validity",
            severity="critical",
            numerator=valid_endpoint_rows,
            denominator=len(links),
            minimum_rate=rules.id_validity_min,
            meaning="Link rows whose start and end node IDs are valid.",
        ),
        _rate_check(
            check_id="link_node_referential_integrity",
            dimension="integrity",
            severity="critical",
            numerator=matched_endpoint_reference_count,
            denominator=endpoint_reference_count,
            minimum_rate=rules.referential_integrity_min,
            meaning="Valid link endpoints that resolve to a supplied node.",
        ),
        _rate_check(
            check_id="link_geometry_build_rate",
            dimension="integrity",
            severity="high",
            numerator=len(built_links),
            denominator=len(links),
            minimum_rate=rules.geometry_build_min,
            meaning="Link rows that can be reconstructed from two valid endpoint nodes.",
        ),
        _rate_check(
            check_id="self_loop_free_rate",
            dimension="consistency",
            severity="medium",
            numerator=valid_endpoint_rows - self_loop_count,
            denominator=valid_endpoint_rows,
            minimum_rate=rules.self_loop_free_min,
            meaning="Valid-endpoint links whose start and end nodes differ.",
        ),
        _rate_check(
            check_id="descriptive_road_name_rate",
            dimension="completeness",
            severity="medium",
            numerator=descriptive_road_names,
            denominator=len(links),
            minimum_rate=rules.attribute_validity_min,
            meaning="Link rows with a non-empty road name other than the '-' placeholder.",
        ),
        _rate_check(
            check_id="lane_count_validity",
            dimension="validity",
            severity="high",
            numerator=valid_lane_counts,
            denominator=len(links),
            minimum_rate=rules.attribute_validity_min,
            meaning="Link rows whose lane count is an integer from 1 through 20.",
        ),
        _rate_check(
            check_id="maximum_speed_limit_validity",
            dimension="validity",
            severity="high",
            numerator=valid_speed_limits,
            denominator=len(links),
            minimum_rate=rules.attribute_validity_min,
            meaning="Link rows whose maximum speed is greater than 0 and at most 200 km/h.",
        ),
        _rate_check(
            check_id="source_geometry_validity",
            dimension="validity",
            severity="high",
            numerator=valid_source_geometries,
            denominator=len(links),
            minimum_rate=rules.source_geometry_validity_min,
            meaning="Link rows with LINESTRING or MULTILINESTRING WKT geometry.",
        ),
        _rate_check(
            check_id="largest_connected_component_share",
            dimension="consistency",
            severity="high",
            numerator=largest_component_nodes,
            denominator=len(node_id_counts),
            minimum_rate=rules.largest_component_share_min,
            meaning="Unique valid nodes in the largest undirected connected component.",
        ),
    ]

    failed_checks = [check.check_id for check in checks if not check.passed]
    return {
        "schema_version": 2,
        "dataset": "road_network",
        "grain": {
            "nodes": "one row per node_id",
            "links": "one row per link_id",
        },
        "status": "pass" if not failed_checks else "fail",
        "failed_checks": failed_checks,
        "thresholds": asdict(rules),
        "summary": {
            "node_rows": len(nodes),
            "valid_unique_node_ids": len(node_id_counts),
            "duplicate_node_row_excess": duplicate_node_excess,
            "link_rows": len(links),
            "valid_unique_link_ids": len(link_id_counts),
            "duplicate_link_row_excess": duplicate_link_excess,
            "orphan_endpoint_references": (
                endpoint_reference_count - matched_endpoint_reference_count
            ),
            "self_loop_links": self_loop_count,
            "built_link_geometries": len(built_links),
            "descriptive_road_names": descriptive_road_names,
            "valid_lane_counts": valid_lane_counts,
            "valid_maximum_speed_limits": valid_speed_limits,
            "valid_source_geometries": valid_source_geometries,
            "connected_components": len(component_sizes),
            "largest_component_nodes": largest_component_nodes,
            "isolated_nodes": sum(size == 1 for size in component_sizes),
            "largest_component_share": (
                round(largest_component_nodes / len(node_id_counts), 6)
                if node_id_counts
                else None
            ),
            "largest_component_sizes": component_sizes[:10],
        },
        "checks": [asdict(check) for check in checks],
        "issue_counts": dict(sorted(issue_counts.items())),
        "issue_sample": issues,
        "issue_sample_truncated": sum(issue_counts.values()) > len(issues),
    }


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load CSV, JSON, or JSON Lines records without mutating the source file."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        last_error: UnicodeDecodeError | None = None
        for encoding in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                with source.open("r", encoding=encoding, newline="") as handle:
                    return [dict(row) for row in csv.DictReader(handle)]
            except UnicodeDecodeError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    if suffix == ".jsonl":
        with source.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    if suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, Mapping)]
        if isinstance(payload, Mapping):
            records = payload.get("records")
            if isinstance(records, list):
                return [dict(row) for row in records if isinstance(row, Mapping)]
            return [dict(row) for row in extract_records(payload)]
        raise ValueError("JSON input must contain records")

    raise ValueError(f"Unsupported input format: {suffix or '<none>'}")


def file_sha256(path: str | Path) -> str:
    """Return a streaming SHA-256 digest for source provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
