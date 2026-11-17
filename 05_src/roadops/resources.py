"""Validate RoadOps field-resource, governance, and operator-constraint inputs.

팀·차량·근무시간·장비·고정·제외 조건을 결정적 자원 모델로 정규화합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from roadops.spatial import normalize_link_id


RESOURCE_SCHEMA_VERSION = 1
ALLOWED_HORIZONS = {0, 1, 3, 6}
ALLOWED_AGENCY_TYPES = {
    "province",
    "administrative_city",
    "police",
    "fire",
    "disaster_headquarters",
    "other",
}
ALLOWED_HANDOFF_TYPES = {"police", "fire"}
ALLOWED_HANDOFF_LEVELS = {"none", "notify", "coordinate", "transfer"}
ALLOWED_CHANNEL_STATUSES = {"active", "unavailable"}


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


def _boolean(value: Any, *, default: bool | None = None) -> bool | None:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
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


def institutional_eligibility(
    team: Mapping[str, Any], task: Mapping[str, Any]
) -> dict[str, Any]:
    """Return deterministic agency and jurisdiction eligibility for one assignment."""

    reasons: list[str] = []
    if task.get("road_team_dispatch_eligible") is False:
        reasons.append("external_handoff_only")

    task_agency = _text(task.get("managing_agency_id"))
    team_agency = _text(team.get("managing_agency_id"))
    support_agencies = set(_string_set(team.get("support_agency_ids")))
    if task_agency and task_agency not in ({team_agency} | support_agencies):
        reasons.append("managing_agency_not_authorized")

    jurisdiction = _text(task.get("road_jurisdiction"))
    authorized = set(_string_set(team.get("authorized_road_jurisdictions")))
    if jurisdiction and "*" not in authorized and jurisdiction not in authorized:
        reasons.append("road_jurisdiction_not_authorized")

    return {"eligible": not reasons, "reasons": reasons}


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

    governance_input = payload.get("governance")
    governance_enabled = (
        isinstance(governance_input, Mapping)
        and bool(governance_input)
        and governance_input.get("mode") != "legacy_unscoped"
    )
    if not governance_enabled:
        governance_input = {}
        warnings.append(
            {"field": "governance", "code": "legacy_unscoped_governance"}
        )

    agency_inputs = governance_input.get("agencies", [])
    if not isinstance(agency_inputs, list):
        agency_inputs = []
        _error(errors, "governance.agencies", "list_required")
    agencies: list[dict[str, Any]] = []
    agency_ids: set[str] = set()
    agency_type_by_id: dict[str, str] = {}
    for index, source in enumerate(agency_inputs):
        field = f"governance.agencies[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        agency_id = _text(source.get("agency_id"))
        agency_type = _text(source.get("agency_type"))
        if agency_id is None:
            _error(errors, f"{field}.agency_id", "required")
        elif agency_id in agency_ids:
            _error(errors, f"{field}.agency_id", "duplicate")
        else:
            agency_ids.add(agency_id)
        if agency_type not in ALLOWED_AGENCY_TYPES:
            _error(errors, f"{field}.agency_type", "unsupported_agency_type")
        if agency_id and agency_type:
            agency_type_by_id[agency_id] = agency_type
        agencies.append(
            {
                "agency_id": agency_id,
                "agency_name": _text(source.get("agency_name")) or agency_id,
                "agency_type": agency_type,
            }
        )
    if governance_enabled and not agencies:
        _error(errors, "governance.agencies", "non_empty_list_required")

    approver_inputs = governance_input.get("approvers", [])
    if not isinstance(approver_inputs, list):
        approver_inputs = []
        _error(errors, "governance.approvers", "list_required")
    approvers: list[dict[str, Any]] = []
    approver_ids: set[str] = set()
    active_approver_ids: set[str] = set()
    for index, source in enumerate(approver_inputs):
        field = f"governance.approvers[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        approver_id = _text(source.get("approver_id"))
        agency_id = _text(source.get("agency_id"))
        active = _boolean(source.get("active"), default=True)
        if approver_id is None:
            _error(errors, f"{field}.approver_id", "required")
        elif approver_id in approver_ids:
            _error(errors, f"{field}.approver_id", "duplicate")
        else:
            approver_ids.add(approver_id)
        if agency_id not in agency_ids:
            _error(errors, f"{field}.agency_id", "unknown_agency")
        if active is None:
            _error(errors, f"{field}.active", "boolean_required")
        elif active and approver_id:
            active_approver_ids.add(approver_id)
        approvers.append(
            {
                "approver_id": approver_id,
                "agency_id": agency_id,
                "role": _text(source.get("role")),
                "active": active,
            }
        )

    channel_inputs = governance_input.get("handoff_channels", [])
    if not isinstance(channel_inputs, list):
        channel_inputs = []
        _error(errors, "governance.handoff_channels", "list_required")
    handoff_channels: list[dict[str, Any]] = []
    channel_ids: set[str] = set()
    channel_index: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(channel_inputs):
        field = f"governance.handoff_channels[{index}]"
        if not isinstance(source, Mapping):
            _error(errors, field, "object_required")
            continue
        channel_id = _text(source.get("channel_id"))
        handoff_type = _text(source.get("handoff_type"))
        target_agency_id = _text(source.get("target_agency_id"))
        status = _text(source.get("status")) or "active"
        if channel_id is None:
            _error(errors, f"{field}.channel_id", "required")
        elif channel_id in channel_ids:
            _error(errors, f"{field}.channel_id", "duplicate")
        else:
            channel_ids.add(channel_id)
        if handoff_type not in ALLOWED_HANDOFF_TYPES:
            _error(errors, f"{field}.handoff_type", "unsupported_handoff_type")
        if target_agency_id not in agency_ids:
            _error(errors, f"{field}.target_agency_id", "unknown_agency")
        elif handoff_type and agency_type_by_id.get(str(target_agency_id)) != handoff_type:
            _error(errors, f"{field}.target_agency_id", "agency_type_mismatch")
        if status not in ALLOWED_CHANNEL_STATUSES:
            _error(errors, f"{field}.status", "unsupported_status")
        normalized_channel = {
            "channel_id": channel_id,
            "handoff_type": handoff_type,
            "target_agency_id": target_agency_id,
            "status": status,
            "contact_method": _text(source.get("contact_method")) or "operator_defined",
        }
        handoff_channels.append(normalized_channel)
        if channel_id:
            channel_index[channel_id] = normalized_channel

    defaults_input = governance_input.get("defaults", {})
    if not isinstance(defaults_input, Mapping):
        defaults_input = {}
        _error(errors, "governance.defaults", "object_required")
    default_agency_id = _text(defaults_input.get("managing_agency_id"))
    default_jurisdiction = _text(defaults_input.get("road_jurisdiction"))
    default_jurisdiction_basis = _text(defaults_input.get("jurisdiction_basis"))
    approval_required = _boolean(
        defaults_input.get("dispatch_approval_required"), default=governance_enabled
    )
    default_approver_id = _text(defaults_input.get("dispatch_approver_id"))
    if governance_enabled and default_agency_id not in agency_ids:
        _error(errors, "governance.defaults.managing_agency_id", "unknown_agency")
    if governance_enabled and default_jurisdiction is None:
        _error(errors, "governance.defaults.road_jurisdiction", "required")
    if governance_enabled and default_jurisdiction_basis is None:
        _error(errors, "governance.defaults.jurisdiction_basis", "required")
    if approval_required is None:
        _error(errors, "governance.defaults.dispatch_approval_required", "boolean_required")
    if default_approver_id and default_approver_id not in active_approver_ids:
        _error(errors, "governance.defaults.dispatch_approver_id", "unknown_or_inactive_approver")
    if approval_required and default_approver_id is None:
        _error(errors, "governance.defaults.dispatch_approver_id", "unknown_or_inactive_approver")

    defaults: dict[str, Any] = {
        "managing_agency_id": default_agency_id,
        "road_jurisdiction": default_jurisdiction,
        "jurisdiction_basis": default_jurisdiction_basis,
        "dispatch_approval_required": approval_required,
        "dispatch_approver_id": default_approver_id,
    }
    for handoff_type in sorted(ALLOWED_HANDOFF_TYPES):
        level_field = f"{handoff_type}_handoff_level"
        channel_field = f"{handoff_type}_handoff_channel_id"
        level = _text(defaults_input.get(level_field)) or "none"
        channel_id = _text(defaults_input.get(channel_field))
        if level not in ALLOWED_HANDOFF_LEVELS:
            _error(errors, f"governance.defaults.{level_field}", "unsupported_handoff_level")
        if level != "none":
            channel = channel_index.get(str(channel_id)) if channel_id else None
            if channel is None or channel.get("handoff_type") != handoff_type:
                _error(errors, f"governance.defaults.{channel_field}", "valid_handoff_channel_required")
            elif channel.get("status") != "active":
                _error(errors, f"governance.defaults.{channel_field}", "handoff_channel_unavailable")
        defaults[level_field] = level
        defaults[channel_field] = channel_id

    governance = {
        "mode": "institution_aware" if governance_enabled else "legacy_unscoped",
        "agencies": sorted(agencies, key=lambda row: str(row.get("agency_id"))),
        "approvers": sorted(approvers, key=lambda row: str(row.get("approver_id"))),
        "handoff_channels": sorted(
            handoff_channels, key=lambda row: str(row.get("channel_id"))
        ),
        "defaults": defaults,
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
        managing_agency_id = _text(source.get("managing_agency_id"))
        support_agency_ids = _string_set(source.get("support_agency_ids"))
        authorized_jurisdictions = _string_set(
            source.get("authorized_road_jurisdictions")
        )
        if governance_enabled:
            if managing_agency_id not in agency_ids:
                _error(errors, f"{field}.managing_agency_id", "unknown_agency")
            for agency_id in support_agency_ids:
                if agency_id not in agency_ids:
                    _error(errors, f"{field}.support_agency_ids", "unknown_agency")
            if not authorized_jurisdictions:
                _error(
                    errors,
                    f"{field}.authorized_road_jurisdictions",
                    "non_empty_list_required",
                )
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
                "managing_agency_id": managing_agency_id,
                "support_agency_ids": support_agency_ids,
                "authorized_road_jurisdictions": authorized_jurisdictions,
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
        managing_agency_id = _text(source.get("managing_agency_id"))
        road_jurisdiction = _text(source.get("road_jurisdiction"))
        jurisdiction_basis = _text(source.get("jurisdiction_basis"))
        dispatch_approval_required = (
            _boolean(source.get("dispatch_approval_required"))
            if "dispatch_approval_required" in source
            else None
        )
        dispatch_approver_id = _text(source.get("dispatch_approver_id"))
        if managing_agency_id and managing_agency_id not in agency_ids:
            _error(errors, f"{field}.managing_agency_id", "unknown_agency")
        if "dispatch_approval_required" in source and dispatch_approval_required is None:
            _error(errors, f"{field}.dispatch_approval_required", "boolean_required")
        if dispatch_approver_id and dispatch_approver_id not in active_approver_ids:
            _error(errors, f"{field}.dispatch_approver_id", "unknown_or_inactive_approver")
        effective_approval_required = (
            approval_required
            if dispatch_approval_required is None
            else dispatch_approval_required
        )
        effective_approver_id = dispatch_approver_id or default_approver_id
        if effective_approval_required and effective_approver_id not in active_approver_ids:
            _error(errors, f"{field}.dispatch_approver_id", "unknown_or_inactive_approver")

        handoff_values: dict[str, Any] = {}
        for handoff_type in sorted(ALLOWED_HANDOFF_TYPES):
            level_field = f"{handoff_type}_handoff_level"
            channel_field = f"{handoff_type}_handoff_channel_id"
            level = _text(source.get(level_field))
            channel_id = _text(source.get(channel_field))
            if level and level not in ALLOWED_HANDOFF_LEVELS:
                _error(errors, f"{field}.{level_field}", "unsupported_handoff_level")
            effective_level = level or str(defaults.get(level_field) or "none")
            effective_channel_id = channel_id or defaults.get(channel_field)
            if effective_level != "none":
                channel = (
                    channel_index.get(str(effective_channel_id))
                    if effective_channel_id
                    else None
                )
                if channel is None or channel.get("handoff_type") != handoff_type:
                    _error(errors, f"{field}.{channel_field}", "valid_handoff_channel_required")
                elif channel.get("status") != "active":
                    _error(errors, f"{field}.{channel_field}", "handoff_channel_unavailable")
            handoff_values[level_field] = level
            handoff_values[channel_field] = channel_id
        task_overrides.append(
            {
                "link_id": link_id,
                "service_minutes": normalized_minutes,
                "required_skills": _string_set(source.get("required_skills")),
                "required_equipment": _string_set(
                    source.get("required_equipment")
                ),
                "managing_agency_id": managing_agency_id,
                "road_jurisdiction": road_jurisdiction,
                "jurisdiction_basis": jurisdiction_basis,
                "dispatch_approval_required": dispatch_approval_required,
                "dispatch_approver_id": dispatch_approver_id,
                **handoff_values,
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
        "governance": governance,
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
        "governance_mode": governance["mode"],
        "agency_count": len(agencies),
        "approver_count": len(approvers),
        "handoff_channel_count": len(handoff_channels),
        "errors": errors,
        "warnings": warnings,
    }
    return normalized, report
