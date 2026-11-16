#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=$(command -v python)
else
  echo "Python 3.11 or newer is required. / Python 3.11 이상이 필요합니다." >&2
  exit 1
fi

exec "$PYTHON_BIN" \
  "$PROJECT_DIR/07_scripts/20261113_roadops_run_agent_flow_v0_1.py" \
  --strict \
  "$@"
