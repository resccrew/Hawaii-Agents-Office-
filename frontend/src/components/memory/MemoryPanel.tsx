"use client";

import { useCallback, useEffect, useState } from "react";
import {
  deleteMemory,
  listMemory,
  readMemory,
  writeMemory,
  type MemoryFact,
  type MemoryIndexEntry,
} from "@/systems/api";

interface Props {
  /** The agent's own memory scope (its agent_id) — "office" is always
   * offered alongside it as the second tab. */
  agentScope: string;
  agentLabel: string;
  onClose: () => void;
}

const TYPES: MemoryFact["type"][] = ["user", "feedback", "project", "reference"];
const OFFICE_SCOPE = "office";

const EMPTY_DRAFT = { slug: "", name: "", description: "", type: "project" as MemoryFact["type"], body: "" };

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64) || "fact";
}

/** List + read + edit + delete memory facts for one agent's own scope or
 * the shared office scope — same MEMORY.md-index-plus-fact-files model as
 * this assistant's own memory system, opened from a button on the agent's
 * chat window (see ChatWindow.tsx). Refetches after every write/delete
 * rather than a live WS channel — memory changes are infrequent (written
 * once at the end of a task, per the spawn-time CLAUDE.md instructions),
 * so a plain refetch keeps this panel independent of connection_manager. */
export function MemoryPanel({ agentScope, agentLabel, onClose }: Props) {
  const [scope, setScope] = useState(agentScope);
  const [entries, setEntries] = useState<MemoryIndexEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [isNew, setIsNew] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshIndex = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listMemory(scope);
      setEntries(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    setSelected(null);
    setIsNew(false);
    setDraft(EMPTY_DRAFT);
    refreshIndex();
  }, [refreshIndex]);

  const openFact = async (slug: string) => {
    setError(null);
    try {
      const fact = await readMemory(scope, slug);
      setSelected(slug);
      setIsNew(false);
      setDraft({ slug: fact.slug, name: fact.name, description: fact.description, type: fact.type, body: fact.body });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const startNew = () => {
    setSelected(null);
    setIsNew(true);
    setDraft(EMPTY_DRAFT);
  };

  const save = async () => {
    const slug = isNew ? slugify(draft.slug || draft.name) : draft.slug;
    if (!slug || !draft.name.trim()) {
      setError("name (and a slug for a new fact) are required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await writeMemory(scope, slug, {
        name: draft.name,
        description: draft.description,
        type: draft.type,
        body: draft.body,
      });
      await refreshIndex();
      setSelected(slug);
      setIsNew(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (slug: string) => {
    setSaving(true);
    setError(null);
    try {
      await deleteMemory(scope, slug);
      if (selected === slug) {
        setSelected(null);
        setDraft(EMPTY_DRAFT);
      }
      await refreshIndex();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const editing = isNew || selected !== null;

  return (
    <div className="add-agent-overlay">
      <div className="add-agent-modal memory-modal">
        <div className="add-agent-header">
          <span>memory — {scope === OFFICE_SCOPE ? "office" : agentLabel}</span>
          <button onClick={onClose}>x</button>
        </div>

        <div className="side-panel-tabs settings-tabs">
          <button
            className={scope === agentScope ? "side-tab side-tab-active" : "side-tab"}
            onClick={() => setScope(agentScope)}
          >
            {agentLabel}
          </button>
          <button
            className={scope === OFFICE_SCOPE ? "side-tab side-tab-active" : "side-tab"}
            onClick={() => setScope(OFFICE_SCOPE)}
          >
            office
          </button>
        </div>

        {error && <div className="add-agent-error">{error}</div>}

        <div className="memory-body">
          <div className="memory-list">
            <button className="memory-new-button" onClick={startNew}>
              + new fact
            </button>
            {loading && <div className="memory-hint">loading…</div>}
            {!loading && entries.length === 0 && <div className="memory-hint">nothing here yet</div>}
            {entries.map((e) => (
              <div
                key={e.slug}
                className={e.slug === selected ? "memory-list-item memory-list-item-active" : "memory-list-item"}
                onClick={() => openFact(e.slug)}
              >
                <div className="memory-list-item-name">{e.name}</div>
                <div className="memory-list-item-desc">{e.description}</div>
              </div>
            ))}
          </div>

          {editing && (
            <div className="memory-editor">
              {isNew && (
                <label>
                  slug
                  <input
                    value={draft.slug}
                    onChange={(e) => setDraft((d) => ({ ...d, slug: e.target.value }))}
                    placeholder="short-kebab-case-id"
                  />
                </label>
              )}
              <label>
                name
                <input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
              </label>
              <label>
                description
                <input
                  value={draft.description}
                  onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                />
              </label>
              <label>
                type
                <select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value as MemoryFact["type"] }))}>
                  {TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                body
                <textarea
                  className="memory-fact-body"
                  rows={8}
                  value={draft.body}
                  onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                />
              </label>
              <div className="memory-editor-actions">
                <button onClick={save} disabled={saving}>
                  {saving ? "saving…" : "save"}
                </button>
                {!isNew && (
                  <button className="memory-delete-button" onClick={() => remove(draft.slug)} disabled={saving}>
                    delete
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
