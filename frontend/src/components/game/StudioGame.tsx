"use client";

import { Application, extend } from "@pixi/react";
import { Container, Graphics, Sprite, Text } from "pixi.js";
import { useGameStore, selectDevs, selectLead } from "@/stores/gameStore";
import { useSpriteTexture } from "@/systems/useSpriteTexture";
import { gridSlot } from "@/systems/layout";
import { DevCapsule } from "./DevCapsule";
import { LeadCapsule } from "./LeadCapsule";

extend({ Container, Graphics, Sprite, Text });

const DEPARTMENTS = ["Engineering", "Art", "Design", "QA"];

const STAGE_WIDTH = 960;
const STAGE_HEIGHT = 640;
const BACKGROUND_PATH = "/backgrounds/studio-office.png";

// User-supplied hand-painted isometric office background. Cover-fit: scale
// up until it fills the stage on both axes, then center-crop the
// overflow (source is 1024x559, wider than the 960x640 stage) so nothing
// stretches out of pixel-art proportion.
function OfficeBackground() {
  const texture = useSpriteTexture(BACKGROUND_PATH);
  if (!texture) return null;
  const scale = Math.max(STAGE_WIDTH / texture.width, STAGE_HEIGHT / texture.height);
  const w = texture.width * scale;
  const h = texture.height * scale;
  return (
    <pixiSprite
      texture={texture}
      x={(STAGE_WIDTH - w) / 2}
      y={(STAGE_HEIGHT - h) / 2}
      width={w}
      height={h}
    />
  );
}

function DepartmentLabels() {
  return (
    <>
      {DEPARTMENTS.map((name, i) => (
        <pixiContainer key={name} x={gridSlot(i).x} y={gridSlot(i).y - 60} scale={0.5}>
          <pixiText
            text={name}
            anchor={0.5}
            style={{
              fontSize: 18,
              fill: "#fff7e6",
              fontFamily: "monospace",
              fontWeight: "bold",
              stroke: { color: "#2b1b3d", width: 4 },
            }}
          />
        </pixiContainer>
      ))}
    </>
  );
}

export function StudioGame({
  onDevClick,
  onLeadClick,
}: {
  onDevClick?: (id: string) => void;
  onLeadClick?: () => void;
}) {
  const devs = useGameStore(selectDevs);
  const lead = useGameStore(selectLead);

  return (
    <Application width={STAGE_WIDTH} height={STAGE_HEIGHT} background="#1a1030">
      <pixiContainer>
        <OfficeBackground />
        <DepartmentLabels />
        {Array.from(devs.values()).map((dev) => (
          <DevCapsule key={dev.id} dev={dev} onClick={onDevClick} />
        ))}
        <LeadCapsule lead={lead} onClick={onLeadClick} />
      </pixiContainer>
    </Application>
  );
}
