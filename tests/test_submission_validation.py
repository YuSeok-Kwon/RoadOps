from __future__ import annotations

import json
from pathlib import Path

from roadops.submission_validation import (
    forbidden_tracked_paths,
    safe_relative_path,
    scan_files_for_configured_secrets,
    source_tree_digest,
    validate_agent_contract,
    validate_env_example,
    validate_source_manifest,
)


def _contract() -> dict:
    return {
        "contract_id": "test-contract",
        "runtime": {"mode": "deterministic_python_tools_no_external_llm"},
        "prompt_contract": {
            "operator_request_template_ko": (
                "팀 {team_count}개와 차량 {vehicle_count}대로 "
                "{duration_hours}시간 안에 {risk_horizon} 계획"
            )
        },
        "tool_flow": [
            {
                "order": 1,
                "tool_id": "request_interpreter",
                "implementation": "example.request",
            },
            {
                "order": 2,
                "tool_id": "data_quality_gate",
                "implementation": "example.quality",
            },
            {
                "order": 3,
                "tool_id": "risk_task_builder",
                "implementation": "example.tasks",
            },
            {
                "order": 4,
                "tool_id": "travel_time_gate",
                "implementation": "example.travel",
            },
            {
                "order": 5,
                "tool_id": "allocation_optimizer",
                "implementation": "example.optimize",
            },
            {
                "order": 6,
                "tool_id": "plan_validator",
                "implementation": "example.validate",
            },
            {
                "order": 7,
                "tool_id": "result_explainer",
                "implementation": "example.explain",
            },
        ],
        "guardrails": [
            "manual_approval_required",
            "quality_failure_blocks_allocation",
            "constraint_validation_after_optimization",
        ],
        "api_policy": {"cached_demo_requires_api_keys": False},
    }


def test_safe_relative_path_rejects_escape_and_absolute_paths():
    assert safe_relative_path("05_src/roadops/agent_flow.py")
    assert not safe_relative_path("../config/.env")
    assert not safe_relative_path("/absolute/file.py")
    assert not safe_relative_path("")


def test_source_manifest_reports_missing_unsafe_and_duplicate_paths(tmp_path: Path):
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    result = validate_source_manifest(
        tmp_path,
        {
            "manifest_id": "test",
            "required_paths": [
                "README.md",
                "README.md",
                "missing.py",
                "../escape.py",
            ],
        },
    )

    assert result["status"] == "fail"
    assert result["duplicate_paths"] == ["README.md"]
    assert result["missing_paths"] == ["missing.py"]
    assert result["unsafe_paths"] == ["../escape.py"]


def test_agent_contract_validates_tool_order_and_guardrails():
    valid = validate_agent_contract(_contract())
    assert valid["status"] == "pass"
    assert valid["tool_count"] == 7

    invalid_payload = _contract()
    invalid_payload["tool_flow"][1]["order"] = 1
    invalid_payload["guardrails"] = []
    invalid = validate_agent_contract(invalid_payload)

    assert invalid["status"] == "fail"
    assert "tool_order_invalid" in invalid["failures"]
    assert "required_guardrails_missing" in invalid["failures"]


def test_env_example_rejects_values_without_returning_them(tmp_path: Path):
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        "JEJU_CITS_API_KEY=super-secret-value\nTAAS_API_KEY=\n",
        encoding="utf-8",
    )
    result = validate_env_example(
        env_example,
        keys=("JEJU_CITS_API_KEY", "TAAS_API_KEY"),
    )

    assert result["status"] == "fail"
    assert result["nonblank_keys"] == ["JEJU_CITS_API_KEY"]
    assert "super-secret-value" not in json.dumps(result)
    assert result["secret_values_included"] is False


def test_configured_secret_scan_reports_key_name_only(tmp_path: Path):
    source = tmp_path / "source.py"
    source.write_text('TOKEN = "super-secret-value"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "JEJU_CITS_API_KEY=super-secret-value\n", encoding="utf-8"
    )

    result = scan_files_for_configured_secrets(
        tmp_path,
        ["source.py"],
        env_path=env_path,
        keys=("JEJU_CITS_API_KEY",),
        process_environment={},
    )

    assert result == ["JEJU_CITS_API_KEY"]
    assert "super-secret-value" not in json.dumps(result)


def test_forbidden_tracked_paths_cover_secrets_outputs_and_dependencies():
    result = forbidden_tracked_paths(
        [
            "README.md",
            "config/.env",
            ".venv/bin/python",
            "02_outputs/data/result.json",
            "08_dashboard/app/node_modules/a.js",
            "08_dashboard/app/dist/index.html",
            "02_outputs/.gitkeep",
        ]
    )

    assert result == [
        ".venv/bin/python",
        "02_outputs/data/result.json",
        "08_dashboard/app/dist/index.html",
        "08_dashboard/app/node_modules/a.js",
        "config/.env",
    ]


def test_source_tree_digest_is_order_independent(tmp_path: Path):
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")

    first = source_tree_digest(tmp_path, ["a.txt", "b.txt"])
    second = source_tree_digest(tmp_path, ["b.txt", "a.txt"])

    assert first == second
