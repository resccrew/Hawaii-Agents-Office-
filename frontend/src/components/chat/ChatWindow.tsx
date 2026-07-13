"use client";

import { useEffect, useRef, useState } from "react";
import {
  useChatStore,
  selectChatSession,
} from "@/stores/chatStore";
import { useRoomStore, selectRoomSessions } from "@/stores/roomStore";
import { useAgentsStore, selectAgents } from "@/stores/agentsStore";
import { connectChat, sendChatMessage, fileToAttachment } from "@/systems/chatWebSocketController";
import type { FitSize } from "@/systems/useFitSize";

// Mirrors the backend's per-file cap (chat.py's MAX_ATTACHMENT_BYTES) —
// checked client-side too so an oversized file gets a clear, instant
// rejection instead of a round-trip to the server just to be told no.
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`;
  return `${(n / (1024 * 1024)).toFixed(1)}MB`;
}

// claude -p's own --model/--effort aliases (see `claude --help`) — picked
// fresh per message, not fixed at spawn: --resume doesn't lock a session
// to whichever model created it.
const MODEL_OPTIONS = [
  { value: "", label: "model: auto" },
  { value: "sonnet", label: "Sonnet 5" },
  { value: "opus", label: "Opus 4.8" },
  { value: "haiku", label: "Haiku 4.5" },
  { value: "fable", label: "Fable 5" },
];
const EFFORT_OPTIONS = [
  { value: "", label: "effort: auto" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
  { value: "xhigh", label: "xhigh" },
  { value: "max", label: "max" },
];

// One draggable + resizable chat window, positioned absolutely inside the
// office canvas frame. Many can be open at once (see ChatLayer); each owns
// its own geometry (local state) and connects to its own agent session.
// Grab the header to move, the bottom-right handle to resize, click
// anywhere to bring it to the front (focusPanel reorders the z-stack).
const DEFAULT_W = 320;
const DEFAULT_H = 360;
const MIN_W = 240;
const MIN_H = 220;
const MAX_W = 720;
const MAX_H = 720;
const GAP = 34; // clearance between the agent sprite and the window
const EDGE = 8;

interface Props {
  sessionId: string;
  anchor?: { x: number; y: number } | null;
  frame?: FitSize;
  zIndex: number;
}

const STATUS_HINT: Record<string, string> = {
  idle: "ready",
  queued: "queued — busy, will send when free",
  streaming: "typing…",
  error: "connection error",
};

export function ChatWindow({ sessionId, anchor, frame, zIndex }: Props) {
  const session = useChatStore(selectChatSession(sessionId));
  const closePanel = useChatStore((s) => s.closePanel);
  const focusPanel = useChatStore((s) => s.focusPanel);
  const roomSessions = useRoomStore(selectRoomSessions);
  const agents = useAgentsStore(selectAgents);
  const [draft, setDraft] = useState("");
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [geom, setGeom] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const disconnectRef = useRef<() => void>(() => {});
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --model/--effort only mean anything for Claude — a session with no
  // registry entry is always a hook-observed interactive one (also always
  // Claude, the only thing that emits hook events; see chat_bridge.py's own
  // fallback). Every other registered provider hides the picker entirely
  // rather than show a control that silently does nothing.
  const agent = agents.find((a) => a.sessionId === sessionId);
  const isClaude = !agent || agent.provider === "claude";

  useEffect(() => {
    disconnectRef.current = connectChat(sessionId);
    return () => disconnectRef.current();
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [session.messages.length]);

  // Initial placement: above the agent, centered, clamped into the frame.
  // Computed once anchor+frame are known; user drag/resize takes over after.
  useEffect(() => {
    if (geom || !frame || frame.width === 0) return;
    let x: number;
    let y: number;
    if (anchor) {
      x = anchor.x - DEFAULT_W / 2;
      y = anchor.y - GAP - DEFAULT_H;
      if (y < frame.cropY + EDGE) y = anchor.y + GAP;
    } else {
      x = frame.width / 2 - DEFAULT_W / 2;
      y = frame.height - DEFAULT_H - 24;
    }
    x = Math.max(frame.cropX + EDGE, Math.min(x, frame.width - frame.cropX - DEFAULT_W - EDGE));
    y = Math.max(frame.cropY + EDGE, Math.min(y, frame.height - frame.cropY - DEFAULT_H - EDGE));
    setGeom({ x, y, w: DEFAULT_W, h: DEFAULT_H });
  }, [anchor, frame, geom]);

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    const tooBig = incoming.filter((f) => f.size > MAX_ATTACHMENT_BYTES);
    const ok = incoming.filter((f) => f.size <= MAX_ATTACHMENT_BYTES);
    if (tooBig.length > 0) {
      setAttachError(`too large (max ${formatBytes(MAX_ATTACHMENT_BYTES)}): ${tooBig.map((f) => f.name).join(", ")}`);
    } else {
      setAttachError(null);
    }
    if (ok.length > 0) setPendingFiles((prev) => [...prev, ...ok]);
  };

  const removeFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    const text = draft.trim();
    if (!text && pendingFiles.length === 0) return;
    setDraft("");
    const files = pendingFiles;
    setPendingFiles([]);
    setAttachError(null);
    const attachments = await Promise.all(files.map(fileToAttachment));
    void sendChatMessage(sessionId, text, { ...(isClaude ? { model, effort } : {}), attachments });
  };

  const startDrag = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button")) return;
    if (!geom) return;
    e.preventDefault();
    focusPanel(sessionId);
    const startX = e.clientX;
    const startY = e.clientY;
    const base = geom;
    const move = (ev: PointerEvent) => {
      setGeom({ ...base, x: base.x + (ev.clientX - startX), y: base.y + (ev.clientY - startY) });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const startResize = (e: React.PointerEvent) => {
    if (!geom) return;
    e.preventDefault();
    e.stopPropagation();
    focusPanel(sessionId);
    const startX = e.clientX;
    const startY = e.clientY;
    const base = geom;
    const move = (ev: PointerEvent) => {
      const w = Math.max(MIN_W, Math.min(MAX_W, base.w + (ev.clientX - startX)));
      const h = Math.max(MIN_H, Math.min(MAX_H, base.h + (ev.clientY - startY)));
      setGeom({ ...base, w, h });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  if (!geom) return null;

  const lead = roomSessions.get(sessionId)?.lead;
  const title = lead?.name || lead?.role || sessionId.slice(0, 8);

  return (
    <div
      className="chat-window"
      style={{ left: geom.x, top: geom.y, width: geom.w, height: geom.h, zIndex }}
      onPointerDown={() => focusPanel(sessionId)}
    >
      <div className="chat-panel-header" onPointerDown={startDrag} title="drag to move">
        <span className="chat-panel-title">
          <span className={`status-dot chat-dot-${session.status}`} />
          {title}
        </span>
        <span className="chat-panel-grip">⠿</span>
        <button onClick={() => closePanel(sessionId)} aria-label="close chat">✕</button>
      </div>
      <div className={`chat-panel-status chat-panel-status-${session.status}`}>
        {STATUS_HINT[session.status] ?? session.status}
      </div>
      <div
        className={`chat-panel-messages${dragOver ? " chat-panel-messages-dragover" : ""}`}
        ref={scrollRef}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files);
        }}
      >
        {session.messages.length === 0 && (
          <div className="panel-empty">
            <span className="panel-empty-icon">…</span>
            no messages yet
            <span className="panel-empty-hint">this agent is listening — drop a file to attach it</span>
          </div>
        )}
        {session.messages.map((m) => (
          <div key={m.id} className={`chat-msg chat-msg-${m.role}`}>
            <span className="chat-msg-role">{m.role === "assistant" ? title : m.role}</span>
            <span className="chat-msg-bubble">{m.text}</span>
          </div>
        ))}
        {dragOver && <div className="chat-panel-drop-hint">drop to attach</div>}
      </div>
      {attachError && <div className="chat-panel-attach-error">{attachError}</div>}
      {pendingFiles.length > 0 && (
        <div className="chat-panel-attachments">
          {pendingFiles.map((f, i) => (
            <span key={`${f.name}-${i}`} className="chat-attachment-chip">
              📎 {f.name}
              <button onClick={() => removeFile(i)} aria-label={`remove ${f.name}`}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {isClaude && (
        <div className="chat-panel-model-row">
          <select value={model} onChange={(e) => setModel(e.target.value)} title="model for the next message">
            {MODEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select value={effort} onChange={(e) => setEffort(e.target.value)} title="effort for the next message">
            {EFFORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="chat-panel-input">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = ""; // allow re-attaching the same file later
          }}
        />
        <button
          className="chat-attach-button"
          onClick={() => fileInputRef.current?.click()}
          aria-label="attach file"
          title="attach file"
        >
          📎
        </button>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="message this agent..."
        />
        <button onClick={handleSend} disabled={!draft.trim() && pendingFiles.length === 0}>
          send
        </button>
      </div>
      <div className="chat-window-resize" onPointerDown={startResize} title="drag to resize" />
    </div>
  );
}
