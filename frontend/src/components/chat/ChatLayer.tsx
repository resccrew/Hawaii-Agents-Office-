"use client";

import { useEffect, useState } from "react";
import { ChatWindow } from "./ChatWindow";
import { useChatStore, selectOpenSessions } from "@/stores/chatStore";

// Renders every open chat window. Array order in the store is the z-order,
// so the index maps straight to zIndex — the last-focused window sits on
// top. Base z of 20 keeps them above the canvas but below modals (z 50).
export function ChatLayer() {
  const openSessions = useChatStore(selectOpenSessions);
  const [frame, setFrame] = useState({ 
    width: typeof window !== 'undefined' ? window.innerWidth : 1000, 
    height: typeof window !== 'undefined' ? window.innerHeight : 800, 
    cropX: 0, 
    cropY: 0 
  });

  useEffect(() => {
    const handleResize = () => setFrame({ 
      width: window.innerWidth, 
      height: window.innerHeight, 
      cropX: 0, 
      cropY: 0 
    });
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <>
      {openSessions.map((sessionId, i) => (
        <ChatWindow
          key={sessionId}
          sessionId={sessionId}
          anchor={null}
          frame={frame}
          zIndex={50 + i}
        />
      ))}
    </>
  );
}
