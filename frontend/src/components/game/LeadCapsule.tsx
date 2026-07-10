"use client";

import { useCallback } from "react";
import type { Graphics } from "pixi.js";
import type { LeadAnimationState } from "@/stores/slices/types";
import { useSpriteTexture } from "@/systems/useSpriteTexture";
import { SPRITE_PATH_BY_ROLE } from "@/systems/spriteRoles";

const WIDTH = 64;
const HEIGHT = 100;
const DEFAULT_SPRITE_PATH = "/sprites/producer_front_idle.png";

export function LeadCapsule({ lead, onClick }: { lead: LeadAnimationState; onClick?: () => void }) {
  // Bugfix (double-render): a spawned peer agent's Lead carries its own
  // role (see backend Lead.role) — render that role's sprite instead of
  // always defaulting to the producer. Real interactive sessions have
  // role=null and keep looking exactly like before.
  const spritePath = (lead.role && SPRITE_PATH_BY_ROLE[lead.role]) || DEFAULT_SPRITE_PATH;
  const texture = useSpriteTexture(spritePath);

  const draw = useCallback(
    (g: Graphics) => {
      g.clear();
      g.roundRect(-WIDTH / 2, -HEIGHT, WIDTH, HEIGHT, WIDTH / 2);
      g.fill({ color: 0xf59e0b, alpha: 1 });
      g.stroke({ width: 4, color: lead.chatAvailable ? 0xffffff : 0x111827 });
    },
    [lead.chatAvailable],
  );

  const scale = texture ? HEIGHT / texture.height : 1;
  const label = lead.name ?? "Producer";

  return (
    <pixiContainer
      x={lead.position.x}
      y={lead.position.y}
      eventMode="static"
      cursor="pointer"
      onClick={onClick}
    >
      {texture ? (
        <pixiSprite
          texture={texture}
          anchor={{ x: 0.5, y: 1 }}
          scale={scale}
          tint={lead.chatAvailable ? 0xffffff : 0xaaaaaa}
        />
      ) : (
        <pixiGraphics draw={draw} />
      )}
      <pixiContainer y={-HEIGHT - 18} scale={0.5}>
        <pixiText
          text={label}
          anchor={0.5}
          style={{ fontSize: 24, fill: "#f8fafc", fontFamily: "monospace", fontWeight: "bold" }}
        />
      </pixiContainer>
      <pixiContainer y={-HEIGHT / 2} scale={0.5}>
        <pixiText
          text={lead.phase}
          anchor={0.5}
          style={{ fontSize: 20, fill: "#111827", fontFamily: "monospace" }}
        />
      </pixiContainer>
    </pixiContainer>
  );
}
