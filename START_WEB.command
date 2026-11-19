#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 run_web.py
fi
echo "Python 3.11 or newer is required. Install Python, then retry."
read -r unused
