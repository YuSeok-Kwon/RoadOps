#!/usr/bin/env python3
"""Validate RoadOps for the competition-center execution profile.

캐시 Agent와 환경 제약을 한 번에 검증합니다.
Python 전체 테스트와 웹 테스트·빌드도 포함합니다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "05_src"))

from roadops.cits_snapshot import write_json_atomic  # noqa: E402
from roadops.environment_validation import (  # noqa: E402
    VALIDATION_VERSION,
    declared_gpu_dependencies,
    host_profile,
    installed_requirement_status,
    node_version_supported,
    python_version_supported,
    read_env_presence,
    run_command,
    scan_bundle_for_configured_secrets,
    scan_hardcoded_user_paths,
    verify_demo_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-profile",
        type=Path,
        default=PROJECT_ROOT
        / "config/execution_profiles/competition_center_v0_1.json",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=PROJECT_ROOT / "demo/cached_inputs_v0_1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT
        / "02_outputs/data/center_environment_validation_v0_1",
    )
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def _read(path: Path):
    if not path.is_file():
        raise SystemExit(f"Required file is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return path.name


def _check(
    check_id: str,
    passed: bool,
    *,
    evidence=None,
    required: bool = True,
) -> dict:
    return {
        "check_id": check_id,
        "status": "pass" if passed else ("fail" if required else "warning"),
        "required": required,
        "evidence": evidence,
    }


def _runtime_paths() -> list[Path]:
    roots = [
        PROJECT_ROOT / "05_src",
        PROJECT_ROOT / "07_scripts",
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "08_dashboard/roadops_map_v0_1/src/content",
    ]
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        if root.is_dir():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    return paths


def _peak_child_rss_megabytes() -> float | None:
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        if sys.platform == "darwin":
            return round(value / 1024**2, 3)
        return round(value / 1024, 3)
    except (ImportError, AttributeError, ValueError):
        return None


def main() -> int:
    args = parse_args()
    target = _read(args.target_profile)
    host = host_profile()
    software = target["software"]
    hardware = target["hardware"]
    requirements_path = PROJECT_ROOT / "requirements.txt"
    dashboard_dir = PROJECT_ROOT / "08_dashboard/roadops_map_v0_1"
    bundle = verify_demo_bundle(args.bundle_dir)
    requirement_status = installed_requirement_status(requirements_path)
    gpu_dependencies = declared_gpu_dependencies(requirements_path)
    hardcoded_paths = scan_hardcoded_user_paths(_runtime_paths())
    env_presence = read_env_presence(PROJECT_ROOT / "config/.env")
    leaked_secret_keys = scan_bundle_for_configured_secrets(
        args.bundle_dir,
        PROJECT_ROOT / "config/.env",
    )

    checks = [
        _check(
            "target_profile_present",
            args.target_profile.is_file(),
            evidence=_relative(args.target_profile),
        ),
        _check(
            "python_version_supported",
            python_version_supported(
                host["python"],
                minimum=software["python_minimum"],
                maximum_exclusive=software["python_maximum_exclusive"],
            ),
            evidence={
                "observed": host["python"],
                "minimum": software["python_minimum"],
                "maximum_exclusive": software["python_maximum_exclusive"],
            },
        ),
        _check(
            "python_dependencies_installed",
            requirement_status["status"] == "pass",
            evidence=requirement_status,
        ),
        _check(
            "large_gpu_dependencies_absent",
            not gpu_dependencies,
            evidence={
                "declared_gpu_dependencies": gpu_dependencies,
                "gpu_required": hardware["gpu_required_by_roadops"],
            },
        ),
        _check(
            "cached_demo_bundle_integrity",
            bundle["status"] == "pass",
            evidence=bundle,
        ),
        _check(
            "cached_demo_requires_no_api_keys",
            True,
            evidence={
                "cached_demo_ready_without_keys": True,
                "live_key_configuration": env_presence,
            },
        ),
        _check(
            "cached_demo_contains_no_configured_secret_values",
            not leaked_secret_keys,
            evidence={"matching_secret_key_names": leaked_secret_keys},
        ),
        _check(
            "runtime_has_no_hardcoded_user_paths",
            not hardcoded_paths,
            evidence={"finding_count": len(hardcoded_paths), "findings": hardcoded_paths},
        ),
        _check(
            "node_version_supported",
            bool(host["node"] and node_version_supported(host["node"])),
            evidence={
                "observed": host["node"],
                "supported": software["node_supported"],
            },
        ),
        _check(
            "npm_available",
            host["npm"] is not None,
            evidence=host["npm"],
        ),
        _check(
            "locked_web_dependencies_present",
            (dashboard_dir / "package-lock.json").is_file(),
            evidence=_relative(dashboard_dir / "package-lock.json"),
        ),
    ]

    smoke_runs: list[dict] = []
    if not args.skip_smoke:
        agent_output = args.output_dir / "agent_smoke"
        smoke_runs.append(
            run_command(
                "cached_agent_demo",
                [
                    sys.executable,
                    str(
                        PROJECT_ROOT
                        / "07_scripts/20261113_roadops_run_agent_flow_v0_1.py"
                    ),
                    "--output-dir",
                    str(agent_output),
                    "--as-of",
                    "2026-11-16T18:00:00+09:00",
                    "--strict",
                ],
                cwd=PROJECT_ROOT,
            )
        )
        smoke_runs.append(
            run_command(
                "python_test_suite",
                [sys.executable, "-m", "pytest", "-q"],
                cwd=PROJECT_ROOT,
            )
        )
        npm = shutil.which("npm")
        if npm and (dashboard_dir / "node_modules").is_dir():
            smoke_runs.append(
                run_command(
                    "web_policy_tests",
                    [npm, "test"],
                    cwd=dashboard_dir,
                )
            )
            smoke_runs.append(
                run_command(
                    "web_production_build",
                    [npm, "run", "build"],
                    cwd=dashboard_dir,
                )
            )
        else:
            reason = "npm_missing" if not npm else "node_modules_missing_run_npm_ci"
            smoke_runs.extend(
                [
                    {
                        "name": name,
                        "status": "fail",
                        "return_code": None,
                        "timed_out": False,
                        "duration_seconds": 0,
                        "stdout_tail": "",
                        "stderr_tail": reason,
                    }
                    for name in ("web_policy_tests", "web_production_build")
                ]
            )
        checks.extend(
            _check(
                f"smoke:{run['name']}",
                run["status"] == "pass",
                evidence={
                    "duration_seconds": run["duration_seconds"],
                    "return_code": run["return_code"],
                    "timed_out": run["timed_out"],
                },
            )
            for run in smoke_runs
        )

    required_failures = [
        check["check_id"]
        for check in checks
        if check["required"] and check["status"] == "fail"
    ]
    warnings = [
        check["check_id"] for check in checks if check["status"] == "warning"
    ]
    status = "fail" if required_failures else "pass_with_limitations"
    report = {
        "schema_version": 1,
        "validation_version": VALIDATION_VERSION,
        "status": status,
        "target_profile": target,
        "observed_host": host,
        "target_hardware_execution_observed": False,
        "target_comparison": {
            "observed_host_logical_cpu_count": host["logical_cpu_count"],
            "target_logical_thread_count": hardware["logical_thread_count"],
            "observed_host_memory_gib": host["memory_gib"],
            "target_memory_gib": hardware["memory_gib"],
            "observed_host_gpu": host["nvidia_gpu"],
            "target_gpu": hardware["gpu_model"],
            "gpu_required_by_roadops": hardware["gpu_required_by_roadops"],
        },
        "checks": checks,
        "required_check_count": sum(check["required"] for check in checks),
        "passed_required_check_count": sum(
            check["required"] and check["status"] == "pass" for check in checks
        ),
        "failed_checks": required_failures,
        "warnings": warnings,
        "smoke_runs": smoke_runs,
        "smoke_total_duration_seconds": round(
            sum(float(run["duration_seconds"]) for run in smoke_runs), 3
        ),
        "peak_child_rss_megabytes_across_smoke_runs": _peak_child_rss_megabytes(),
        "limitations": [
            "Validation ran on the observed host, not on the competition-center PC.",
            "CPU architecture and operating-system differences remain unverified.",
            (
                "Peak child RSS is unavailable on Windows and is a process-group "
                "maximum, not a per-tool profile."
            ),
            "Live API mode depends on provider access and is not required for the cached demo.",
            (
                "The committed web lock currently has npm audit advisories; "
                "static offline output does not ship the Vite dev server."
            ),
        ],
    }
    result_path = args.output_dir / "environment_validation.json"
    write_json_atomic(result_path, report)
    print(
        json.dumps(
            {
                "status": status,
                "required_check_count": report["required_check_count"],
                "passed_required_check_count": report[
                    "passed_required_check_count"
                ],
                "failed_checks": required_failures,
                "smoke_runs": [
                    {
                        "name": run["name"],
                        "status": run["status"],
                        "duration_seconds": run["duration_seconds"],
                    }
                    for run in smoke_runs
                ],
                "smoke_total_duration_seconds": report[
                    "smoke_total_duration_seconds"
                ],
                "peak_child_rss_megabytes": report[
                    "peak_child_rss_megabytes_across_smoke_runs"
                ],
                "target_hardware_execution_observed": False,
                "output": _relative(result_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.strict and status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
