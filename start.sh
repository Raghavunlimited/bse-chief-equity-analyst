#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "Swing Desk — starting…"

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
# Seed demo history if the DB is empty (live ingest can be rate-limited)
if [ ! -f "$BACKEND/data/swing_trader.db" ]; then
  echo "No DB yet — seeding demo EOD (replace later with live ingest)…"
  python seed_demo_data.py || true
fi
# Platform users + auditable demo signals (idempotent)
python seed_platform.py || true
echo "Demo logins: customer@swingdesk.local / Customer1!  ·  admin@swingdesk.local / AdminDemo1!"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cleanup() {
  echo "Stopping…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for API health
echo "Waiting for API…"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "API ready."
    break
  fi
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo "API failed to become healthy."
    exit 1
  fi
done

cd "$FRONTEND"
BROWSER=none npm start &
FRONTEND_PID=$!

echo "UI:  http://localhost:3000"
echo "API: http://localhost:8000/docs"
wait
