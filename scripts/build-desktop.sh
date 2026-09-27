#!/usr/bin/env bash
# Builds the desktop app end to end: backend sidecar (PyInstaller) -> frontend
# static export -> Tauri bundle (.app + .dmg on macOS). Previously three
# manual, undocumented steps split across backend/build_sidecar.py and
# tauri.conf.json's externalBin/beforeBuildCommand — this is the "one
# command" version.
#
# Needs on PATH: uv, npm, cargo, and the `cargo tauri` subcommand
# (`cargo install tauri-cli`). Rust/Xcode command line tools are Tauri's own
# prerequisites on macOS, not installed by this script.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

for tool in uv npm cargo; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "error: '$tool' not found on PATH — required to build the desktop app" >&2
        exit 1
    }
done
cargo tauri --version >/dev/null 2>&1 || {
    echo "error: 'cargo tauri' not found — install it with: cargo install tauri-cli" >&2
    exit 1
}

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
    echo "==> backend/.venv missing — setting it up (uv venv + uv pip install -e .[dev])"
    (cd "$BACKEND" && uv venv && uv pip install -e ".[dev]")
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
    echo "==> frontend/node_modules missing — running npm install"
    (cd "$FRONTEND" && npm install)
fi

echo "==> building backend sidecar (PyInstaller)"
(cd "$BACKEND" && .venv/bin/python build_sidecar.py)

echo "==> building Tauri bundle (this also runs 'bun run build' in frontend/ via beforeBuildCommand)"
(cd "$ROOT/src-tauri" && cargo tauri build)

echo "==> done — bundles under src-tauri/target/release/bundle/"
