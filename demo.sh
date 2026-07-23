#!/usr/bin/env bash
# Clauseline — one-command offline demo launcher (macOS / Linux / Git Bash).
#
#   ./demo.sh
#
# Starts the zero-dependency demo backend (no Docker, no API keys) and the
# Next.js dashboard. Ctrl+C stops both. First run installs frontend deps.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  Clauseline demo — offline, no keys, no Docker"
echo "  ---------------------------------------------"

PY=python3; command -v python3 >/dev/null 2>&1 || PY=python

echo "  [1/3] Starting demo backend on http://localhost:8000 ..."
( cd "$ROOT/backend" && "$PY" demo_server.py ) &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true; echo; echo "  Demo stopped."' EXIT

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "  [2/3] Installing frontend dependencies (first run only, ~1-2 min)..."
  ( cd "$ROOT/frontend" && npm install )
else
  echo "  [2/3] Frontend dependencies already installed."
fi

echo "  [3/3] Starting dashboard on http://localhost:3000 ..."
echo ""
echo "  ==> Open http://localhost:3000/evals when it says 'Ready'."
echo "      Ctrl+C here stops the demo."
echo ""
cd "$ROOT/frontend" && npm run dev
