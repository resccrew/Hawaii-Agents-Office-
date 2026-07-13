"use client";

import { useCallback } from "react";
import type { Graphics } from "pixi.js";

// Shared small "name plate" — a dark pill behind text so labels stay
// readable against the busy hand-painted office background instead of
// relying on a text stroke alone. Used by DevCapsule, LeadCapsule, and
// StudioGame's department labels so every label in the scene reads the
// same way (design-pass fix: labels were previously bare stroked text
// that both blended into the background and, for the phase label,
// literally overlapped the character sprite's body).
export function LabelTag({
  text,
  fontSize = 20,
  color = "#f8fafc",
  width,
}: {
  text: string;
  fontSize?: number;
  color?: string;
  width?: number;
}) {
  const pillWidth = width ?? Math.max(70, text.length * fontSize * 0.62);
  const pillHeight = fontSize + 14;

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      g.roundRect(-pillWidth / 2, -pillHeight / 2, pillWidth, pillHeight, 4);
      g.fill({ color: 0x1a1030, alpha: 0.78 });
      g.stroke({ width: 2, color: 0x2b1b3d, alpha: 0.9 });
    },
    [pillWidth, pillHeight],
  );

  return (
    <pixiContainer scale={0.5}>
      <pixiGraphics draw={draw} />
      <pixiText
        text={text}
        anchor={0.5}
        style={{ fontSize, fill: color, fontFamily: "monospace", fontWeight: "bold" }}
      />
    </pixiContainer>
  );
}
