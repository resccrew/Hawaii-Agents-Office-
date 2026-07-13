"use client";

import { useSpriteTexture } from "@/systems/useSpriteTexture";

export const STAGE_WIDTH = 1200;
export const STAGE_HEIGHT = 800;
const BACKGROUND_PATH = "/backgrounds/studio-office.png";

// User-supplied hand-painted office background. Cover-fit: scale up until it
// fills the stage on both axes, then center-crop the overflow (source is
// 1024x559, narrower than the 1200x800 stage) so nothing stretches out of
// pixel-art proportion. Shared by RoomGame — the single-session StudioGame
// view it originally belonged to was retired when the studio became one
// shared room (see RoomGame). Kept here as the canonical background +
// stage-dimension source the rest of the scene imports.
export function OfficeBackground() {
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
