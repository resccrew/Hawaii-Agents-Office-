#!/usr/bin/env python3
"""
Studio Ops Hooks - Event handler for Claude Code lifecycle events.

Ported from claude-office's hooks/src/claude_office_hooks/main.py, package
path renamed only — the reliability discipline is load-bearing and kept
verbatim:

CRITICAL: This hook must NEVER interfere with Claude Code:
- Never print to stdout (would inject context into Claude's conversation)
- Never print to stderr (would show errors to user)
- Always exit 0 (non-zero blocks Claude actions)

All output is suppressed and errors are logged to the debug file.
"""

import io
import sys

sys.stdout = io.StringIO()
sys.stderr = io.StringIO()

from studio_ops_hooks.debug_logger import log_error  # noqa: E402

try:
    import argparse
    import json
    import os
    import urllib.request
    from typing import Any, cast

    from studio_ops_hooks.config import API_URL, TIMEOUT, get_api_key, load_config
    from studio_ops_hooks.debug_logger import debug_log
    from studio_ops_hooks.event_mapper import map_event

    try:
        from importlib.metadata import version as _pkg_version

        __version__ = _pkg_version("studio-ops-hooks")
    except Exception:
        __version__ = "0.0.0+unknown"

    _config = load_config()
    DEBUG = _config.get("STUDIO_OPS_DEBUG", "0") == "1"

    def _open_request(req: "urllib.request.Request") -> Any:
        """Open *req* without creating an SSL context for http URLs — see
        claude-office's identical comment for the Windows OPENSSL_Uplink
        crash this avoids. https URLs keep the standard opener."""
        if API_URL.lower().startswith("https"):
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        opener = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.ProxyHandler(),
            urllib.request.HTTPHandler(),
            urllib.request.HTTPDefaultErrorHandler(),
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPErrorProcessor(),
        ):
            opener.add_handler(handler)
        return opener.open(req, timeout=TIMEOUT)

    def send_event(payload: dict[str, Any]) -> None:
        """POST *payload* as JSON to the backend API. Silently ignores all
        errors so the hook never blocks Claude."""
        try:
            json_data = json.dumps(payload).encode("utf-8")
            headers: dict[str, str] = {"Content-Type": "application/json"}
            api_key = get_api_key()
            if api_key:
                headers["X-API-Key"] = api_key
            req = urllib.request.Request(API_URL, data=json_data, headers=headers)
            with _open_request(req) as response:
                if response.status >= 300:
                    log_error(RuntimeError(f"backend returned HTTP {response.status}"), "send_event")
        except Exception as exc:
            log_error(exc, "send_event failed")

    def main() -> None:
        if "--version" in sys.argv or "-V" in sys.argv:
            real_stdout = sys.__stdout__
            if real_stdout is not None:
                real_stdout.write(f"studio-ops-hook {__version__}\n")
                real_stdout.flush()
            sys.exit(0)

        parser = argparse.ArgumentParser(description="Studio Ops hook event handler")
        parser.add_argument(
            "event_type", nargs="?", help="The type of event (session_start, pre_tool_use, etc.)"
        )
        parser.add_argument(
            "-V", "--version", action="version", version=f"studio-ops-hook {__version__}"
        )
        parser.add_argument(
            "--strip-prefixes",
            type=str,
            default=None,
            help="Comma-separated prefixes to strip from project names.",
        )
        args = parser.parse_args()

        if not args.event_type:
            real_stderr = sys.__stderr__
            if real_stderr is not None:
                real_stderr.write("error: event_type is required\n")
                real_stderr.flush()
            sys.exit(1)

        strip_prefixes: list[str] | None = None
        prefixes_str = (
            args.strip_prefixes
            or os.environ.get("STUDIO_OPS_STRIP_PREFIXES")
            or _config.get("STUDIO_OPS_STRIP_PREFIXES")
        )
        if prefixes_str:
            strip_prefixes = [p.strip() for p in prefixes_str.split(",") if p.strip()]

        raw_data: dict[str, Any] = {}
        try:
            real_stdin = sys.__stdin__
            if (
                real_stdin is not None
                and not real_stdin.closed
                and hasattr(real_stdin, "isatty")
                and not real_stdin.isatty()
            ):
                raw_input = real_stdin.read()
                if raw_input.strip():
                    raw_data = cast(dict[str, Any], json.loads(raw_input))
        except Exception as exc:
            log_error(exc, "stdin read skipped")

        session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
        payload = map_event(args.event_type, raw_data, session_id, strip_prefixes)

        if payload is None:
            if DEBUG:
                debug_log(args.event_type, raw_data, {"skipped": True, "reason": "event returns None"}, enabled=DEBUG)
            return

        debug_log(args.event_type, raw_data, payload, enabled=DEBUG)
        send_event(payload)

    def run() -> None:
        """Entry point for both direct script execution and the installed
        console script (pyproject.toml: studio-ops-hook = "...main:run").

        Deliberately NOT named `main` for the console-script target: pip's
        generated wrapper does `sys.exit(main())` directly, which would
        bypass this try/except and let an uncaught exception inside main()
        propagate as a non-zero exit — silently breaking the "always exit
        0" guarantee the moment this ships as an installed command instead
        of a `python main.py` invocation.
        """
        try:
            main()
        except SystemExit:
            raise
        except Exception as e:
            log_error(e, "Error in main()")
        sys.exit(0)

    if __name__ == "__main__":
        run()

except Exception as e:
    log_error(e, "Error during module initialization")
    sys.exit(0)
