"use client";

import { useState } from "react";

const ROLES = [
  { value: "programmer", label: "Programmer" },
  { value: "game_designer", label: "Game Designer" },
  { value: "artist", label: "Artist" },
  { value: "qa_tester", label: "QA Tester" },
  { value: "producer", label: "Producer" },
];

const DEPARTMENTS = ["Engineering", "Art", "Design", "QA"];

interface Props {
  onSpawned: (sessionId: string) => void;
  apiBase?: string;
}

// The whole point of Phase 6's Add-Agent flow: no terminal is ever shown.
// This form POSTs to /api/v1/agents, which spawns `claude -p` invisibly
// server-side and returns a session_id the moment it's ready — from here
// on, the new agent behaves exactly like any other Dev: click it, chat
// with it via the existing ChatPanel.
export function AddAgentButton({ onSpawned, apiBase = "http://localhost:8010" }: Props) {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState(ROLES[0].value);
  const [department, setDepartment] = useState(DEPARTMENTS[0]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<"idle" | "spawning" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!prompt.trim()) return;
    setStatus("spawning");
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/v1/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: "claude",
          department_id: department,
          role,
          name: name.trim() || role,
          initial_prompt: prompt,
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
      onSpawned(data.session_id);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!open) {
    return (
      <button className="add-agent-fab pixel-frame" onClick={() => setOpen(true)}>
        + agent
      </button>
    );
  }

  return (
    <div className="add-agent-overlay">
    <div className="add-agent-modal pixel-frame">
      <div className="add-agent-header">
        <span>spawn new agent</span>
        <button onClick={() => setOpen(false)}>x</button>
      </div>
      <label>
        role
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
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
