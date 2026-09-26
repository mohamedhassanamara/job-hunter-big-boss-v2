#!/usr/bin/env bash
# Start the FastAPI backend and the Vite frontend together. Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
  echo "Backend venv missing — run 'make setup' first." >&2
  exit 1
fi

cleanup() { trap - INT TERM EXIT; kill 0 2>/dev/null || true; }
trap cleanup INT TERM EXIT

(cd "$ROOT/backend" && .venv/bin/alembic upgrade head >/dev/null && exec .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/frontend" && exec npm run dev -- --port 5173 --strictPort) &

echo "API  → http://localhost:8000/docs"
echo "Web  → http://localhost:5173"
wait
