#!/usr/bin/env python3
"""Run JS calculation and independent Python CSV routing from packaged inputs."""
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    subprocess.run(["node", "07_scripts/20261120_roadops_verify_capture_detour.mjs", "--verify-only"], cwd=root, check=True)
    subprocess.run([sys.executable, "07_scripts/20261120_roadops_check_comparable_detour.py",
        "--network-dir", str(root / "demo/road_network_20261014")], cwd=root, check=True)
