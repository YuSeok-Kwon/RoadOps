#!/usr/bin/env python3
"""Validate the executable RoadOps source and user-manual submission unit.

제출 소스·프롬프트 계약·Tool·requirements·환경변수 예시·매뉴얼을
하나의 재현 가능한 단위로 검증합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.environment_validation import (  # noqa: E402
    SECRET_ENV_KEYS,
    declared_gpu_dependencies,
    run_command,
    scan_hardcoded_user_paths,
    verify_demo_bundle,
)
from roadops.submission_validation import (  # noqa: E402
    SUBMISSION_VALIDATION_VERSION,
    forbidden_tracked_paths,
    read_json,
    scan_files_for_configured_secrets,
    source_tree_digest,
    validate_agent_contract,
    validate_env_example,
    validate_source_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=PROJECT_ROOT / "config/submission/source_manifest_v0_1.json",
    )
    parser.add_argument(
        "--agent-contract",
        type=Path,
        default=PROJECT_ROOT / "config/agent/roadops_agent_contract_v0_1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "02_outputs/data/submission_source_validation_v0_1",
    )
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _check(
    check_id: str,
    passed: bool,
    *,
    evidence: Any = None,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "pass" if passed else ("fail" if required else "warning"),
        "required": required,
        "evidence": evidence,
    }


def _git_paths(*extra_args: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", *extra_args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return sorted(
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    )


def _filesystem_paths() -> list[str]:
    """Inventory an extracted submission when no Git index is available."""

    paths: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(
            part in {".git", ".pytest_cache", "__pycache__"}
            for part in relative.parts
        ) or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def _load_smoke_result(output_dir: Path) -> dict[str, Any] | None:
    path = output_dir / "agent_result.json"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    args = parse_args()
    source_manifest = read_json(args.source_manifest)
    agent_contract = read_json(args.agent_contract)
    manifest_validation = validate_source_manifest(PROJECT_ROOT, source_manifest)
    contract_validation = validate_agent_contract(agent_contract)
    env_validation = validate_env_example(PROJECT_ROOT / "config/.env.example")
    bundle_validation = verify_demo_bundle(
        PROJECT_ROOT / "demo/cached_inputs_v0_1"
    )

    tracked_paths = _git_paths("--cached")
    candidate_paths = _git_paths("--cached", "--others", "--exclude-standard")
    inventory_mode = "git_index_plus_untracked"
    if not candidate_paths:
        candidate_paths = _filesystem_paths()
        inventory_mode = "extracted_filesystem"
    forbidden_paths = forbidden_tracked_paths(tracked_paths or candidate_paths)
    leaked_secret_keys = scan_files_for_configured_secrets(
        PROJECT_ROOT,
        candidate_paths,
        env_path=PROJECT_ROOT / "config/.env",
        process_environment=os.environ,
    )
    runtime_paths = [
        PROJECT_ROOT / relative
        for relative in candidate_paths
        if relative.startswith(("05_src/", "07_scripts/", "config/agent/"))
    ]
    hardcoded_paths = scan_hardcoded_user_paths(runtime_paths)
    requirements_path = PROJECT_ROOT / "requirements.txt"
    gpu_dependencies = declared_gpu_dependencies(requirements_path)
    required_manual = PROJECT_ROOT / (
        "04_docs/deployment/20261116_roadops_execution_user_manual_v0_1.md"
    )
    posix_launcher = PROJECT_ROOT / "run_demo.sh"
    powershell_launcher = PROJECT_ROOT / "run_demo.ps1"

    checks = [
        _check(
            "source_manifest_valid",
            manifest_validation["status"] == "pass",
            evidence=manifest_validation,
        ),
        _check(
            "agent_prompt_and_tool_contract_valid",
            contract_validation["status"] == "pass",
            evidence=contract_validation,
        ),
        _check(
            "environment_example_has_blank_placeholders",
            env_validation["status"] == "pass",
            evidence=env_validation,
        ),
        _check(
            "local_secret_and_output_paths_not_tracked",
            not forbidden_paths,
            evidence={"forbidden_tracked_paths": forbidden_paths},
        ),
        _check(
            "configured_secret_values_absent_from_submission_candidates",
            not leaked_secret_keys,
            evidence={"matching_secret_key_names": leaked_secret_keys},
        ),
        _check(
            "runtime_has_no_hardcoded_user_paths",
            not hardcoded_paths,
            evidence={"finding_count": len(hardcoded_paths), "findings": hardcoded_paths},
        ),
        _check(
            "cached_demo_bundle_integrity",
            bundle_validation["status"] == "pass",
            evidence=bundle_validation,
        ),
        _check(
            "requirements_declared_without_gpu_runtime",
            requirements_path.is_file() and not gpu_dependencies,
            evidence={
                "requirements": _relative(requirements_path),
                "declared_gpu_dependencies": gpu_dependencies,
            },
        ),
        _check(
            "user_manual_present",
            required_manual.is_file(),
            evidence=_relative(required_manual),
        ),
        _check(
            "posix_launcher_present_and_executable",
            posix_launcher.is_file() and os.access(posix_launcher, os.X_OK),
            evidence=_relative(posix_launcher),
        ),
        _check(
            "powershell_launcher_present",
            powershell_launcher.is_file(),
            evidence=_relative(powershell_launcher),
        ),
    ]

    smoke_runs: list[dict[str, Any]] = []
    if not args.skip_smoke:
        posix_output = args.output_dir / "posix_demo"
        posix_run = run_command(
            "posix_cached_demo_entrypoint",
            [
                str(posix_launcher),
                "--output-dir",
                str(posix_output),
                "--as-of",
                "2026-11-16T18:00:00+09:00",
            ],
            cwd=PROJECT_ROOT,
        )
        smoke_runs.append(posix_run)
        checks.append(
            _check(
                "posix_cached_demo_entrypoint",
                posix_run["status"] == "pass",
                evidence={
                    "duration_seconds": posix_run["duration_seconds"],
                    "return_code": posix_run["return_code"],
                },
            )
        )
        smoke_result = _load_smoke_result(posix_output)
        smoke_contract = (smoke_result or {}).get("agent_contract", {})
        expected_tools = contract_validation.get("tool_ids", [])
        checks.append(
            _check(
                "executed_tool_sequence_matches_contract",
                bool(
                    smoke_result
                    and smoke_result.get("status") in {"pass", "pass_with_limitations"}
                    and smoke_contract.get("execution_status") == "pass"
                    and smoke_contract.get("observed_tool_ids") == expected_tools
                ),
                evidence={
                    "result_status": (smoke_result or {}).get("status"),
                    "contract_id": smoke_contract.get("contract_id"),
                    "observed_tool_ids": smoke_contract.get("observed_tool_ids", []),
                },
            )
        )

        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell:
            powershell_output = args.output_dir / "powershell_demo"
            powershell_run = run_command(
                "powershell_cached_demo_entrypoint",
                [
                    powershell,
                    "-NoProfile",
                    "-File",
                    str(powershell_launcher),
                    "--output-dir",
                    str(powershell_output),
                    "--as-of",
                    "2026-11-16T18:00:00+09:00",
                ],
                cwd=PROJECT_ROOT,
            )
            smoke_runs.append(powershell_run)
            checks.append(
                _check(
                    "powershell_cached_demo_entrypoint_observed",
                    powershell_run["status"] == "pass",
                    evidence={
                        "duration_seconds": powershell_run["duration_seconds"],
                        "return_code": powershell_run["return_code"],
                    },
                )
            )
        else:
            checks.append(
                _check(
                    "powershell_cached_demo_entrypoint_observed",
                    False,
                    evidence="PowerShell was not installed on the observed host.",
                    required=False,
                )
            )

    failures = [
        check["check_id"]
        for check in checks
        if check["required"] and check["status"] == "fail"
    ]
    warnings = [
        check["check_id"] for check in checks if check["status"] == "warning"
    ]
    status = (
        "fail"
        if failures
        else ("pass_with_limitations" if warnings else "pass")
    )
    report = {
        "schema_version": 1,
        "validation_version": SUBMISSION_VALIDATION_VERSION,
        "status": status,
        "source_manifest": _relative(args.source_manifest),
        "agent_contract": _relative(args.agent_contract),
        "candidate_file_count": len(candidate_paths),
        "tracked_file_count": len(tracked_paths),
        "inventory_mode": inventory_mode,
        "candidate_source_sha256": source_tree_digest(
            PROJECT_ROOT, candidate_paths
        ),
        "configured_secret_key_names": [
            key
            for key in SECRET_ENV_KEYS
            if bool(os.environ.get(key))
        ],
        "secret_values_included": False,
        "checks": checks,
        "required_check_count": sum(check["required"] for check in checks),
        "passed_required_check_count": sum(
            check["required"] and check["status"] == "pass" for check in checks
        ),
        "failed_checks": failures,
        "warnings": warnings,
        "smoke_runs": smoke_runs,
        "limitations": [
            "The PowerShell launcher is executed only when PowerShell is installed.",
            "This validates the S2 source unit; S4 will build and re-extract the final ZIP.",
            "The cached demo is a frozen reviewed snapshot, not live road status.",
        ],
    }
    output_path = args.output_dir / "submission_source_validation.json"
    write_json_atomic(output_path, report)
    print(
        json.dumps(
            {
                "status": status,
                "required_check_count": report["required_check_count"],
                "passed_required_check_count": report[
                    "passed_required_check_count"
                ],
                "failed_checks": failures,
                "warnings": warnings,
                "inventory_mode": inventory_mode,
                "candidate_file_count": len(candidate_paths),
                "secret_value_match_count": len(leaked_secret_keys),
                "output": _relative(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
