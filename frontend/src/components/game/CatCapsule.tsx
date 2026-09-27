"use client";

import { useRef, useState } from "react";
import { useTick } from "@pixi/react";
import type { BubbleContent, Position } from "@/lib/types";
import { useSpriteTexture } from "@/systems/useSpriteTexture";
import type { CatPlan } from "@/systems/catMovement";
import { LabelTag } from "./LabelTag";
import { SpeechBubble } from "./SpeechBubble";

// Five hand-picked designs (not a walk-cycle of one cat — five distinct
// cats), assigned per-subagent for visual variety the same way DevRole
// assigns one of four role sprites to a Dev. Kept fixed for a cat's whole
// lifetime (see RoomGame.tsx's index assignment), not swapped per pose —
// same "one static image, just translated" approach LeadCapsule/DevCapsule
// already use, no per-frame animation.
export const CAT_SPRITES = [
  "/sprites/cats/tabby_groom.png",
  "/sprites/cats/tuxedo_stand.png",
  "/sprites/cats/orange_walk.png",
  "/sprites/cats/calico_sit.png",
  "/sprites/cats/black_sit.png",
];

const TARGET_HEIGHT = 46; // small — a cat at a Dev's feet, not another Lead
const WALK_SPEED = 65; // px/sec, slower/lazier than a Lead's 130

interface Props {
  catIndex: number;
  plan: CatPlan;
  showLabel?: boolean;
  bubble?: BubbleContent | null;
  bubbleStackOffset?: number;
}

// One Task-tool subagent, rendered as a cat that stays near its owner Lead
// (see catMovement.ts) — curls up while the owner is idle, paces a small
// loop nearby while it's working. Purely decorative/no interaction: unlike
// Leads, subagents have no addressable chat session of their own.
export function CatCapsule({ catIndex, plan, showLabel = false, bubble, bubbleStackOffset = 0 }: Props) {
  const spritePath = CAT_SPRITES[((catIndex % CAT_SPRITES.length) + CAT_SPRITES.length) % CAT_SPRITES.length];
  const texture = useSpriteTexture(spritePath);

  const [renderPos, setRenderPos] = useState<Position>(plan.position);
  const waypoint = useRef(0);
  const planKey = useRef<string | null>(null);
  const facingLeft = useRef(false);

  if (planKey.current !== plan.targetKey) {
    planKey.current = plan.targetKey;
    waypoint.current = 0;
  }

  useTick((ticker) => {
    const path = plan.path;
    if (waypoint.current >= path.length) return;
    const target = path[waypoint.current];
    setRenderPos((prev) => {
      const dx = target.x - prev.x;
      const dy = target.y - prev.y;
      const dist = Math.hypot(dx, dy);
      if (Math.abs(dx) > 2) facingLeft.current = dx < 0;
      const step = (WALK_SPEED * ticker.deltaMS) / 1000;
      if (dist <= step) {
        waypoint.current += 1;
        return target;
      }
      return { x: prev.x + (dx / dist) * step, y: prev.y + (dy / dist) * step };
    });
  });

  if (!texture) return null;
  const scale = TARGET_HEIGHT / texture.height;

  return (
    <pixiContainer x={renderPos.x} y={renderPos.y}>
      <pixiSprite
        texture={texture}
        anchor={{ x: 0.5, y: 1 }}
        scale={{ x: facingLeft.current ? -scale : scale, y: scale }}
      />
      {showLabel && (
        <pixiContainer y={10}>
          <LabelTag text={plan.label} fontSize={10} color="#e9b7d4" />
        </pixiContainer>
      )}
      <SpeechBubble bubble={bubble} baseY={-TARGET_HEIGHT - 10} stackOffset={bubbleStackOffset} />
    </pixiContainer>
  );
}
