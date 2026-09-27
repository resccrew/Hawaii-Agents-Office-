.PHONY: dev desktop test

# Backend + frontend together, one Ctrl+C stops both. See scripts/dev.sh.
dev:
	@bash scripts/dev.sh

# Full desktop bundle (.app / .dmg on macOS): sidecar -> frontend export ->
# Tauri build. See scripts/build-desktop.sh.
desktop:
	@bash scripts/build-desktop.sh

# Backend pytest + frontend tsc --noEmit. Sets up backend/.venv and
# frontend/node_modules first if either is missing, same as `make dev`.
test:
	@test -x backend/.venv/bin/python || (cd backend && uv venv && uv pip install -e ".[dev]")
	@test -d frontend/node_modules || (cd frontend && npm install)
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run typecheck
