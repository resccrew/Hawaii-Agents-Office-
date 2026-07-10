"use client";

import { useEffect, useRef, useState } from "react";
import { StudioGame } from "@/components/game/StudioGame";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { TaskBoard } from "@/components/tasks/TaskBoard";
import { AddAgentButton } from "@/components/agents/AddAgentButton";
import {
  useGameStore,
  selectIsConnected,
  selectSessionId,
  selectDepartmentId,
} from "@/stores/gameStore";
import { useChatStore } from "@/stores/chatStore";
import { connectSession } from "@/systems/webSocketController";

export default function Home() {
  const [sessionInput, setSessionInput] = useState("fixture-session-001");
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const isConnected = useGameStore(selectIsConnected);
  const sessionId = useGameStore(selectSessionId);
  const departmentId = useGameStore(selectDepartmentId);
  const openChatPanel = useChatStore((s) => s.openPanel);
  const disconnectRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!activeSession) return;
    disconnectRef.current = connectSession(activeSession);
    return () => disconnectRef.current();
  }, [activeSession]);

  const handleAgentSpawned = (newSessionId: string) => {
    // Add-Agent flow's whole point: the new agent appears immediately,
    // no terminal ever shown — switch straight to observing/chatting
    // with it, same as connecting to any other session.
    setSessionInput(newSessionId);
    setActiveSession(newSessionId);
    openChatPanel(newSessionId);
  };

  return (
    <main>
      <div className="toolbar">
        <span className="toolbar-title">🌴 Studio Ops</span>
        <input
          className="pixel-frame"
          value={sessionInput}
          onChange={(e) => setSessionInput(e.target.value)}
          placeholder="session_id"
        />
        <button className="pixel-frame" onClick={() => setActiveSession(sessionInput)}>
          Connect
        </button>
        <span
          className="status-dot"
          style={{ background: isConnected ? "#22c55e" : "#ef4444" }}
        />
        <span>{isConnected ? `connected: ${sessionId}` : "disconnected"}</span>
        <AddAgentButton onSpawned={handleAgentSpawned} />
      </div>
      <div className="game-stage-wrapper">
        <StudioGame
          onDevClick={() => sessionId && openChatPanel(sessionId)}
          onLeadClick={() => sessionId && openChatPanel(sessionId)}
        />
      </div>
      <TaskBoard departmentId={departmentId ?? "Engineering"} />
      <ChatPanel />
    </main>
  );
}
