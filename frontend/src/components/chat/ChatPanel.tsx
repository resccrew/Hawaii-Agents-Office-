"use client";

import { useEffect, useRef, useState } from "react";
import {
  useChatStore,
  selectActiveChatSessionId,
  selectChatSession,
} from "@/stores/chatStore";
import { connectChat, sendChatMessage } from "@/systems/chatWebSocketController";

// HTML overlay, not PixiJS — chat text is a poor fit for canvas rendering
// (scrolling, selection, IME input). Opened by clicking a Dev/Lead capsule
// (ChatTrigger wiring lives in StudioGame's onClick handlers in page.tsx).
export function ChatPanel() {
  const activeSessionId = useChatStore(selectActiveChatSessionId);
  const closePanel = useChatStore((s) => s.closePanel);
  const session = useChatStore(selectChatSession(activeSessionId ?? ""));
  const [draft, setDraft] = useState("");
  const disconnectRef = useRef<() => void>(() => {});
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!activeSessionId) return;
    disconnectRef.current = connectChat(activeSessionId);
    return () => disconnectRef.current();
  }, [activeSessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [session.messages.length]);

  if (!activeSessionId) return null;

  const handleSend = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void sendChatMessage(activeSessionId, text);
  };

  return (
    <div className="chat-panel">
      <div className="chat-panel-header">
        <span>chat — {activeSessionId}</span>
        <button onClick={closePanel}>close</button>
      </div>
      <div className="chat-panel-status">
        status: {session.status}
        {session.status === "queued" && " (agent busy in terminal — will send when free)"}
      </div>
      <div className="chat-panel-messages" ref={scrollRef}>
        {session.messages.map((m) => (
          <div key={m.id} className={`chat-msg chat-msg-${m.role}`}>
            <span className="chat-msg-role">{m.role}</span>
            <span>{m.text}</span>
          </div>
        ))}
      </div>
      <div className="chat-panel-input">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="message this agent..."
        />
        <button onClick={handleSend}>send</button>
      </div>
    </div>
  );
}
