#!/usr/bin/env python3
"""Installer for Studio Ops hooks — ported from claude-office's manage_hooks.py."""

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

HOOK_TYPES = [
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "PermissionRequest",
    "Notification",
    "Stop",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
]


def get_settings_path() -> Path:
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def load_settings(path: Path) -> dict[str, Any]:
    """A missing file returns {} (fresh install). A file that exists but
    fails to parse is a hard stop — proceeding would overwrite the user's
    real settings.json (permissions, env, model, statusline, and any other
    hooks they already have configured, including claude-office's own)."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"ERROR: {path} exists but is not valid JSON ({e}).\n"
            "Refusing to continue: proceeding would overwrite your settings.\n"
            "Fix or move the file, then re-run install."
        ) from e


def save_settings(path: Path, settings: dict[str, Any]) -> None:
    """Atomic write with a one-time backup, same as claude-office's installer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(".json.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def create_hook_config(hook_cmd: str, hook_type: str) -> dict[str, Any]:
    event_type = convert_camel_to_snake(hook_type)
    config = {
        "type": "command",
        "command": f"{hook_cmd} {event_type}",
        "timeout": 2,
    }
    hook_entry: dict[str, Any] = {"hooks": [config]}
    if hook_type in [
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
        "Notification",
        "SubagentStart",
        "SubagentStop",
    ]:
        hook_entry["matcher"] = ".*"
    return hook_entry


def is_same_hook(entry1: dict[str, Any], entry2: dict[str, Any]) -> bool:
    try:
        cmd1 = entry1.get("hooks", [])[0].get("command")
        cmd2 = entry2.get("hooks", [])[0].get("command")
        return cmd1 == cmd2
    except (IndexError, AttributeError):
        return False


def install_hooks(hook_cmd: str, dry_run: bool = False) -> None:
    settings_path = get_settings_path()
    print(f"Installing hooks to {settings_path}...")

    settings = load_settings(settings_path)
    hooks_config = settings.get("hooks", {})
    changes_made = False

    for hook_type in HOOK_TYPES:
        new_entry = create_hook_config(hook_cmd, hook_type)
        event_type = convert_camel_to_snake(hook_type)
        current_list = hooks_config.get(hook_type, [])

        if any(is_same_hook(existing, new_entry) for existing in current_list):
            print(f"  [Skip] {hook_type}: Hook already exists.")
            continue

        print(f"  [Add]  {hook_type}: {hook_cmd} {event_type}")
        current_list.append(new_entry)
        hooks_config[hook_type] = current_list
        changes_made = True

    if changes_made:
        settings["hooks"] = hooks_config
        if not dry_run:
            save_settings(settings_path, settings)
            print("Settings saved.")
        else:
            print("Dry run: No changes saved.")
    else:
        print("No changes needed.")


def uninstall_hooks(_hook_cmd: str, dry_run: bool = False) -> None:
    del _hook_cmd
    settings_path = get_settings_path()
    print(f"Uninstalling hooks from {settings_path}...")

    settings = load_settings(settings_path)
    hooks_config = settings.get("hooks", {})
    changes_made = False

    for hook_type in list(hooks_config.keys()):
        current_list = hooks_config[hook_type]
        original_len = len(current_list)

        new_list: list[Any] = []
        for entry in current_list:
            try:
                cmd = entry.get("hooks", [])[0].get("command", "")
                if "studio-ops-hook" in cmd:
                    print(f"  [Remove] {hook_type}: {cmd}")
                    continue
            except (IndexError, AttributeError):
                pass
            new_list.append(entry)

        if len(new_list) < original_len:
            hooks_config[hook_type] = new_list
            changes_made = True

        if not hooks_config[hook_type]:
            del hooks_config[hook_type]

    if changes_made:
        settings["hooks"] = hooks_config
        if not dry_run:
            save_settings(settings_path, settings)
            print("Settings saved.")
        else:
            print("Dry run: No changes saved.")
    else:
        print("No hooks found to remove.")


def convert_camel_to_snake(name: str) -> str:
    import re

    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Studio Ops hooks.")
    parser.add_argument("action", choices=["install", "uninstall"], help="Action to perform")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    parser.add_argument("--hook-cmd", help="Path to studio-ops-hook command", required=True)

    args = parser.parse_args()

    if args.action == "install":
        install_hooks(args.hook_cmd, args.dry_run)
    elif args.action == "uninstall":
        uninstall_hooks(args.hook_cmd, args.dry_run)


if __name__ == "__main__":
    main()
