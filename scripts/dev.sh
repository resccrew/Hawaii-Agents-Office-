#!/usr/bin/env bash
# Runs the backend (uvicorn, :8010) and frontend (next dev, :3010) together —
# the "two terminals" from the README, collapsed into one command. Ctrl+C
# stops both: they're launched in the same process group (no `setsid`/
# subshell wrapping either `&` job), so a single SIGINT from the terminal
# reaches both children directly, and the EXIT trap below mops up whichever
# one is still alive if the other already died on its own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [ ! -x "$BACKEND/.venv/bin/uvicorn" ]; then
    echo "==> backend/.venv missing or incomplete — setting it up (uv venv + uv pip install -e .[dev])"
    (cd "$BACKEND" && uv venv && uv pip install -e ".[dev]")
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
    echo "==> frontend/node_modules missing — running npm install"
    (cd "$FRONTEND" && npm install)
fi

if ! command -v studio-ops-hook >/dev/null 2>&1; then
    echo "==> NOTE: studio-ops-hook isn't on PATH — the office will stay empty until hooks"
    echo "    are installed. See README's 'Hooks' step, or run:"
    echo "      cd hooks && uv tool install --editable . && python manage_hooks.py install --hook-cmd studio-ops-hook"
fi

pids=()
cleanup() {
    trap - EXIT INT TERM
    echo "==> stopping backend + frontend"
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait "${pids[@]}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> starting backend on :8010"
(cd "$BACKEND" && .venv/bin/uvicorn app.main:app --reload --port 8010) &
pids+=("$!")

echo "==> starting frontend on :3010"
(cd "$FRONTEND" && npm run dev) &
pids+=("$!")

echo "==> both running — http://localhost:3010 (Ctrl+C to stop both)"
wait "${pids[@]}"
