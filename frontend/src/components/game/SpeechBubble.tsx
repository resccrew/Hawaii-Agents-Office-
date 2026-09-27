"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTick } from "@pixi/react";
import type { Graphics } from "pixi.js";
import type { BubbleContent } from "@/lib/types";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";

const VISIBLE_MS = 4500; // how long a bubble stays up before it starts fading
const FADE_MS = 550;
const MAX_CHARS = 46;

// Heuristic for "this bubble is reporting a tool failure" — the wire
// BubbleContent (models/common.py) has no dedicated error flag, only
// type: "thought" | "speech" plus a free `icon`; state_machine.py's own
// comments ("error surfaces via bubble") confirm icon is the intended
// signal. Matches the icons an error-path bubble would realistically use.
const ERROR_ICON_RE = /[⚠❌🔥🛑]/u;

function truncate(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > MAX_CHARS ? `${trimmed.slice(0, MAX_CHARS - 1)}…` : trimmed;
}

interface Props {
  bubble: BubbleContent | null | undefined;
  /** Extra upward push (px) so this bubble clears another one directly
   *  below it when several characters are close together on stage — see
   *  RoomGame.tsx's computeBubbleStackOffsets. */
  stackOffset?: number;
  /** Base distance (px) above the container's origin (typically the head). */
  baseY?: number;
}

// Short lifecycle/tool-event speech bubble rendered above a character
// (LeadCapsule/CatCapsule). Backed by Dev.bubble/Lead.bubble
// (BubbleContent: type/text/icon/persistent — see lib/types.ts, mirroring
// backend/app/models/common.py), which today is populated from
// AgentEventData/LifecycleEventData's bubble_content/speech_content as
// events land. Auto-hides after a few seconds unless `persistent`; a
// fresh bubble (new text) always resets the clock. Fade-out is skipped
// entirely under reduceMotion — it just disappears, per the project's
// existing reduced-motion contract (see LeadCapsule's own reduceMotion use).
export function SpeechBubble({ bubble, stackOffset = 0, baseY = -18 }: Props) {
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);
  const [shown, setShown] = useState<{ text: string; icon?: string | null } | null>(null);
  const [alpha, setAlpha] = useState(1);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fadeStart = useRef<number | null>(null);
  const lastKey = useRef<string | null>(null);

  useEffect(() => {
    if (!bubble) return;
    const text = bubble.text?.trim();
    if (!text) return;
    const key = `${text}::${bubble.icon ?? ""}`;
    if (key === lastKey.current) return; // same content already showing/shown
    lastKey.current = key;

    if (hideTimer.current) clearTimeout(hideTimer.current);
    fadeStart.current = null;
    setAlpha(1);
    setShown({ text: truncate(text), icon: bubble.icon });

    if (!bubble.persistent) {
      hideTimer.current = setTimeout(() => {
        if (reduceMotion) {
          setShown(null);
          lastKey.current = null;
        } else {
          fadeStart.current = performance.now();
        }
      }, VISIBLE_MS);
    }
    return () => {
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, [bubble?.text, bubble?.icon, bubble?.persistent, reduceMotion]);

  useTick(() => {
    if (fadeStart.current === null) return;
    const t = Math.min(1, (performance.now() - fadeStart.current) / FADE_MS);
    setAlpha(1 - t);
    if (t >= 1) {
      fadeStart.current = null;
      lastKey.current = null;
      setShown(null);
    }
  });

  const isError = !!shown?.icon && ERROR_ICON_RE.test(shown.icon);

  const label = shown ? `${shown.icon ? `${shown.icon} ` : ""}${shown.text}` : "";
  const pillWidth = Math.min(230, Math.max(60, label.length * 6.4 + 22));
  const pillHeight = 26;

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      g.roundRect(-pillWidth / 2, -pillHeight, pillWidth, pillHeight, 8);
      g.fill({ color: isError ? 0x3a1220 : 0x1a1030, alpha: 0.92 });
      g.stroke({ width: 1.5, color: isError ? 0xfb7185 : 0x6d5b96, alpha: 0.9 });
      // Little tail pointing down toward the character.
      g.moveTo(-6, -2);
      g.lineTo(0, 6);
      g.lineTo(6, -2);
      g.fill({ color: isError ? 0x3a1220 : 0x1a1030, alpha: 0.92 });
    },
    [pillWidth, isError],
  );

  if (!shown) return null;

  return (
    <pixiContainer y={baseY - stackOffset} alpha={alpha}>
      <pixiGraphics draw={draw} />
      <pixiText
        text={label}
        anchor={0.5}
        y={-pillHeight / 2}
        style={{
          fontSize: 12,
          fill: isError ? "#ffd7de" : "#f6eefb",
          fontFamily: "monospace",
          fontWeight: isError ? "bold" : "normal",
        }}
      />
    </pixiContainer>
  );
}
