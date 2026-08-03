"use client";

import { useEffect, useState } from "react";
import {
  getSettings,
  updateSettings,
  getModelCatalog,
  type SettingField,
  type ModelCatalog,
} from "@/systems/api";
import { useUiSettingsStore, DEFAULT_UI_SETTINGS } from "@/stores/uiSettingsStore";

interface Props {
  onClose: () => void;
}

const GROUP_LABELS: Record<string, string> = {
  openai: "OpenAI (GPT)",
  gemini: "Gemini",
  ollama: "Ollama (local)",
  nanobanana: "Nano Banana (image gen)",
};

// Which settings keys are "pick a model" fields — these get a live
// dropdown (see ModelField below) instead of a plain text input. ollama has
// no key of its own (local server), so its catalog call never needs one.
const MODEL_FIELD_PROVIDER: Record<string, string> = {
  openai_model: "openai",
  gemini_model: "gemini",
  ollama_model: "ollama",
};

const CUSTOM = "__custom__";

function groupOf(key: string): string {
  return key.split("_")[0];
}

const SOURCE_LABEL: Record<SettingField["source"], string> = {
  override: "saved here",
  env: "from environment",
  unset: "not configured",
};

const DEPARTMENTS = ["Engineering", "Art", "Design", "QA", "Production"];

// A model select for one provider — fetches its catalog lazily (on mount)
// and lets the field fall back to free text via a "custom…" option, since
// the live catalog (or the static fallback when no key is set yet) is a
// starting point, not a hard whitelist.
function ModelField({
  field,
  draft,
  onChange,
}: {
  field: SettingField;
  draft: string | undefined;
  onChange: (value: string) => void;
}) {
  const provider = MODEL_FIELD_PROVIDER[field.key];
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const current = draft ?? field.preview ?? "";
  const [customMode, setCustomMode] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getModelCatalog(provider)
      .then((c) => {
        if (cancelled) return;
        setCatalog(c);
        setCustomMode(current !== "" && !c.models.includes(current));
      })
      .catch(() => {
        if (!cancelled) setCatalog({ models: [], source: "unreachable" });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Only re-fetch if the provider changes (it never does per-instance) —
    // deliberately not depending on `current`, or every keystroke in
    // custom mode would refetch the catalog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const options = catalog?.models ?? [];

  return (
    <div className="settings-model-field">
      {!customMode ? (
        <select
          value={options.includes(current) ? current : ""}
          onChange={(e) => {
            if (e.target.value === CUSTOM) {
              setCustomMode(true);
              return;
            }
            onChange(e.target.value);
          }}
        >
          <option value="">{loading ? "loading models…" : "use default"}</option>
          {options.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
          <option value={CUSTOM}>custom…</option>
        </select>
      ) : (
        <div className="settings-model-custom">
          <input
            type="text"
            value={current}
            onChange={(e) => onChange(e.target.value)}
            placeholder="model name"
          />
          <button type="button" onClick={() => setCustomMode(false)}>
            list
          </button>
        </div>
      )}
      {catalog && (
        <span className="settings-model-source">
          {catalog.source === "live"
            ? `${options.length} models from your ${GROUP_LABELS[provider]} account`
            : catalog.source === "unreachable"
              ? "couldn't reach the server — type a model name"
              : "starter list — add an API key above for your account's real catalog"}
        </span>
      )}
    </div>
  );
}

// Provider API keys, model choices, and local endpoints (backend-persisted
// — see settings_store.py), plus general frontend-only app settings
// (localStorage-persisted — see uiSettingsStore.ts). Two tabs so "where do
// I paste my key" and "what URL does this app even point at" don't compete
// for the same screen.
export function SettingsModal({ onClose }: Props) {
  const [tab, setTab] = useState<"general" | "keys">("general");

  const backendHttpUrl = useUiSettingsStore((s) => s.backendHttpUrl);
  const setBackendHttpUrl = useUiSettingsStore((s) => s.setBackendHttpUrl);
  const defaultDepartment = useUiSettingsStore((s) => s.defaultDepartment);
  const setDefaultDepartment = useUiSettingsStore((s) => s.setDefaultDepartment);
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);
  const setReduceMotion = useUiSettingsStore((s) => s.setReduceMotion);
  const [backendUrlDraft, setBackendUrlDraft] = useState(backendHttpUrl);

  const [fields, setFields] = useState<SettingField[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    getSettings()
      .then((f) => {
        setFields(f);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (backendUrlDraft.trim() !== backendHttpUrl) {
        setBackendHttpUrl(backendUrlDraft);
      }
      const changed = Object.fromEntries(Object.entries(drafts).filter(([, v]) => v !== undefined));
      if (Object.keys(changed).length > 0) {
        const updated = await updateSettings(changed);
        setFields(updated);
        setDrafts({});
      }
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const groups = Array.from(new Set(fields.map((f) => groupOf(f.key))));

  return (
    <div className="add-agent-overlay">
      <div className="settings-modal pixel-frame">
        <div className="add-agent-header">
          <span>settings</span>
          <button onClick={onClose}>x</button>
        </div>

        <div className="side-panel-tabs settings-tabs">
          <button
            className={tab === "general" ? "side-tab side-tab-active" : "side-tab"}
            onClick={() => setTab("general")}
          >
            general
          </button>
          <button
            className={tab === "keys" ? "side-tab side-tab-active" : "side-tab"}
            onClick={() => setTab("keys")}
          >
            keys &amp; models
          </button>
        </div>

        {error && <div className="add-agent-error">error: {error}</div>}

        {tab === "general" && (
          <div className="settings-body">
            <label className="settings-field">
              <span className="settings-field-label">backend URL</span>
              <input
                type="text"
                value={backendUrlDraft}
                onChange={(e) => setBackendUrlDraft(e.target.value)}
                placeholder={DEFAULT_UI_SETTINGS.backendHttpUrl}
              />
            </label>
            <label className="settings-field">
              <span className="settings-field-label">default department for new agents</span>
              <select value={defaultDepartment} onChange={(e) => setDefaultDepartment(e.target.value)}>
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="settings-checkbox-field">
              <input
                type="checkbox"
                checked={reduceMotion}
                onChange={(e) => setReduceMotion(e.target.checked)}
              />
              <span>reduce motion (agents appear instantly, no burst/UI animation)</span>
            </label>
            <label className="settings-field">
              <span className="settings-field-label">app theme</span>
              <select value={useUiSettingsStore((s) => s.theme)} onChange={(e) => useUiSettingsStore.getState().setTheme(e.target.value as "hawaii" | "terminal")}>
                <option value="hawaii">Hawaii Office (Beach/Sunset)</option>
                <option value="terminal">Terminal (Tokyo Night)</option>
              </select>
            </label>
            <div className="settings-hint">
              Changing the backend URL reconnects every socket the next time a panel opens — reload
              the page if something still looks stale.
            </div>
          </div>
        )}

        {tab === "keys" && (
          <div className="settings-body">
            {loading && <div className="panel-empty">loading…</div>}
            {!loading &&
              groups.map((group) => (
                <div key={group} className="settings-group">
                  <div className="settings-group-title">{GROUP_LABELS[group] ?? group}</div>
                  {fields
                    .filter((f) => groupOf(f.key) === group)
                    .map((f) => (
                      <label key={f.key} className="settings-field">
                        <span className="settings-field-label">
                          {f.label}
                          <span className={`settings-source settings-source-${f.source}`}>
                            {SOURCE_LABEL[f.source]}
                          </span>
                        </span>
                        {MODEL_FIELD_PROVIDER[f.key] ? (
                          <ModelField
                            field={f}
                            draft={drafts[f.key]}
                            onChange={(v) => setDrafts((d) => ({ ...d, [f.key]: v }))}
                          />
                        ) : (
                          <input
                            type={f.kind === "secret" ? "password" : "text"}
                            value={drafts[f.key] ?? ""}
                            onChange={(e) => setDrafts((d) => ({ ...d, [f.key]: e.target.value }))}
                            placeholder={f.preview ?? (f.kind === "secret" ? "not set" : "default")}
                          />
                        )}
                      </label>
                    ))}
                </div>
              ))}
            <div className="settings-hint">
              Leave a field blank to keep its current value. Clear a field and save to remove a
              saved override (falls back to its env var, if any).
            </div>
          </div>
        )}

        {savedAt && !saving && <div className="settings-saved">saved ✓</div>}

        <button className="add-agent-submit" onClick={handleSave} disabled={saving || loading}>
          {saving ? "saving…" : "save"}
        </button>
      </div>
    </div>
  );
}
