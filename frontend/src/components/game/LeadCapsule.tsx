"use client";

import { useCallback, useRef, useState } from "react";
import { useTick } from "@pixi/react";
import type { Graphics } from "pixi.js";
import type { DevRole, Position } from "@/lib/types";
import { useSpriteTexture } from "@/systems/useSpriteTexture";
import { SPRITE_PATH_BY_ROLE } from "@/systems/spriteRoles";
import type { OfficePlan } from "@/systems/officeMovement";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { LabelTag } from "./LabelTag";

const WIDTH = 64;
const HEIGHT = 100;
const DEFAULT_SPRITE_PATH = "/sprites/producer_front_idle.png";
const WALK_SPEED = 130; // px/sec along the A*-routed path

interface Props {
  plan: OfficePlan;
  role: DevRole | null;
  name: string | null;
  chatAvailable: boolean;
  onClick?: () => void;
}

// The office character for one spawned agent. Walks along plan.path — busy:
// lounge → CEO ("getting task") → window ("planning") → desk chair
// ("working"); idle: wherever they are → a lounge seat. Makes who's-busy
// obvious at a glance: seated at a desk = working, hanging out by the bar/
// hammock = free.
export function LeadCapsule({ plan, role, name, chatAvailable, onClick }: Props) {
  const spritePath = (role && SPRITE_PATH_BY_ROLE[role]) || DEFAULT_SPRITE_PATH;
  const texture = useSpriteTexture(spritePath);
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);

  // Local walk state — position persists across plan changes (continuity),
  // waypoint index resets when a new plan (new targetKey) comes in.
  const [renderPos, setRenderPos] = useState<Position>(plan.position);
  const waypoint = useRef(0);
  const dwellLeft = useRef(0);
  const dwellLabel = useRef<string | null>(null);
  const planKey = useRef<string | null>(null);

  if (planKey.current !== plan.targetKey) {
    planKey.current = plan.targetKey;
    if (reduceMotion) {
      // General settings → "reduce motion": skip the walk pantomime
      // entirely, appear at the destination immediately (useTick's guard
      // below then no-ops since waypoint is already past the path end).
      const finalTarget = plan.path[plan.path.length - 1] ?? plan.position;
      setRenderPos(finalTarget);
      waypoint.current = plan.path.length;
      dwellLeft.current = 0;
      dwellLabel.current = null;
    } else {
      waypoint.current = 0;
      dwellLeft.current = 0;
      dwellLabel.current = null;
    }
  }

  useTick((ticker) => {
    if (dwellLeft.current > 0) {
      dwellLeft.current -= ticker.deltaMS;
      return;
    }
    const path = plan.path;
    if (waypoint.current >= path.length) return;
    const target = path[waypoint.current];
    setRenderPos((prev) => {
      const dx = target.x - prev.x;
      const dy = target.y - prev.y;
      const dist = Math.hypot(dx, dy);
      const step = (WALK_SPEED * ticker.deltaMS) / 1000;
      if (dist <= step) {
        // Arrived at this waypoint — pause here if it's a scripted stop
        // (getting the task from the CEO, planning by the window).
        const stop = plan.stops.find((s) => s.index === waypoint.current);
        if (stop) {
          dwellLeft.current = stop.ms;
          dwellLabel.current = stop.label;
        }
        waypoint.current += 1;
        return target;
      }
      return { x: prev.x + (dx / dist) * step, y: prev.y + (dy / dist) * step };
    });
  });

  const isMoving = waypoint.current < plan.path.length || dwellLeft.current > 0;
  const statusLabel = isMoving ? dwellLeft.current > 0 ? dwellLabel.current ?? "walking" : "walking" : plan.arrivedPhase;

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      g.roundRect(-WIDTH / 2, -HEIGHT, WIDTH, HEIGHT, WIDTH / 2);
      g.fill({ color: 0xf59e0b, alpha: 1 });
      g.stroke({ width: 4, color: chatAvailable ? 0xffffff : 0x111827 });
    },
    [chatAvailable],
  );

  const scale = texture ? HEIGHT / texture.height : 1;
  const label = name ?? "Producer";

  return (
    <pixiContainer
      x={renderPos.x}
      y={renderPos.y}
      eventMode="static"
      cursor="pointer"
      onClick={onClick}
    >
      {texture ? (
        <pixiSprite
          texture={texture}
          anchor={{ x: 0.5, y: 1 }}
          scale={scale}
          tint={chatAvailable ? 0xffffff : 0xaaaaaa}
        />
      ) : (
        <pixiGraphics draw={draw} />
      )}
      <pixiContainer y={-HEIGHT - 16}>
        <LabelTag text={label} fontSize={22} color="#ffe08a" width={110} />
      </pixiContainer>
      <pixiContainer y={18}>
        <LabelTag text={statusLabel} fontSize={16} color="#a7f3d0" />
      </pixiContainer>
    </pixiContainer>
  );
}
