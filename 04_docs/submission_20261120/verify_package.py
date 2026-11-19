#!/usr/bin/env python3
"""Verify all immutable submitted files. Generated outputs are ignored."""
import hashlib
import json
from pathlib import Path


def verify(root):
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    errors = []
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(name + ": missing or unsafe path")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(name + ": hash mismatch")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(manifest['files'])} file hashes match the submission manifest.")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parent)
