"""AgentSession registry — Phase 6's core new concept: an "agent" that
exists independently of a Claude Code hook-observed session. Every agent
spawned via the Add-Agent flow (POST /api/v1/agents) gets an entry here,
whether it's a Claude provider (a real resumable `claude -p` session) or a
generative provider (image/video — no persistent session, just a job
history). This is deliberately a separate registry from
EventProcessor.state_machines: that one is keyed by Claude Code's own
session_id (hook-observed), this one is keyed by our own agent_id and is
the source of truth for "which provider, which workspace, how do I talk
to this thing again" — the two are linked via AgentSession.session_id for
claude-provider agents (the STATE MACHINE'S session_id IS the claude
session_id, so an agent's chat goes through the exact same
/ws/chat/{session_id} + ChatBridge as a hook-observed session).
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

AGENT_WORKSPACES_ROOT = Path.home() / "studio-ops" / "agent-workspaces"
MCP_SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp" / "studio_ops_mcp.py"
BACKEND_URL = "http://localhost:8010"
# Bugfix: registry was in-memory only — any backend restart (which happens
# routinely during development, and will happen on any deploy/crash) lost
# every spawned agent's identity, including mcp_config_path, silently
# breaking chat_bridge.py's MCP-tool wiring for agents that were otherwise
# still perfectly resumable. Minimal JSON snapshot, not a database.
STATE_FILE = Path.home() / "studio-ops" / "state" / "agents.json"


@dataclass
class AgentSession:
    agent_id: str
    provider: str  # "claude" | "nanobanana" | "openai" | ...
    department_id: str
    role: str
    name: str
    status: str = "starting"  # starting | active | error
    # Claude-provider only: the underlying resumable claude session_id and
    # its cwd — same two things ChatBridge/claude_cli_service already need
    # for --resume. For non-conversational (generative) providers this
    # stays None; those don't have a persistent session to resume.
    claude_session_id: str | None = None
    workspace_dir: str | None = None
    mcp_config_path: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None
    # Cost control: every studio agent (the CEO and everyone it hires) runs
    # on a cheaper model at moderate effort by DEFAULT, so autonomous work
    # (spawns + every autopilot-driven turn) burns limits far slower than an
    # ad-hoc chat would. The human can still override per-message from the
    # chat window's model/effort selector — that override wins for that turn.
    model: str = "sonnet"
    effort: str = "medium"
    # Optional sprite/skin override — a DevRole key (e.g. "artist") that
    # determines which character sprite this agent renders with, independent
    # of its functional role. None means "use the role's default sprite".
    sprite: str | None = None
    # Cost/usage running totals — accumulated from every hook event carrying
    # these fields (EventDataBase.input_tokens/output_tokens/cache_*_tokens,
    # see models/events.py) whose session_id resolves to this agent via
    # AgentRegistry.find_by_claude_session. Surfaced on GET /api/v1/agents
    # for the roster's per-agent token/cost badge — real, additive counters,
    # not an estimate.
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


def _write_mcp_config(workspace: Path, agent_id: str) -> str:
    """Writes a per-agent --mcp-config JSON wiring up the studio-ops MCP
    server (studio_ops_mcp.py) with this agent's identity in its env, so
    every tool call it makes (send_message, create_task, ...) is
    attributable. session_id isn't known yet at this point (that's what
    spawn() is about to create) — STUDIO_OPS_AGENT_SESSION_ID is left
    unset here; it's informational only in the MCP tools, not load-bearing.
    """
    config = {
        "mcpServers": {
            "studio-ops": {
                "command": sys.executable,
                "args": [str(MCP_SERVER_SCRIPT)],
                "env": {
                    "STUDIO_OPS_AGENT_ID": agent_id,
                    "STUDIO_OPS_BACKEND_URL": BACKEND_URL,
                },
            }
        }
    }
    path = workspace / "mcp-config.json"
    path.write_text(json.dumps(config, indent=2))
    return str(path)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentSession] = {}
        self._load()

    def create(
        self,
        *,
        provider: str,
        department_id: str,
        role: str,
        name: str,
        sprite: str | None = None,
    ) -> AgentSession:
        agent_id = f"agent-{uuid.uuid4().hex[:12]}"
        workspace = AGENT_WORKSPACES_ROOT / agent_id
        workspace.mkdir(parents=True, exist_ok=True)
        session = AgentSession(
            agent_id=agent_id,
            provider=provider,
            department_id=department_id,
            role=role,
            name=name,
            sprite=sprite,
            workspace_dir=str(workspace),
        )
        if provider == "claude":
            session.mcp_config_path = _write_mcp_config(workspace, agent_id)
        self._agents[agent_id] = session
        self.save()
        return session

    def get(self, agent_id: str) -> AgentSession | None:
        return self._agents.get(agent_id)

    def list(self, *, department_id: str | None = None) -> list[AgentSession]:
        values = list(self._agents.values())
        if department_id:
            values = [a for a in values if a.department_id == department_id]
        return values

    def find_by_claude_session(self, claude_session_id: str) -> AgentSession | None:
        for a in self._agents.values():
            if a.claude_session_id == claude_session_id:
                return a
        return None

    def accumulate_tokens(
        self,
        agent_id: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
    ) -> None:
        """Adds one event's token counts onto an agent's running totals.
        Each hook event reports the tokens for that single turn/step, not a
        cumulative total, so this always adds rather than replaces. A
        no-op (not even a save()) when the event carried none of these
        fields, which is the common case for most event types."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return
        if not any(
            v is not None
            for v in (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
        ):
            return
        agent.input_tokens += input_tokens or 0
        agent.output_tokens += output_tokens or 0
        agent.cache_read_tokens += cache_read_tokens or 0
        agent.cache_creation_tokens += cache_creation_tokens or 0
        self.save()

    def remove(self, agent_id: str) -> bool:
        """Drops an agent from the registry. Doesn't kill anything at the OS
        level — a claude-provider agent has no long-lived process (each turn
        is its own `claude -p --resume` subprocess, see
        claude_cli_service.py's module docstring); this just makes the agent
        stop existing as far as /api/v1/agents and future spawns/chat are
        concerned."""
        existed = self._agents.pop(agent_id, None) is not None
        if existed:
            self.save()
        return existed

    def save(self) -> None:
        """Best-effort JSON snapshot — never raises, so a disk hiccup can't
        break a spawn that otherwise succeeded."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = [
                {**asdict(a), "created_at": a.created_at.isoformat()}
                for a in self._agents.values()
            ]
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(STATE_FILE)
        except OSError:
            pass

    def _load(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            raw = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for entry in raw:
            entry = dict(entry)
            entry["created_at"] = datetime.fromisoformat(entry["created_at"])
            session = AgentSession(**entry)
            self._agents[session.agent_id] = session


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
