#!/usr/bin/env bash
# One-command local dev bootstrap: cleans stale caches, sets up the backend
# venv and frontend node_modules, starts both servers, and opens the UI.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.start-logs"

BACKEND_PORT=8000
FRONTEND_PORT=5173
BACKEND_HEALTH_URL="http://localhost:${BACKEND_PORT}/health"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

mkdir -p "$LOG_DIR"

echo "==> Freeing ports ${BACKEND_PORT} and ${FRONTEND_PORT} if already in use"
lsof -ti:"$BACKEND_PORT" | xargs -r kill -9 2>/dev/null || true
lsof -ti:"$FRONTEND_PORT" | xargs -r kill -9 2>/dev/null || true

echo "==> Cleaning stale caches"
find "$BACKEND_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$BACKEND_DIR/.pytest_cache"
rm -rf "$FRONTEND_DIR/node_modules/.vite"

echo "==> Backend: venv + dependencies"
if [ ! -d "$BACKEND_DIR/venv" ]; then
  python3 -m venv "$BACKEND_DIR/venv"
fi
# shellcheck disable=SC1091
source "$BACKEND_DIR/venv/bin/activate"
pip install -q -r "$BACKEND_DIR/requirements.txt"
deactivate

if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo "warning: backend/.env not found -- copy backend/.env.example and fill in credentials first" >&2
fi

echo "==> Frontend: npm install"
(cd "$FRONTEND_DIR" && npm install --silent)

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "==> Shutting down"
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on :${BACKEND_PORT}"
(
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source venv/bin/activate
  exec uvicorn app.main:app --reload --port "$BACKEND_PORT"
) > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

echo "==> Starting frontend on :${FRONTEND_PORT}"
(cd "$FRONTEND_DIR" && exec npm run dev -- --port "$FRONTEND_PORT") > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

echo "==> Waiting for backend..."
until curl -s -o /dev/null "$BACKEND_HEALTH_URL"; do
  sleep 0.5
done
echo "    backend is up"

echo "==> Waiting for frontend..."
until curl -s -o /dev/null "$FRONTEND_URL"; do
  sleep 0.5
done
echo "    frontend is up"

if command -v open >/dev/null 2>&1; then
  echo "==> Opening ${FRONTEND_URL}"
  open "$FRONTEND_URL"
fi

echo ""
echo "Backend:  ${BACKEND_HEALTH_URL}  (logs: ${LOG_DIR}/backend.log)"
echo "Frontend: ${FRONTEND_URL}  (logs: ${LOG_DIR}/frontend.log)"
echo "Press Ctrl+C to stop both."

wait
