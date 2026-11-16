from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from roadops.environment_validation import (
    node_version_supported,
    parse_requirement_names,
    parse_version,
    python_version_supported,
    read_env_presence,
    scan_bundle_for_configured_secrets,
    scan_hardcoded_user_paths,
    verify_demo_bundle,
)


def test_version_parsing_and_supported_ranges():
    assert parse_version("Python 3.14.3") == (3, 14, 3)
    assert python_version_supported(
        "3.11.9", minimum="3.11", maximum_exclusive="3.15"
    )
    assert not python_version_supported(
        "3.10.14", minimum="3.11", maximum_exclusive="3.15"
    )
    assert node_version_supported("v20.19.0")
    assert not node_version_supported("v21.7.3")
    assert node_version_supported("v22.12.0")


def test_invalid_version_is_rejected():
    with pytest.raises(ValueError, match="Version not found"):
        parse_version("unknown")


def test_requirement_parser_ignores_comments_and_constraints(tmp_path: Path):
    path = tmp_path / "requirements.txt"
    path.write_text("# comment\nhttpx>=0.27,<1\npyshp[extra]==2.3.1\n\n", encoding="utf-8")

    assert parse_requirement_names(path) == ["httpx", "pyshp"]


def test_env_presence_never_returns_secret_values(tmp_path: Path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("JEJU_CITS_API_KEY=very-secret\nTAAS_API_KEY=\n", encoding="utf-8")
    monkeypatch.delenv("JEJU_CITS_API_KEY", raising=False)
    monkeypatch.delenv("TAAS_API_KEY", raising=False)

    result = read_env_presence(path, keys=("JEJU_CITS_API_KEY", "TAAS_API_KEY"))

    assert result["configured_key_count"] == 1
    assert result["keys"] == {"JEJU_CITS_API_KEY": True, "TAAS_API_KEY": False}
    assert "very-secret" not in json.dumps(result)
    assert result["secret_values_included"] is False


def test_bundle_secret_scan_returns_key_name_only(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "payload.json").write_text(
        '{"credential":"very-secret-value"}', encoding="utf-8"
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "JEJU_CITS_API_KEY=very-secret-value\n", encoding="utf-8"
    )
    monkeypatch.delenv("JEJU_CITS_API_KEY", raising=False)

    findings = scan_bundle_for_configured_secrets(
        bundle,
        env_path,
        keys=("JEJU_CITS_API_KEY",),
    )

    assert findings == ["JEJU_CITS_API_KEY"]
    assert "very-secret-value" not in json.dumps(findings)


def _write_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    payload = bundle / "data.json"
    payload.write_text('{"ok":true}\n', encoding="utf-8")
    raw = payload.read_bytes()
    manifest = {
        "demo_version": "test",
        "semantics": "frozen",
        "files": [
            {
                "path": "data.json",
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def test_demo_bundle_hash_validation_detects_tampering(tmp_path: Path):
    bundle = _write_bundle(tmp_path)

    assert verify_demo_bundle(bundle)["status"] == "pass"
    (bundle / "data.json").write_text('{"ok":false}\n', encoding="utf-8")
    result = verify_demo_bundle(bundle)

    assert result["status"] == "fail"
    assert "size_mismatch:data.json" in result["failures"]
    assert "hash_mismatch:data.json" in result["failures"]


def test_demo_bundle_rejects_path_traversal(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../data.json"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_demo_bundle(bundle)

    assert result["status"] == "fail"
    assert "unsafe_path:../data.json" in result["failures"]


def test_hardcoded_user_path_scan_reports_only_locations(tmp_path: Path):
    source = tmp_path / "script.py"
    source.write_text('ROOT = "/Users/example/project"\n', encoding="utf-8")

    findings = scan_hardcoded_user_paths([source])

    assert findings == [{"path": str(source), "line": 1}]
    assert "/Users/example" not in json.dumps(findings)
