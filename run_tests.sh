#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv-test}"
LOG_DIR="${TEST_LOG_DIR:-$ROOT_DIR/.test-results}"
LOG_FILE="$LOG_DIR/pytest.log"

mkdir -p "$LOG_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$ROOT_DIR/requirements.txt" pytest pytest-asyncio

set +e
"$VENV_DIR/bin/python" -m pytest "$ROOT_DIR/tests" -v 2>&1 | tee "$LOG_FILE"
TEST_EXIT=${PIPESTATUS[0]}
set -e
SUMMARY_LINE="$(grep -E '^[0-9]+ passed|^[0-9]+ failed|no tests ran' "$LOG_FILE" | tail -n 1 || true)"

{
  echo "run_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "exit_code=$TEST_EXIT"
  echo "pytest_summary=${SUMMARY_LINE:-unavailable}"
  echo "log_file=$LOG_FILE"
} | tee "$LOG_DIR/summary.txt"

exit "$TEST_EXIT"
