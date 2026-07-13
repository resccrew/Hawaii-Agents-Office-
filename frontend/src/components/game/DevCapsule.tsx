"use client";

import { useCallback, useRef, useState } from "react";
import { useTick } from "@pixi/react";
import type { Graphics } from "pixi.js";
import type { DevAnimationState } from "@/stores/slices/types";
import { useSpriteTexture } from "@/systems/useSpriteTexture";
import { SPRITE_PATH_BY_ROLE } from "@/systems/spriteRoles";
import { LabelTag } from "./LabelTag";

// Phase 5: real sprite art (falls back to the Phase 2 procedural capsule
// when a role's sprite hasn't been generated/approved yet, or fails to
// load — see studio-character-sprite skill for the generation pipeline).
const WIDTH = 48;
const HEIGHT = 80;
const WALK_SPEED = 140; // px/sec, moving along the A*-routed path

export function DevCapsule({
  dev,
  onClick,
}: {
  dev: DevAnimationState;
  onClick?: (devId: string) => void;
}) {
  const spritePath = SPRITE_PATH_BY_ROLE[dev.role] ?? null;
  const texture = useSpriteTexture(spritePath);

  // Local, per-instance animation state — walks the dev along dev.path
  // (computed once by pathToSpot() at arrival) frame by frame, routed
  // around furniture instead of snapping straight to the desk. Kept local
  // rather than written back to the store every tick (60x/sec store writes
  // would be wasteful when only this component ever reads position).
  const [renderPos, setRenderPos] = useState(dev.position);
  const waypointIndex = useRef(0);
  const initializedFor = useRef<string | null>(null);

  if (initializedFor.current !== dev.id) {
    initializedFor.current = dev.id;
    waypointIndex.current = 0;
  }

  useTick((ticker) => {
    const path = dev.path;
    if (!path || waypointIndex.current >= path.length) return;

    const target = path[waypointIndex.current];
    setRenderPos((prev) => {
      const dx = target.x - prev.x;
      const dy = target.y - prev.y;
      const dist = Math.hypot(dx, dy);
      const step = (WALK_SPEED * ticker.deltaMS) / 1000;
      if (dist <= step) {
        waypointIndex.current += 1;
        return target;
      }
      return { x: prev.x + (dx / dist) * step, y: prev.y + (dy / dist) * step };
    });
  });

  const isMoving = waypointIndex.current < (dev.path?.length ?? 0);

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      const colorNum = parseInt(dev.color.replace("#", ""), 16) || 0x2563eb;
      const alpha = dev.phase === "arriving" || dev.phase === "leaving" ? 0.5 : 1;
      g.roundRect(-WIDTH / 2, -HEIGHT, WIDTH, HEIGHT, WIDTH / 2);
      g.fill({ color: colorNum, alpha });
      g.stroke({ width: 3, color: dev.chatAvailable ? 0xffffff : 0x111827 });
    },
    [dev.color, dev.phase, dev.chatAvailable],
  );

  const spriteAlpha = dev.phase === "arriving" || dev.phase === "leaving" ? 0.5 : 1;
  const scale = texture ? HEIGHT / texture.height : 1;

  return (
    <pixiContainer
      x={renderPos.x}
      y={renderPos.y}
      eventMode="static"
      cursor="pointer"
      onClick={() => onClick?.(dev.id)}
    >
      {texture ? (
        <pixiSprite
          texture={texture}
          anchor={{ x: 0.5, y: 1 }}
          scale={scale}
          alpha={spriteAlpha}
          tint={dev.chatAvailable ? 0xffffff : 0xaaaaaa}
        />
      ) : (
        <pixiGraphics draw={draw} />
      )}
      {/* Name sits just above the head — clear of both the sprite and the
          department label (which is anchored much higher, see
          StudioGame.tsx). Status sits just below the feet, on the floor —
          not mid-body, which is where it used to collide with the sprite
          artwork before real character sprites replaced flat capsules. */}
      <pixiContainer y={-HEIGHT - 14}>
        <LabelTag text={dev.name ?? dev.role} fontSize={20} />
      </pixiContainer>
      <pixiContainer y={16}>
        <LabelTag text={isMoving ? "walking" : dev.phase} fontSize={16} color="#a7f3d0" />
      </pixiContainer>
    </pixiContainer>
  );
}
