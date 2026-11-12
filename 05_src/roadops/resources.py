"""Validate RoadOps patrol-resource and operator-constraint inputs.

팀·차량·근무시간·장비·고정·제외 조건을 결정적 자원 모델로 정규화합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from roadops.spatial import normalize_link_id


RESOURCE_SCHEMA_VERSION = 1
ALLOWED_HORIZONS = {0, 1, 3, 6}


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _string_set(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_text(item) for item in value if _text(item) is not None})


def _point(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat = _number(latitude)
    lon = _number(longitude)
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _error(errors: list[dict[str, str]], field: str, code: str) -> None:
    errors.append({"field": field, "code": code})


def validate_resource_plan(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize a resource plan and return inspectable validation results."""

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    schema_version = _integer(payload.get("schema_version"))
    if schema_version != RESOURCE_SCHEMA_VERSION:
        _error(errors, "schema_version", "unsupported_schema_version")

    scenario_id = _text(payload.get("scenario_id"))
    if scenario_id is None:
        _error(errors, "scenario_id", "required")

    planning_input = payload.get("planning")
    if not isinstance(planning_input, Mapping):
        planning_input = {}
        _error(errors, "planning", "object_required")
    planning_start = _datetime(planning_input.get("planning_start_at"))
    if planning_start is None:
        _error(errors, "planning.planning_start_at", "timezone_aware_datetime_required")
    horizon = _integer(planning_input.get("horizon_hours"))
    if horizon not in ALLOWED_HORIZONS:
        _error(errors, "planning.horizon_hours", "unsupported_horizon")
    service_minutes = _number(planning_input.get("default_service_minutes"))
    if service_minutes is None or not 0 < service_minutes <= 180:
        _error(errors, "planning.default_service_minutes", "out_of_range")
    average_speed = _number(planning_input.get("baseline_speed_kph"))
    if average_speed is None or not 0 < average_speed <= 120:
        _error(errors, "planning.baseline_speed_kph", "out_of_range")
    max_tasks = _integer(planning_input.get("max_tasks_per_team"))
    if max_tasks is None or not 1 <= max_tasks <= 20:
        _error(errors, "planning.max_tasks_per_team", "out_of_range")
    planning = {
        "planning_start_at": planning_start.isoformat() if planning_start else None,
        "horizon_hours": horizon,
        "default_service_minutes": service_minutes,
        "baseline_speed_kph": average_speed,
        "max_tasks_per_team": max_tasks,
        "distance_semantics": "straight_line_baseline_not_route_time",
    }

    vehicle_inputs = payload.get("vehicles")
    if not isinstance(vehicle_inputs, list) or not vehicle_inputs:
        vehicle_inputs = []
        _error(errors, "vehicles", "non_empty_list_required")
    vehicles: list[dict[str, Any]] = []
    vehicle_ids: set[str] = set()
    for index, source in enumerate(vehicle_inputs):
        field = f"vehicles[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        vehicle_id = _text(source.get("vehicle_id"))
        if vehicle_id is None:
            _error(errors, f"{field}.vehicle_id", "required")
        elif vehicle_id in vehicle_ids:
            _error(errors, f"{field}.vehicle_id", "duplicate")
        else:
            vehicle_ids.add(vehicle_id)
        capacity = _integer(source.get("personnel_capacity"))
        if capacity is None or capacity < 1:
            _error(errors, f"{field}.personnel_capacity", "positive_integer_required")
        status = _text(source.get("status")) or "available"
        if status not in {"available", "unavailable", "maintenance"}:
            _error(errors, f"{field}.status", "unsupported_status")
        vehicles.append(
            {
                "vehicle_id": vehicle_id,
                "vehicle_type": _text(source.get("vehicle_type")) or "patrol_car",
                "personnel_capacity": capacity,
                "status": status,
                "equipment": _string_set(source.get("equipment")),
            }
        )
    vehicle_index = {
        str(vehicle["vehicle_id"]): vehicle
        for vehicle in vehicles
        if vehicle.get("vehicle_id") is not None
    }

    team_inputs = payload.get("teams")
    if not isinstance(team_inputs, list) or not team_inputs:
        team_inputs = []
        _error(errors, "teams", "non_empty_list_required")
    teams: list[dict[str, Any]] = []
    team_ids: set[str] = set()
    assigned_vehicle_ids: set[str] = set()
    for index, source in enumerate(team_inputs):
        field = f"teams[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        team_id = _text(source.get("team_id"))
        if team_id is None:
            _error(errors, f"{field}.team_id", "required")
        elif team_id in team_ids:
            _error(errors, f"{field}.team_id", "duplicate")
        else:
            team_ids.add(team_id)
        personnel = _integer(source.get("personnel_count"))
        if personnel is None or personnel < 1:
            _error(errors, f"{field}.personnel_count", "positive_integer_required")
        vehicle_id = _text(source.get("vehicle_id"))
        vehicle = vehicle_index.get(str(vehicle_id)) if vehicle_id else None
        if vehicle is None:
            _error(errors, f"{field}.vehicle_id", "unknown_vehicle")
        else:
            if vehicle_id in assigned_vehicle_ids:
                _error(errors, f"{field}.vehicle_id", "vehicle_assigned_twice")
            assigned_vehicle_ids.add(str(vehicle_id))
            if vehicle["status"] != "available":
                _error(errors, f"{field}.vehicle_id", "vehicle_not_available")
            if (
                personnel is not None
                and vehicle["personnel_capacity"] is not None
                and personnel > vehicle["personnel_capacity"]
            ):
                _error(errors, f"{field}.personnel_count", "vehicle_capacity_exceeded")
        point = _point(source.get("start_latitude"), source.get("start_longitude"))
        if point is None:
            _error(errors, f"{field}.start", "valid_coordinates_required")
        shift_start = _datetime(source.get("shift_start_at"))
        shift_end = _datetime(source.get("shift_end_at"))
        if shift_start is None:
            _error(errors, f"{field}.shift_start_at", "timezone_aware_datetime_required")
        if shift_end is None:
            _error(errors, f"{field}.shift_end_at", "timezone_aware_datetime_required")
        if shift_start and shift_end and shift_end <= shift_start:
            _error(errors, f"{field}.shift_end_at", "must_follow_shift_start")
        if planning_start and shift_start and shift_end and not (
            shift_start <= planning_start < shift_end
        ):
            _error(errors, field, "planning_start_outside_shift")
        team_equipment = set(_string_set(source.get("equipment")))
        if vehicle is not None:
            team_equipment.update(vehicle["equipment"])
        teams.append(
            {
                "team_id": team_id,
                "team_name": _text(source.get("team_name")) or team_id,
                "personnel_count": personnel,
                "vehicle_id": vehicle_id,
                "start_latitude": point[0] if point else None,
                "start_longitude": point[1] if point else None,
                "shift_start_at": shift_start.isoformat() if shift_start else None,
                "shift_end_at": shift_end.isoformat() if shift_end else None,
                "skills": _string_set(source.get("skills")),
                "equipment": sorted(team_equipment),
            }
        )

    constraints_input = payload.get("constraints")
    if not isinstance(constraints_input, Mapping):
        constraints_input = {}
        _error(errors, "constraints", "object_required")

    def normalize_link_list(name: str) -> list[str]:
        values = constraints_input.get(name, [])
        if not isinstance(values, list):
            _error(errors, f"constraints.{name}", "list_required")
            return []
        normalized: list[str] = []
        for index, raw in enumerate(values):
            link_id = normalize_link_id(raw)
            if link_id is None:
                _error(errors, f"constraints.{name}[{index}]", "valid_link_id_required")
            else:
                normalized.append(link_id)
        if len(normalized) != len(set(normalized)):
            _error(errors, f"constraints.{name}", "duplicate_link_id")
        return sorted(set(normalized))

    mandatory_links = normalize_link_list("mandatory_link_ids")
    excluded_links = normalize_link_list("excluded_link_ids")
    overlap = sorted(set(mandatory_links) & set(excluded_links))
    if overlap:
        _error(errors, "constraints", "mandatory_excluded_conflict")

    fixed_inputs = constraints_input.get("fixed_assignments", [])
    if not isinstance(fixed_inputs, list):
        fixed_inputs = []
        _error(errors, "constraints.fixed_assignments", "list_required")
    fixed_assignments: list[dict[str, str]] = []
    fixed_links: set[str] = set()
    for index, source in enumerate(fixed_inputs):
        field = f"constraints.fixed_assignments[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        team_id = _text(source.get("team_id"))
        link_id = normalize_link_id(source.get("link_id"))
        if team_id not in team_ids:
            _error(errors, f"{field}.team_id", "unknown_team")
        if link_id is None:
            _error(errors, f"{field}.link_id", "valid_link_id_required")
            continue
        if link_id in fixed_links:
            _error(errors, f"{field}.link_id", "fixed_twice")
        if link_id in excluded_links:
            _error(errors, f"{field}.link_id", "fixed_excluded_conflict")
        fixed_links.add(link_id)
        fixed_assignments.append({"team_id": team_id, "link_id": link_id})

    override_inputs = constraints_input.get("task_overrides", [])
    if not isinstance(override_inputs, list):
        override_inputs = []
        _error(errors, "constraints.task_overrides", "list_required")
    task_overrides: list[dict[str, Any]] = []
    override_links: set[str] = set()
    for index, source in enumerate(override_inputs):
        field = f"constraints.task_overrides[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        link_id = normalize_link_id(source.get("link_id"))
        if link_id is None:
            _error(errors, f"{field}.link_id", "valid_link_id_required")
            continue
        if link_id in override_links:
            _error(errors, f"{field}.link_id", "override_twice")
        override_links.add(link_id)
        custom_minutes = source.get("service_minutes")
        normalized_minutes = None
        if custom_minutes not in (None, ""):
            normalized_minutes = _number(custom_minutes)
            if normalized_minutes is None or not 0 < normalized_minutes <= 180:
                _error(errors, f"{field}.service_minutes", "out_of_range")
        task_overrides.append(
            {
                "link_id": link_id,
                "service_minutes": normalized_minutes,
                "required_skills": _string_set(source.get("required_skills")),
                "required_equipment": _string_set(
                    source.get("required_equipment")
                ),
            }
        )

    constraints = {
        "mandatory_link_ids": mandatory_links,
        "excluded_link_ids": excluded_links,
        "fixed_assignments": sorted(
            fixed_assignments, key=lambda row: (str(row["link_id"]), str(row["team_id"]))
        ),
        "task_overrides": sorted(task_overrides, key=lambda row: str(row["link_id"])),
        "duplicate_link_policy": "one_field_task_per_link",
    }
    normalized = {
        "schema_version": RESOURCE_SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "planning": planning,
        "teams": sorted(teams, key=lambda row: str(row.get("team_id"))),
        "vehicles": sorted(vehicles, key=lambda row: str(row.get("vehicle_id"))),
        "constraints": constraints,
    }
    report = {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "scenario_id": scenario_id,
        "team_count": len(teams),
        "vehicle_count": len(vehicles),
        "total_personnel": sum(
            int(team["personnel_count"] or 0) for team in teams
        ),
        "mandatory_link_count": len(mandatory_links),
        "excluded_link_count": len(excluded_links),
        "fixed_assignment_count": len(fixed_assignments),
        "task_override_count": len(task_overrides),
        "errors": errors,
        "warnings": warnings,
    }
    return normalized, report
