"""Event mapping logic for the Studio Ops hooks.

Ported from claude-office's hooks/src/claude_office_hooks/event_mapper.py.
Maps raw Claude Code hook payloads (received on stdin as JSON) to the
Event schema studio-ops's backend/app/models/events.py expects. The event
type names (session_start, pre_tool_use, subagent_start, ...) are identical
to claude-office's — that schema was ported as-is (theme-independent) — so
this mapper needed no renaming of event types, only the package path.

Fields this emits that studio-ops's Pydantic models don't declare (e.g. the
raw tool_response "result" list) are silently dropped by `extra="ignore"`
on EventDataBase, not rejected — so this can stay a close port rather than
a field-by-field rewrite.

IMPORTANT: This module must not produce any stdout/stderr output.
"""

import os
import re
from pathlib import Path
from typing import Any, cast

from studio_ops_hooks.config import STRIP_PREFIXES
from studio_ops_hooks.debug_logger import get_iso_timestamp

try:
    import defusedxml.ElementTree as ET  # noqa: N817

    _HAS_DEFUSEDXML = True
except ImportError:  # pragma: no cover - defusedxml is a declared dependency
    _HAS_DEFUSEDXML = False


def get_project_name(raw_data: dict[str, Any], strip_prefixes: list[str] | None = None) -> str:
    """Derive a human-readable project name from the Claude transcript path."""
    transcript_path = raw_data.get("transcript_path", "")

    if transcript_path:
        path_obj = Path(transcript_path).expanduser()
        parts = path_obj.parts

        try:
            projects_index = parts.index("projects")
            if projects_index + 1 < len(parts):
                raw_project_name = parts[projects_index + 1]

                project_name = raw_project_name
                prefixes = strip_prefixes or STRIP_PREFIXES
                if prefixes:
                    sorted_prefixes: list[str] = sorted(prefixes, key=len, reverse=True)
                    for prefix in sorted_prefixes:
                        if project_name.startswith(prefix):
                            project_name = project_name[len(prefix) :]
                            break

                return project_name
        except (ValueError, IndexError):
            pass

    cwd = raw_data.get("cwd", "")
    if cwd:
        return Path(cwd).name

    return "unknown"


def _build_agent_transcript_path(main_transcript: str | None, native_agent_id: str) -> str | None:
    if not main_transcript:
        return None
    session_dir = main_transcript.rsplit(".jsonl", 1)[0]
    return f"{session_dir}/subagents/agent-{native_agent_id}.jsonl"


def _handle_session_start(raw_data: dict[str, Any], data: dict[str, Any]) -> None:
    source = raw_data.get("source", "unknown")
    data["summary"] = f"Session started ({source})"


def _handle_pre_compact(payload: dict[str, Any], data: dict[str, Any]) -> None:
    payload["event_type"] = "context_compaction"
    data["summary"] = "Context window compacting"


def _handle_pre_tool_use(
    raw_data: dict[str, Any],
    payload: dict[str, Any],
    data: dict[str, Any],
    transcript_path: str | None,
) -> None:
    data["tool_name"] = raw_data.get("tool_name")
    data["tool_input"] = raw_data.get("tool_input")

    if data["tool_name"] in ("Task", "Agent"):
        payload["event_type"] = "subagent_start"
        data["agent_id"] = f"subagent_{data.get('tool_use_id', 'unknown')}"
        tool_input_raw = raw_data.get("tool_input", {})
        if isinstance(tool_input_raw, dict):
            tool_input = cast(dict[str, Any], tool_input_raw)
            description: str = tool_input.get("description", "")
            prompt: str = tool_input.get("prompt", "")
            agent_type: str = tool_input.get("subagent_type", "")
            if description:
                data["agent_name"] = description
            data["task_description"] = prompt if prompt else description
            if agent_type:
                data["agent_type"] = agent_type
        else:
            data["task_description"] = str(tool_input_raw) if tool_input_raw else ""
        data.pop("tool_input", None)
    else:
        data["agent_id"] = "main"


def _handle_post_tool_use(
    raw_data: dict[str, Any],
    payload: dict[str, Any],
    data: dict[str, Any],
    transcript_path: str | None,
) -> None:
    data["tool_name"] = raw_data.get("tool_name")
    data["tool_input"] = raw_data.get("tool_input")
    data["success"] = True  # PostToolUse only fires on success

    if data["tool_name"] in ("Task", "Agent"):
        tool_input_raw = raw_data.get("tool_input", {})
        is_background = False
        if isinstance(tool_input_raw, dict):
            tool_input = cast(dict[str, Any], tool_input_raw)
            is_background = bool(tool_input.get("run_in_background"))

        tool_response_raw = raw_data.get("tool_response", {})
        has_async_agent_id = False
        if isinstance(tool_response_raw, dict):
            tool_response = cast(dict[str, Any], tool_response_raw)
            has_async_agent_id = bool(tool_response.get("agentId"))

        if is_background or has_async_agent_id:
            # Background/async agent — native SubagentStop handles completion.
            data["agent_id"] = "main"
            if has_async_agent_id and isinstance(tool_response_raw, dict):
                native_agent_id = cast(dict[str, Any], tool_response_raw).get("agentId")
                data["native_agent_id"] = native_agent_id
                if native_agent_id:
                    agent_path = _build_agent_transcript_path(
                        data.get("transcript_path") or transcript_path, native_agent_id
                    )
                    if agent_path:
                        data["agent_transcript_path"] = agent_path
        else:
            payload["event_type"] = "subagent_stop"
            data["agent_id"] = f"subagent_{data.get('tool_use_id', 'unknown')}"
            if isinstance(tool_response_raw, dict):
                tool_response = cast(dict[str, Any], tool_response_raw)
                native_agent_id: str | None = tool_response.get("agentId")
                data["native_agent_id"] = native_agent_id
                if native_agent_id:
                    agent_path = _build_agent_transcript_path(
                        data.get("transcript_path") or transcript_path, native_agent_id
                    )
                    if agent_path:
                        data["agent_transcript_path"] = agent_path
    else:
        data["agent_id"] = "main"


def _handle_native_subagent_start(
    raw_data: dict[str, Any],
    payload: dict[str, Any],
    data: dict[str, Any],
    transcript_path: str | None,
) -> dict[str, Any] | None:
    native_agent_id = raw_data.get("agent_id")
    if not native_agent_id:
        return None

    payload["event_type"] = "subagent_info"
    data["native_agent_id"] = native_agent_id
    data["agent_type"] = raw_data.get("agent_type")

    agent_path = _build_agent_transcript_path(
        data.get("transcript_path") or transcript_path, native_agent_id
    )
    if agent_path:
        data["agent_transcript_path"] = agent_path

    return payload


def _handle_native_subagent_stop(
    raw_data: dict[str, Any],
    data: dict[str, Any],
    transcript_path: str | None,
) -> dict[str, Any] | None:
    native_agent_id = raw_data.get("agent_id")
    if not native_agent_id:
        return None

    data["native_agent_id"] = native_agent_id
    agent_transcript = raw_data.get("agent_transcript_path")
    if agent_transcript:
        data["agent_transcript_path"] = agent_transcript
    else:
        agent_path = _build_agent_transcript_path(transcript_path, native_agent_id)
        if agent_path:
            data["agent_transcript_path"] = agent_path

    return data


def _handle_user_prompt_submit(
    raw_data: dict[str, Any],
    payload: dict[str, Any],
    data: dict[str, Any],
) -> None:
    prompt = raw_data.get("prompt", "")

    if _HAS_DEFUSEDXML:
        task_notification_pattern = r"<task-notification>(.*?)</task-notification>"
        match = re.search(task_notification_pattern, prompt, re.DOTALL)
        if match:
            try:
                xml_content = match.group(0)
                root = ET.fromstring(xml_content)
                task_id = root.findtext("task-id", "")
                output_file = root.findtext("output-file", "")
                status = root.findtext("status", "completed")
                summary_text = root.findtext("summary", "")

                payload["event_type"] = "background_task_notification"
                data["background_task_id"] = task_id
                data["background_task_output_file"] = output_file
                data["background_task_status"] = status
                data["background_task_summary"] = summary_text
                data["summary"] = f"Background task {task_id[:8]}... {status}"
                return
            except ET.ParseError:
                pass

    if len(prompt) > 50:
        prompt = prompt[:47] + "..."
    data["prompt"] = prompt
    data["summary"] = f"User: {prompt}" if prompt else "User submitted prompt"


def _handle_permission_request(raw_data: dict[str, Any], data: dict[str, Any]) -> None:
    data["tool_name"] = raw_data.get("tool_name")
    data["tool_input"] = raw_data.get("tool_input")
    data["agent_id"] = "main"


def _handle_notification(raw_data: dict[str, Any], data: dict[str, Any]) -> None:
    data["notification_type"] = raw_data.get("type")
    data["message"] = raw_data.get("message")


def _handle_session_end(raw_data: dict[str, Any], data: dict[str, Any]) -> None:
    data["reason"] = raw_data.get("reason")


def map_event(
    event_type: str,
    raw_data: dict[str, Any],
    session_id: str,
    strip_prefixes: list[str] | None = None,
) -> dict[str, Any] | None:
    """Map raw Claude Code hook data to the studio-ops backend Event model.
    Returns a dict ready to POST, or None if the event should be skipped."""
    actual_session_id = raw_data.get("session_id") or session_id or "unknown_session"
    project_name = get_project_name(raw_data, strip_prefixes)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    working_dir = raw_data.get("cwd", "")
    transcript_path: str | None = raw_data.get("transcript_path")

    data: dict[str, Any] = {
        "project_name": project_name,
        "project_dir": project_dir,
        "working_dir": working_dir,
        "transcript_path": transcript_path,
    }

    if "tool_use_id" in raw_data:
        data["tool_use_id"] = raw_data["tool_use_id"]

    task_list_id = os.environ.get("CLAUDE_CODE_TASK_LIST_ID")
    if task_list_id:
        data["task_list_id"] = task_list_id

    payload: dict[str, Any] = {
        "event_type": event_type,
        "session_id": actual_session_id,
        "timestamp": get_iso_timestamp(),
        "data": data,
    }

    if event_type == "session_start":
        _handle_session_start(raw_data, data)
    elif event_type == "pre_compact":
        _handle_pre_compact(payload, data)
    elif event_type == "pre_tool_use":
        _handle_pre_tool_use(raw_data, payload, data, transcript_path)
    elif event_type == "post_tool_use":
        _handle_post_tool_use(raw_data, payload, data, transcript_path)
    elif event_type == "subagent_start":
        result = _handle_native_subagent_start(raw_data, payload, data, transcript_path)
        if result is None:
            return None
    elif event_type == "subagent_stop":
        result = _handle_native_subagent_stop(raw_data, data, transcript_path)
        if result is None:
            return None
    elif event_type == "user_prompt_submit":
        _handle_user_prompt_submit(raw_data, payload, data)
    elif event_type == "permission_request":
        _handle_permission_request(raw_data, data)
    elif event_type == "notification":
        _handle_notification(raw_data, data)
    elif event_type == "stop":
        pass
    elif event_type == "session_end":
        _handle_session_end(raw_data, data)
    else:
        return None

    return payload
