"use client";

import { ChatWindow } from "./ChatWindow";
import { useChatStore, selectOpenSessions } from "@/stores/chatStore";
import type { FitSize } from "@/systems/useFitSize";

interface Props {
  // Maps an agent's session_id to its on-screen pixel position inside the
  // canvas frame (computed in page.tsx from the agent's slot), so a newly
  // opened window can anchor above the right sprite. null = agent not
  // on-screen (overflow) → window opens at a default spot.
  anchorFor: (sessionId: string) => { x: number; y: number } | null;
  frame: FitSize;
}

// Renders every open chat window. Array order in the store is the z-order,
// so the index maps straight to zIndex — the last-focused window sits on
// top. Base z of 20 keeps them above the canvas but below modals (z 50).
export function ChatLayer({ anchorFor, frame }: Props) {
  const openSessions = useChatStore(selectOpenSessions);

  return (
    <>
      {openSessions.map((sessionId, i) => (
        <ChatWindow
          key={sessionId}
          sessionId={sessionId}
          anchor={anchorFor(sessionId)}
          frame={frame}
          zIndex={20 + i}
        />
      ))}
    </>
  );
}
