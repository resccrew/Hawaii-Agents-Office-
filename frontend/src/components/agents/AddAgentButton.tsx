"use client";

import { useState } from "react";
import { useEmojiBurst } from "@/systems/useEmojiBurst";
import { getHttpBase } from "@/systems/backendUrl";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";

const ROLES = [
  { value: "programmer", label: "Programmer" },
  { value: "game_designer", label: "Game Designer" },
  { value: "artist", label: "Artist" },
  { value: "qa_tester", label: "QA Tester" },
  { value: "producer", label: "Producer" },
];

// All available character skins — sprite path must match what's in public/sprites/
const SKINS = [
  { key: "programmer", label: "Coder", path: "/sprites/programmer_front_idle.png" },
  { key: "game_designer", label: "Designer", path: "/sprites/game_designer_front_idle.png" },
  { key: "artist", label: "Artist", path: "/sprites/artist_front_idle.png" },
  { key: "qa_tester", label: "Tester", path: "/sprites/qa_tester_front_idle.png" },
  { key: "producer", label: "Producer", path: "/sprites/producer_front_idle.png" },
];

// Which "brain" powers this agent — matches the backend's provider
// registry (app/services/providers/__init__.py). Claude agents get the
// full studio-ops MCP toolset (spawn/message/task tools); the others chat
// and can be coordinated via chat, but can't yet call those tools
// themselves (see openai_provider.py's docstring) — surfaced via the hint
// text, not hidden, so picking one is an informed choice.
const PROVIDERS = [
  { value: "claude", label: "Claude", hint: "full studio-ops tool access" },
  { value: "openai", label: "OpenAI (GPT)", hint: "chat only — needs STUDIO_OPS_OPENAI_API_KEY" },
  { value: "gemini", label: "Gemini", hint: "chat only — needs STUDIO_OPS_GEMINI_API_KEY" },
  { value: "ollama", label: "Ollama (local)", hint: "chat only — needs a local `ollama serve`" },
];

export const DEPARTMENTS = ["Engineering", "Art", "Design", "QA"];

interface Props {
  onSpawned: (sessionId: string) => void;
  apiBase?: string;
}

// The whole point of Phase 6's Add-Agent flow: no terminal is ever shown.
// This form POSTs to /api/v1/agents, which spawns the chosen provider's
// session invisibly server-side and returns a session_id the moment it's
// ready — from here on, the new agent behaves exactly like any other Dev:
// click it, chat with it via the existing ChatPanel.
export function AddAgentButton({ onSpawned, apiBase = getHttpBase() }: Props) {
  const defaultDepartment = useUiSettingsStore((s) => s.defaultDepartment);
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState(PROVIDERS[0].value);
  const [role, setRole] = useState(ROLES[0].value);
  const [department, setDepartment] = useState(
    DEPARTMENTS.includes(defaultDepartment) ? defaultDepartment : DEPARTMENTS[0],
  );
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  // Skin/sprite selection — defaults to matching the chosen role; user can
  // override to give any agent any character appearance (purely cosmetic).
  const [sprite, setSprite] = useState<string>(ROLES[0].value);
  const [skinLocked, setSkinLocked] = useState(false);
  const [status, setStatus] = useState<"idle" | "spawning" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const { burst, layer } = useEmojiBurst();

  // When role changes, auto-sync the skin UNLESS the user has manually
  // picked a different skin ("locked").
  const handleRoleChange = (newRole: string) => {
    setRole(newRole);
    if (!skinLocked) setSprite(newRole);
  };

  const handleSpriteSelect = (key: string) => {
    setSprite(key);
    // If the user picked the same skin as the current role, reset the lock
    // so future role changes auto-sync again.
    setSkinLocked(key !== role);
  };

  const handleSubmit = async () => {
    if (!prompt.trim()) return;
    setStatus("spawning");
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/v1/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          department_id: department,
          role,
          name: name.trim() || role,
          initial_prompt: prompt,
          // Only send sprite when it differs from the role — backend treats
          // null as "use role's sprite", keeping backward compat.
          sprite: sprite !== role ? sprite : null,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setStatus("idle");
      setOpen(false);
      setPrompt("");
      setName("");
      setSkinLocked(false);
      onSpawned(data.session_id);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!open) {
    return (
      <button
        className="add-agent-fab pixel-frame"
        onClick={() => {
          burst();
          // Delay opening the modal — it replaces this button (and the
          // burst layer riding on it) entirely, so opening immediately cut
          // the animation off before a single frame of it was visible.
          // Long enough to see the pop-and-fly, short enough to still feel
          // like one snappy action.
          window.setTimeout(() => setOpen(true), 350);
        }}
      >
        + agent
        {layer}
      </button>
    );
  }

  const providerHint = PROVIDERS.find((p) => p.value === provider)?.hint;

  return (
    <div className="add-agent-overlay">
    <div className="add-agent-modal pixel-frame">
      <div className="add-agent-header">
        <span>spawn new agent</span>
        <button onClick={() => setOpen(false)}>x</button>
      </div>
      <label>
        brain
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        {providerHint && <span className="add-agent-hint">{providerHint}</span>}
      </label>
      <label>
        role
        <select value={role} onChange={(e) => handleRoleChange(e.target.value)}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <div className="skin-picker-label">
        skin
        {skinLocked && (
          <button
            className="skin-picker-reset"
            type="button"
            onClick={() => { setSprite(role); setSkinLocked(false); }}
            title="Reset to match role"
          >
            reset
          </button>
        )}
      </div>
      <div className="skin-picker">
        {SKINS.map((skin) => (
          <button
            key={skin.key}
            type="button"
            className={`skin-option${sprite === skin.key ? " skin-option-selected" : ""}`}
            onClick={() => handleSpriteSelect(skin.key)}
            title={skin.label}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={skin.path} alt={skin.label} draggable={false} />
            <span>{skin.label}</span>
          </button>
        ))}
      </div>
      <label>
        department
        <select value={department} onChange={(e) => setDepartment(e.target.value)}>
          {DEPARTMENTS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label>
        name (optional)
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kai" />
      </label>
      <label>
        initial task/prompt
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="what should this agent start working on?"
        />
      </label>
      {status === "error" && <div className="add-agent-error">error: {error}</div>}
      <button
        className="add-agent-submit"
        onClick={handleSubmit}
        disabled={status === "spawning"}
      >
        {status === "spawning" ? "spawning… (invisible terminal starting)" : "spawn agent"}
      </button>
    </div>
    </div>
  );
}
