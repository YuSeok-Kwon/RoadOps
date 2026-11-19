#!/usr/bin/env python3
"""Assemble the competition delivery without modifying the working app or raw data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "04_docs/submission_20261120"
APP = Path("08_dashboard/roadops_map_v0_1")
FORBIDDEN = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".DS_Store", ".env"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed_source(path: str) -> bool:
    p = Path(path)
    if any(part in FORBIDDEN for part in p.parts) or p.name.startswith("secrets."):
        return False
    if p.parts[0] in {"05_src", "tests", "demo", "08_dashboard"}:
        return True
    if p.parts[0] == "config":
        return "schedulers" not in p.parts and p.name != ".gitkeep"
    if p.parts[0] == "07_scripts":
        return (p.suffix == ".py" and not any(word in p.name for word in ["presentation", "pptx", "deck_support"])) or p.name == "20261120_roadops_verify_capture_detour.mjs"
    if p.parts[:2] == ("04_docs", "submission_20261120"):
        return True
    if p.parts[:2] == ("04_docs", "deployment"):
        return True
    return path in {"README.md", "requirements.txt", "pyproject.toml", "run_demo.sh", "run_demo.ps1", "AGENTS.md"}


def copy_file(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def mark_submission_snapshot(path: Path):
    """Mark only the delivery metadata; reviewed rows and timestamps stay intact."""
    snapshot = json.loads(path.read_text())
    for row in snapshot["queries"]["map_metadata"]["rows"]:
        row["delivery_mode"] = "submission_snapshot"
        row["automatic_refresh_interval_minutes"] = 0
        row["automatic_refresh_mechanism"] = "static_submission_snapshot"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")


def ensure_delivery_safe(root: Path):
    """Do not ship local credentials, dependencies, symlinks or private config."""
    violations = []
    secret_values = []
    env_file = ROOT / "config/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                value = line.split("=", 1)[1].strip().strip("\"'")
                if len(value) >= 12:
                    secret_values.append(value.encode())
    for file in root.rglob("*"):
        rel = file.relative_to(root)
        if file.is_symlink() or any(part in FORBIDDEN for part in rel.parts):
            violations.append(str(rel))
        if file.is_file() and any(value in file.read_bytes() for value in secret_values):
            violations.append(str(rel) + " (credential match)")
    if violations:
        raise ValueError("Unsafe delivery files: " + ", ".join(violations))


def prepare(args):
    stage = args.output / "RoadOps"
    if stage.exists():
        raise SystemExit(f"Staging directory already exists: {stage}; use --finalize or a new output directory.")
    stage.mkdir(parents=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    # New submission helpers are included before their first commit, too.
    own = [str(p.relative_to(ROOT)) for p in TEMPLATES.rglob("*") if p.is_file()]
    own.append(str(Path(__file__).relative_to(ROOT)))
    own.append("tests/test_submission_package.py")
    for name in sorted(set(tracked + own)):
        if name and allowed_source(name):
            copy_file(ROOT / name, stage / name)
    copy_file(TEMPLATES / "README.md", stage / "README.md")
    for name in ["run_web.py", "START_WEB.cmd", "START_WEB.command", "verify_package.py", "verify_detour.py"]:
        copy_file(TEMPLATES / name, stage / name)
    (stage / "START_WEB.command").chmod(0o755)
    for name in ["run_demo.sh"]:
        (stage / name).chmod(0o755)
    copy_file(TEMPLATES / "launch.html", stage / "web/index.html")
    copy_file(args.proposal, stage / "RoadOps_기획서_권유석.pdf")
    copy_file(args.presentation_snapshot, stage / "demo/presentation_20261119/data.json")
    original_latest_hash = sha256(stage / APP / "src/data.json")
    mark_submission_snapshot(stage / APP / "src/data.json")
    mark_submission_snapshot(stage / "demo/presentation_20261119/data.json")
    for name in ["jeju_nodes.csv", "jeju_links.csv"]:
        copy_file(ROOT / "02_outputs/interim/molit_nodelink_jeju_20261014" / name,
                  stage / "demo/road_network_20261014" / name)
    for name in ["verified-result.json", "independent-verification.json"]:
        copy_file(ROOT / "999_Temporary/roadops_detour_1213_20261120" / name, stage / "evidence" / name)
    for p in (ROOT / "04_docs/content/assets/20261120_roadops_part_8").glob("*.png"):
        copy_file(p, stage / "evidence/screens" / p.name)
    # License notices for the packages used by the UI build and source rebuild.
    modules = ROOT / APP / "node_modules"
    for package in sorted(modules.glob("*/package.json")) + sorted(modules.glob("@*/*/package.json")):
        metadata = json.loads(package.read_text())
        folder = metadata.get("name", package.parent.name).replace("/", "__")
        target = stage / "licenses/npm" / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / "package-info.json").write_text(json.dumps({k: metadata[k] for k in
            ["name", "version", "license", "repository", "author", "homepage"] if k in metadata}, ensure_ascii=False, indent=2))
        for license_file in package.parent.iterdir():
            if license_file.is_file() and license_file.name.lower().startswith(("license", "licence", "notice", "copying")):
                copy_file(license_file, target / license_file.name)
    metadata = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "proposal_sha256": sha256(args.proposal),
        "original_presentation_snapshot_sha256": sha256(args.presentation_snapshot),
        "original_latest_snapshot_sha256": original_latest_hash,
        "presentation_snapshot_sha256": sha256(stage / "demo/presentation_20261119/data.json"),
        "latest_snapshot_sha256": sha256(stage / APP / "src/data.json"),
        "snapshot_policy": "Frozen copies with submission/refresh metadata only. Reviewed data rows and timestamps, and the working app input files, are unchanged.",
        "windows_execution_tested": False, "center_pc_tested": False,
    }
    (stage / "evidence/package-provenance.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(stage)


def finalize(args):
    stage = args.output / "RoadOps"
    for required in ["web/latest/index.html", "web/presentation/index.html", "evidence/validation.json"]:
        if not (stage / required).is_file():
            raise SystemExit(f"Required verified build/evidence missing: {required}")
    if json.loads((stage / "evidence/validation.json").read_text()).get("status") != "pass":
        raise SystemExit("Validation must pass before packaging")
    ensure_delivery_safe(stage)
    files = {str(p.relative_to(stage)).replace(os.sep, "/"): sha256(p)
             for p in sorted(stage.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
    manifest = {
        "package": "RoadOps", "author": "권유석", "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "source_working_tree_note": "The two saved UI asset files are frozen working copies; see package-provenance.json for hashes.",
        "files": files,
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    subprocess.run([os.sys.executable, str(stage / "verify_package.py")], check=True)
    target = args.output / "RoadOps_최종결과물_권유석.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                archive.write(p, "RoadOps/" + str(p.relative_to(stage)).replace(os.sep, "/"))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
    copy_file(stage / "RoadOps_기획서_권유석.pdf", args.output / "RoadOps_기획서_권유석.pdf")
    (args.output / "제출안내.txt").write_text(
        "제출 파일은 다음 두 개입니다.\n1. RoadOps_기획서_권유석.pdf — 15페이지\n"
        "2. RoadOps_최종결과물_권유석.zip — 실행본·소스·매뉴얼·데이터 명세·검증 자료\n\n"
        "갤러리 > 기획서 및 최종 결과물 제출\n마감: 2026-11-20 10:00 (한국시간)\n"
        "ZIP의 RoadOps 폴더 전체를 압축 해제한 뒤 README.md를 읽어 주세요.\n", encoding="utf-8")
    print(json.dumps({"zip": str(target), "bytes": target.stat().st_size, "sha256": sha256(target), "files": len(files) + 1}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--presentation-snapshot", type=Path)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.finalize:
        finalize(args)
    else:
        if not args.proposal or not args.presentation_snapshot:
            parser.error("--proposal and --presentation-snapshot are required for preparation")
        prepare(args)
