"""Validate the reproducible RoadOps submission source without exposing secrets.

제출 소스의 필수 파일·실행 계약·비밀값 미포함을 안전하게 검사합니다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from roadops.environment_validation import SECRET_ENV_KEYS


SUBMISSION_VALIDATION_VERSION = "roadops-submission-source-v0.1"
EXPECTED_AGENT_TOOL_IDS = (
    "request_interpreter",
    "data_quality_gate",
    "risk_task_builder",
    "travel_time_gate",
    "allocation_optimizer",
    "plan_validator",
    "result_explainer",
)
FORBIDDEN_TRACKED_DIRECTORIES = {
    ".venv",
    "02_outputs",
    "999_Temporary",
    "dist",
    "node_modules",
}
TEXT_SUFFIXES = {
    "",
    ".csv",
    ".env",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def safe_relative_path(value: str) -> bool:
    """Return whether a manifest path stays inside the project root."""

    normalized = str(value or "").replace("\\", "/").strip()
    if not normalized:
        return False
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts


def validate_source_manifest(
    project_root: Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate declared submission paths and return only relative evidence."""

    declared = payload.get("required_paths", [])
    if not isinstance(declared, list):
        declared = []
    relative_paths = [str(value) for value in declared]
    unsafe = sorted(path for path in relative_paths if not safe_relative_path(path))
    duplicates = sorted(
        {path for path in relative_paths if relative_paths.count(path) > 1}
    )
    missing = sorted(
        path
        for path in relative_paths
        if safe_relative_path(path) and not (project_root / path).is_file()
    )
    failures: list[str] = []
    if not relative_paths:
        failures.append("required_paths_empty")
    if unsafe:
        failures.append("unsafe_required_paths")
    if duplicates:
        failures.append("duplicate_required_paths")
    if missing:
        failures.append("required_paths_missing")
    return {
        "status": "pass" if not failures else "fail",
        "manifest_id": payload.get("manifest_id"),
        "required_path_count": len(relative_paths),
        "unsafe_paths": unsafe,
        "duplicate_paths": duplicates,
        "missing_paths": missing,
        "failures": failures,
    }


def validate_agent_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the documented prompt, tool order, and safety contract."""

    failures: list[str] = []
    contract_id = str(payload.get("contract_id") or "").strip()
    runtime = payload.get("runtime")
    prompt = payload.get("prompt_contract")
    tools = payload.get("tool_flow")
    guardrails = payload.get("guardrails")
    api_policy = payload.get("api_policy")

    if not contract_id:
        failures.append("contract_id_missing")
    if not isinstance(runtime, Mapping) or runtime.get("mode") != (
        "deterministic_python_tools_no_external_llm"
    ):
        failures.append("runtime_mode_invalid")
    prompt_template = (
        str(prompt.get("operator_request_template_ko") or "")
        if isinstance(prompt, Mapping)
        else ""
    )
    if not prompt_template.strip():
        failures.append("operator_prompt_missing")
    required_placeholders = {
        "{team_count}",
        "{vehicle_count}",
        "{duration_hours}",
        "{risk_horizon}",
    }
    missing_placeholders = sorted(
        placeholder
        for placeholder in required_placeholders
        if placeholder not in prompt_template
    )
    if missing_placeholders:
        failures.append("operator_prompt_placeholders_missing")

    tool_ids: list[str] = []
    orders: list[int] = []
    if not isinstance(tools, list) or not tools:
        failures.append("tool_flow_missing")
    else:
        for index, item in enumerate(tools, start=1):
            if not isinstance(item, Mapping):
                failures.append(f"tool_invalid:{index}")
                continue
            tool_ids.append(str(item.get("tool_id") or "").strip())
            try:
                orders.append(int(item.get("order")))
            except (TypeError, ValueError):
                orders.append(-1)
            if not str(item.get("implementation") or "").strip():
                failures.append(f"tool_implementation_missing:{index}")
    if tool_ids and (not all(tool_ids) or len(tool_ids) != len(set(tool_ids))):
        failures.append("tool_ids_invalid_or_duplicate")
    if orders and orders != list(range(1, len(orders) + 1)):
        failures.append("tool_order_invalid")
    if tool_ids != list(EXPECTED_AGENT_TOOL_IDS):
        failures.append("roadops_tool_flow_invalid")

    required_guardrails = {
        "manual_approval_required",
        "quality_failure_blocks_allocation",
        "constraint_validation_after_optimization",
    }
    declared_guardrails = (
        {str(value) for value in guardrails}
        if isinstance(guardrails, list)
        else set()
    )
    missing_guardrails = sorted(required_guardrails - declared_guardrails)
    if missing_guardrails:
        failures.append("required_guardrails_missing")
    if not isinstance(api_policy, Mapping) or api_policy.get(
        "cached_demo_requires_api_keys"
    ) is not False:
        failures.append("cached_demo_api_policy_invalid")

    return {
        "status": "pass" if not failures else "fail",
        "contract_id": contract_id or None,
        "runtime_mode": runtime.get("mode") if isinstance(runtime, Mapping) else None,
        "tool_ids": tool_ids,
        "tool_count": len(tool_ids),
        "missing_prompt_placeholders": missing_placeholders,
        "missing_guardrails": missing_guardrails,
        "failures": failures,
    }


def validate_env_example(
    path: Path,
    keys: Sequence[str] = SECRET_ENV_KEYS,
) -> dict[str, Any]:
    """Ensure the committed environment template contains only blank values."""

    entries: dict[str, list[str]] = {}
    if path.is_file():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            entries.setdefault(key.strip(), []).append(value.strip())
    missing = sorted(set(keys) - set(entries))
    duplicates = sorted(key for key, values in entries.items() if len(values) > 1)
    nonblank = sorted(
        key for key, values in entries.items() if any(value for value in values)
    )
    unexpected = sorted(set(entries) - set(keys))
    failures: list[str] = []
    if not path.is_file():
        failures.append("env_example_missing")
    if missing:
        failures.append("required_env_keys_missing")
    if duplicates:
        failures.append("duplicate_env_keys")
    if nonblank:
        failures.append("env_example_contains_values")
    return {
        "status": "pass" if not failures else "fail",
        "expected_key_count": len(keys),
        "declared_key_count": len(entries),
        "missing_keys": missing,
        "duplicate_keys": duplicates,
        "nonblank_keys": nonblank,
        "unexpected_keys": unexpected,
        "secret_values_included": False,
        "failures": failures,
    }


def _configured_secrets(
    env_path: Path,
    keys: Sequence[str],
    process_environment: Mapping[str, str] | None,
) -> dict[str, str]:
    configured: dict[str, str] = {}
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in keys and len(value) >= 8:
                configured[key] = value
    for key in keys:
        value = str((process_environment or {}).get(key) or "").strip()
        if len(value) >= 8:
            configured[key] = value
    return configured


def scan_files_for_configured_secrets(
    project_root: Path,
    relative_paths: Iterable[str],
    *,
    env_path: Path,
    keys: Sequence[str] = SECRET_ENV_KEYS,
    process_environment: Mapping[str, str] | None = None,
) -> list[str]:
    """Return leaked key names only; never return or log credential values."""

    configured = _configured_secrets(env_path, keys, process_environment)
    findings: set[str] = set()
    for relative in relative_paths:
        if not safe_relative_path(relative):
            continue
        path = project_root / relative
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for key, value in configured.items():
            if value in text:
                findings.add(key)
    return sorted(findings)


def forbidden_tracked_paths(relative_paths: Iterable[str]) -> list[str]:
    """Find local outputs, environments, and secrets that must not ship."""

    findings: set[str] = set()
    for raw_path in relative_paths:
        normalized = str(raw_path).replace("\\", "/").strip("/")
        if not normalized:
            continue
        path = PurePosixPath(normalized)
        if path.name == ".gitkeep":
            continue
        if normalized == "config/.env" or any(
            part in FORBIDDEN_TRACKED_DIRECTORIES for part in path.parts
        ):
            findings.add(normalized)
    return sorted(findings)


def source_tree_digest(project_root: Path, relative_paths: Iterable[str]) -> str:
    """Build a stable digest over tracked paths and bytes."""

    digest = hashlib.sha256()
    for relative in sorted(set(relative_paths)):
        if not safe_relative_path(relative):
            continue
        path = project_root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def read_json(path: Path) -> Mapping[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return payload
