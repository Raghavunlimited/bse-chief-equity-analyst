#!/usr/bin/env bash
# Personal local desk — binds loopback by default (Phase 7).
# AUTH_ENABLED=false is intentional for single-operator use on this machine only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# Loopback only unless operator explicitly overrides (never use 0.0.0.0 with auth off
# unless ALLOW_PUBLIC_BIND=true — the API will refuse boot otherwise).
export BIND_HOST="${BIND_HOST:-127.0.0.1}"
export UVICORN_HOST="$BIND_HOST"
export ALLOW_PUBLIC_BIND="${ALLOW_PUBLIC_BIND:-false}"

echo "Swing Desk — personal local start"
echo "  BIND_HOST=$BIND_HOST  (loopback recommended when AUTH is off)"
echo "  UI will be http://127.0.0.1:3000  API http://127.0.0.1:8000"
echo "  Not for public network exposure without auth + non-default SECRET_KEY."

if [ ! -d "$BACKEND/venv" ]; then
  echo "Creating Python venv…"
  python3 -m venv "$BACKEND/venv"
  # shellcheck disable=SC1091
  source "$BACKEND/venv/bin/activate"
  pip install -q -r "$BACKEND/requirements.txt"
else
  # shellcheck disable=SC1091
  source "$BACKEND/venv/bin/activate"
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Installing frontend deps…"
  (cd "$FRONTEND" && npm install)
fi

cd "$BACKEND"
if [ ! -f "$BACKEND/data/swing_trader.db" ]; then
  echo "No DB yet — configure KOTAK_CONSUMER_KEY in backend/.env and Force full from the UI."
  echo "Demo/synthetic seed is forbidden. Backup later: ./scripts/backup_sqlite.sh"
fi

# seed_platform.py intentionally refuses (Phase 1) — do not treat as required.
# Platform tables are created on API startup.

uvicorn app.main:app --reload --host "$BIND_HOST" --port 8000 &
BACKEND_PID=$!

cleanup() {
  echo "Stopping…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Waiting for API on 127.0.0.1:8000…"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "API liveness OK."
    break
  fi
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo "API failed to become healthy (check BIND_HOST / .env / logs)."
    exit 1
  fi
done

cd "$FRONTEND"
# HOST=127.0.0.1 alone breaks CRA 5 / webpack-dev-server 4 (empty allowedHosts).
# .env.development + DANGEROUSLY_DISABLE_HOST_CHECK keep loopback without that crash.
BROWSER=none \
  HOST=127.0.0.1 \
  DANGEROUSLY_DISABLE_HOST_CHECK=true \
  WDS_SOCKET_HOST=127.0.0.1 \
  npm start &
FRONTEND_PID=$!

echo ""
echo "UI:  http://127.0.0.1:3000"
echo "API: http://127.0.0.1:8000"
if [ "${ENABLE_API_DOCS:-true}" = "true" ] || [ -z "${ENABLE_API_DOCS:-}" ]; then
  echo "Docs (local only): http://127.0.0.1:8000/docs"
fi
echo "Guide: docs/PERSONAL_USE.md · Ops: docs/OPS.md"
wait
