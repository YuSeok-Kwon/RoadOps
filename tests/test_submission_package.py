"""Distribution safety and portable manifest verification, independent of the app."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load("submission_pack", "07_scripts/20261120_roadops_package_submission.py")
checker = load("submission_check", "04_docs/submission_20261120/verify_package.py")


def test_private_files_are_not_selected_for_delivery():
    for path in ["config/.env", "config/secrets.json", "config/schedulers/local.plist",
                 "08_dashboard/app/node_modules/lib/index.js", "05_src/__pycache__/x.pyc"]:
        assert not pack.allowed_source(path)
    for path in ["config/.env.example", "05_src/roadops/agent_flow.py",
                 "08_dashboard/roadops_map_v0_1/.openai/hosting.json"]:
        assert pack.allowed_source(path)


def test_delivery_rejects_symlink_and_secret_file(tmp_path):
    (tmp_path / "x").symlink_to(ROOT / "README.md")
    with pytest.raises(ValueError, match="Unsafe"):
        pack.ensure_delivery_safe(tmp_path)
    (tmp_path / "x").unlink()
    (tmp_path / ".env").write_text("TOKEN=example")
    with pytest.raises(ValueError, match="Unsafe"):
        pack.ensure_delivery_safe(tmp_path)


def test_manifest_detects_corruption_and_path_escape(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("original")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"files": {"file.txt": pack.sha256(p)}}))
    checker.verify(tmp_path)
    p.write_text("changed")
    with pytest.raises(SystemExit, match="mismatch"):
        checker.verify(tmp_path)
    manifest.write_text(json.dumps({"files": {"../outside": "0"}}))
    with pytest.raises(SystemExit, match="unsafe"):
        checker.verify(tmp_path)
