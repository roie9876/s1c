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

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python not found at: $VENV_PY" >&2
  exit 1
fi

echo "Installing requirements from $REQ_FILE"
"$VENV_PY" -m pip install -U pip
"$VENV_PY" -m pip install -r "$REQ_FILE"

# Friendly config warning for the OIDC PoC.
ENV_FILE="$PORTAL_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set +u
  source "$ENV_FILE"
  set -u
fi

if [[ -z "${KEYCLOAK_CLIENT_ID:-}" || -z "${KEYCLOAK_CLIENT_SECRET:-}" ]]; then
  echo "" >&2
  echo "WARNING: Keycloak OIDC not configured yet." >&2
  echo "- Set KEYCLOAK_CLIENT_ID and KEYCLOAK_CLIENT_SECRET in: $ENV_FILE" >&2
  echo "- Realm: master (PoC)" >&2
  echo "- Redirect URI must include: http://localhost:5001/auth/callback" >&2
  echo "Without this, /login will return HTTP 500." >&2
  echo "" >&2
fi

echo "Starting Local Portal on http://127.0.0.1:5001"
"$VENV_PY" "$APP_FILE"
