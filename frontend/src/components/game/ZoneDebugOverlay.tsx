"use client";

import { useCallback } from "react";
import type { Graphics } from "pixi.js";
import { WORK_SEATS, THINKING_SPOTS, IDLE_SEATS, CEO_SPOT } from "@/systems/layout";
import { obstaclesInStageSpace } from "@/systems/obstacles";
import { LabelTag } from "./LabelTag";

// Visual QA aid only — enabled via ?debug=1 in the URL. Draws every named
// zone (work seats, thinking spots, idle seats, the CEO spot) and the
// obstacle rectangles on top of the office art, so zone coordinates can be
// eyeballed against the actual background image and corrected without
// guessing blind. Never rendered in normal use.
const MARKERS: { points: { x: number; y: number }[]; color: number; label: string }[] = [
  { points: WORK_SEATS, color: 0x22c55e, label: "seat" },
  { points: THINKING_SPOTS, color: 0x38bdf8, label: "think" },
  { points: IDLE_SEATS, color: 0xf59e0b, label: "idle" },
  { points: [CEO_SPOT], color: 0xef4444, label: "ceo" },
];

export function ZoneDebugOverlay() {
  const drawObstacles = useCallback((g: Graphics) => {
    g.clear();
    for (const r of obstaclesInStageSpace()) {
      g.rect(r.x, r.y, r.w, r.h);
      g.fill({ color: 0xff00ff, alpha: 0.18 });
      g.stroke({ width: 1, color: 0xff00ff, alpha: 0.6 });
    }
  }, []);

  return (
    <pixiContainer>
      <pixiGraphics draw={drawObstacles} />
      {MARKERS.map((group) =>
        group.points.map((p, i) => (
          <pixiContainer key={`${group.label}-${i}`} x={p.x} y={p.y}>
            <MarkerDot color={group.color} />
            <pixiContainer y={-14}>
              <LabelTag text={`${group.label}${i}`} fontSize={10} color="#ffffff" />
            </pixiContainer>
          </pixiContainer>
        )),
      )}
    </pixiContainer>
  );
}

function MarkerDot({ color }: { color: number }) {
  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      g.circle(0, 0, 5);
      g.fill({ color, alpha: 0.9 });
      g.stroke({ width: 1, color: 0x000000 });
    },
    [color],
  );
  return <pixiGraphics draw={draw} />;
}
