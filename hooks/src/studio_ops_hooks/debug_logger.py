"""Debug logging utilities for the Studio Ops hooks.

Ported from claude-office's hooks/src/claude_office_hooks/debug_logger.py.

IMPORTANT: This module must not produce any stdout/stderr output.
Output suppression is handled in main.py before this module is imported.
All diagnostic output goes to DEBUG_LOG_PATH (a file), never stdout/stderr —
writing to either would break Claude Code integration.
"""

import datetime
import json
import re
import traceback
from pathlib import Path
from typing import Any

DEBUG_LOG_PATH = Path.home() / ".claude" / "studio-ops-hooks.log"

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(oauth[_-]?token[\":\s]*[=\"]?\s*)([^\s\"',}]+)", re.IGNORECASE),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(bearer\s+)([^\s]+)", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(sk-[a-zA-Z0-9-]{10,})", re.IGNORECASE), r"[REDACTED]"),
    (
        re.compile(
            r"\"(token|password|secret|api[_-]?key)\"[\":\s]*\"([^\"]+)\"",
            re.IGNORECASE,
        ),
        r'"\1":"[REDACTED]"',
    ),
]


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def get_iso_timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def log_error(error: Exception, context: str = "") -> None:
    """Write an exception with full traceback to the debug log file.
    Never raises — this is the only place errors should be surfaced."""
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = get_iso_timestamp()
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'!' * 60}\n")
            f.write(f"[{timestamp}] ERROR: {context}\n")
            f.write(f"Exception: {type(error).__name__}: {error}\n")
            f.write("Traceback:\n")
            f.write(traceback.format_exc())
            f.write(f"{'!' * 60}\n")
    except Exception:
        pass


def log_notice(message: str, context: str = "") -> None:
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = get_iso_timestamp()
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'-' * 60}\n")
            f.write(f"[{timestamp}] NOTICE: {context}\n")
            f.write(f"{message}\n")
            f.write(f"{'-' * 60}\n")
    except Exception:
        pass


def debug_log(
    event_type: str,
    raw_data: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    enabled: bool,
) -> None:
    if not enabled:
        return
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"[{get_iso_timestamp()}] Event: {event_type}\n")
            f.write("--- RAW INPUT FROM CLAUDE CODE ---\n")
            f.write(_redact(json.dumps(raw_data, indent=2, default=str)))
            f.write("\n--- MAPPED PAYLOAD TO BACKEND ---\n")
            f.write(_redact(json.dumps(payload, indent=2, default=str)))
            f.write(f"\n{'=' * 60}\n")
    except Exception:
        pass
