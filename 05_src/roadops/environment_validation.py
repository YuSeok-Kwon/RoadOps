"""Cross-platform helpers for RoadOps execution-environment validation.

RoadOps 캐시 데모와 실행 환경을 비밀값 노출 없이 점검합니다.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VALIDATION_VERSION = "roadops-center-environment-v0.1"
FORBIDDEN_GPU_PACKAGES = {
    "cuda-python",
    "cupy",
    "tensorflow",
    "torch",
    "transformers",
}
SECRET_ENV_KEYS = (
    "JEJU_CITS_API_KEY",
    "JEJU_ITS_API_KEY",
    "DATA_GO_KR_SERVICE_KEY",
    "TAAS_API_KEY",
)


def parse_version(value: str) -> tuple[int, int, int]:
    """Return a three-part numeric version from command output."""

    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(value))
    if not match:
        raise ValueError(f"Version not found: {value}")
    return tuple(int(part or 0) for part in match.groups())


def python_version_supported(
    value: str,
    *,
    minimum: str,
    maximum_exclusive: str,
) -> bool:
    version = parse_version(value)
    return parse_version(minimum) <= version < parse_version(maximum_exclusive)


def node_version_supported(value: str) -> bool:
    """Match Vite 8's supported Node ranges."""

    version = parse_version(value)
    return (20, 19, 0) <= version < (21, 0, 0) or version >= (22, 12, 0)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_bundle_path(bundle_dir: Path, relative: str) -> Path | None:
    candidate = (bundle_dir / relative).resolve()
    try:
        candidate.relative_to(bundle_dir.resolve())
    except ValueError:
        return None
    return candidate


def verify_demo_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Verify every committed cached-demo file against its manifest hash."""

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return {
            "status": "fail",
            "manifest": str(manifest_path),
            "file_count": 0,
            "failures": ["manifest_missing"],
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "status": "fail",
            "manifest": str(manifest_path),
            "file_count": 0,
            "failures": ["manifest_invalid"],
        }

    failures: list[str] = []
    checked: list[dict[str, Any]] = []
    for item in manifest.get("files", []):
        relative = str(item.get("path") or "")
        path = _safe_bundle_path(bundle_dir, relative)
        if path is None:
            failures.append(f"unsafe_path:{relative}")
            continue
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        actual_bytes = path.stat().st_size
        actual_hash = file_sha256(path)
        bytes_match = actual_bytes == int(item.get("bytes", -1))
        hash_match = actual_hash == item.get("sha256")
        checked.append(
            {
                "path": relative,
                "bytes": actual_bytes,
                "bytes_match": bytes_match,
                "sha256_match": hash_match,
            }
        )
        if not bytes_match:
            failures.append(f"size_mismatch:{relative}")
        if not hash_match:
            failures.append(f"hash_mismatch:{relative}")

    if not checked:
        failures.append("manifest_has_no_files")
    return {
        "status": "pass" if not failures else "fail",
        "manifest": str(manifest_path),
        "demo_version": manifest.get("demo_version"),
        "semantics": manifest.get("semantics"),
        "file_count": len(checked),
        "checked_files": checked,
        "failures": failures,
    }


def parse_requirement_names(path: Path) -> list[str]:
    names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip().lower()
        if name:
            names.append(name)
    return names


def installed_requirement_status(path: Path) -> dict[str, Any]:
    packages = parse_requirement_names(path)
    installed: dict[str, str] = {}
    missing: list[str] = []
    for package in packages:
        try:
            installed[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
    return {
        "status": "pass" if not missing else "fail",
        "required_package_count": len(packages),
        "installed_versions": installed,
        "missing_packages": missing,
        "forbidden_gpu_packages_declared": sorted(
            set(packages) & FORBIDDEN_GPU_PACKAGES
        ),
    }


def declared_gpu_dependencies(path: Path) -> list[str]:
    return sorted(set(parse_requirement_names(path)) & FORBIDDEN_GPU_PACKAGES)


def read_env_presence(path: Path, keys: Sequence[str] = SECRET_ENV_KEYS) -> dict[str, Any]:
    """Return only presence booleans; never return secret values."""

    values: dict[str, bool] = {key: bool(os.environ.get(key)) for key in keys}
    if path.is_file():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in values and value.strip():
                values[key.strip()] = True
    return {
        "configured_key_count": sum(values.values()),
        "expected_key_count": len(values),
        "keys": values,
        "secret_values_included": False,
    }


def scan_bundle_for_configured_secrets(
    bundle_dir: Path,
    env_path: Path,
    keys: Sequence[str] = SECRET_ENV_KEYS,
) -> list[str]:
    """Return matching key names only; secret values never leave this function."""

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
        value = os.environ.get(key, "").strip()
        if len(value) >= 8:
            configured[key] = value

    findings: list[str] = []
    for path in bundle_dir.rglob("*") if bundle_dir.is_dir() else ():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for key, value in configured.items():
            if value in text and key not in findings:
                findings.append(key)
    return sorted(findings)


def scan_hardcoded_user_paths(paths: Iterable[Path]) -> list[dict[str, Any]]:
    patterns = (
        re.compile(r"/Users/[^/\s'\"]+"),
        re.compile(r"/home/[^/\s'\"]+"),
        re.compile(r"[A-Za-z]:\\Users\\[^\\\s'\"]+"),
    )
    findings: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in {
            ".py",
            ".json",
            ".js",
            ".jsx",
            ".mjs",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "re.compile(" in line:
                continue
            if any(pattern.search(line) for pattern in patterns):
                findings.append(
                    {"path": str(path), "line": line_number}
                )
    return findings


def _memory_bytes() -> int | None:
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.total_physical)
        except (AttributeError, OSError):
            return None
    if sys.platform == "darwin":
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            text=True,
            capture_output=True,
            check=False,
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        match = re.search(
            r"^MemTotal:\s+(\d+)\s+kB$",
            meminfo.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        return int(match.group(1)) * 1024 if match else None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * page_count)
    except (AttributeError, OSError, ValueError):
        return None


def command_version(command: str, argument: str = "--version") -> str | None:
    executable = shutil.which(command)
    if executable is None:
        return None
    result = subprocess.run(
        [executable, argument],
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if result.returncode == 0 and output else None


def host_profile() -> dict[str, Any]:
    memory = _memory_bytes()
    nvidia_smi = shutil.which("nvidia-smi")
    gpu = None
    if nvidia_smi:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            gpu = result.stdout.strip().splitlines()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "memory_bytes": memory,
        "memory_gib": round(memory / 1024**3, 3) if memory else None,
        "python": platform.python_version(),
        "node": command_version("node"),
        "npm": command_version("npm"),
        "nvidia_gpu": gpu,
    }


def run_command(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        timed_out = False
    except subprocess.TimeoutExpired as error:
        return_code = None
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        timed_out = True
    duration = time.perf_counter() - started
    return {
        "name": name,
        "command": list(command),
        "status": "pass" if return_code == 0 else "fail",
        "return_code": return_code,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 3),
        "stdout_tail": "\n".join(str(stdout).splitlines()[-12:]),
        "stderr_tail": "\n".join(str(stderr).splitlines()[-12:]),
    }
