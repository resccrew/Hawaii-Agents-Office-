#!/bin/bash
set -e

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_CMD="studio-ops-hook"

echo "Uninstalling hooks..."
uv run "$HOOKS_DIR/manage_hooks.py" uninstall --hook-cmd "$HOOK_CMD"

echo "Removing studio-ops-hooks tool..."
uv tool uninstall studio-ops-hooks 2>/dev/null || true

rm -f "$HOME/.claude/studio-ops-config.env"
rm -f "$HOME/.claude/studio-ops-hooks.log"

echo "Done! Hooks removed from configuration."
