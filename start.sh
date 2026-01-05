#!/usr/bin/env bash
set -euo pipefail

# Start the LocalPortal simulator (Flask) with its local virtualenv.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTAL_DIR="$ROOT_DIR/POC/LocalPortal"
VENV_DIR="$PORTAL_DIR/.venv"
REQ_FILE="$PORTAL_DIR/requirements.txt"
APP_FILE="$PORTAL_DIR/app.py"

if [[ ! -d "$PORTAL_DIR" ]]; then
  echo "ERROR: LocalPortal folder not found at: $PORTAL_DIR" >&2
  exit 1
fi

PY_BIN="python3"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN="python"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Installing requirements from $REQ_FILE"
python -m pip install -r "$REQ_FILE" >/dev/null

echo "Starting Local Portal on http://127.0.0.1:5001"
python "$APP_FILE"
