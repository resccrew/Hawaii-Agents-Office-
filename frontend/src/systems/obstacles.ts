// Obstacle map for the office background (public/backgrounds/studio-office.png,
// 1024x559 source). Rectangles are hand-mapped from the image (desks, the
// Aloha Brew bar, the hammock stand, shelving units) — furniture agents
// must walk around rather than through. Decorative wall-adjacent plants
// aren't individually boxed; a perimeter margin (see WALKABLE_BOUNDS)
// keeps agents off the walls generally, which covers most of them.

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const BG_IMAGE_WIDTH = 1024;
export const BG_IMAGE_HEIGHT = 559;

export const STAGE_WIDTH = 960;
export const STAGE_HEIGHT = 640;

// Cover-fit transform — must match OfficeBackground's scaling in
// StudioGame.tsx exactly, since obstacle coordinates are meaningless if
// this drifts out of sync with how the image is actually drawn.
const BG_SCALE = Math.max(STAGE_WIDTH / BG_IMAGE_WIDTH, STAGE_HEIGHT / BG_IMAGE_HEIGHT);
const BG_OFFSET_X = (STAGE_WIDTH - BG_IMAGE_WIDTH * BG_SCALE) / 2;
const BG_OFFSET_Y = (STAGE_HEIGHT - BG_IMAGE_HEIGHT * BG_SCALE) / 2;

export function imageToStage(ix: number, iy: number): { x: number; y: number } {
  return { x: ix * BG_SCALE + BG_OFFSET_X, y: iy * BG_SCALE + BG_OFFSET_Y };
}

// Image-space obstacle rectangles (furniture clusters).
const OBSTACLES_IMAGE_SPACE: Rect[] = [
  { x: 95, y: 130, w: 235, h: 170 }, // Desk A — top-left double desk + chairs
  { x: 430, y: 140, w: 220, h: 130 }, // Desk B — mixer/monitor desk
  { x: 435, y: 245, w: 215, h: 115 }, // Desk C — aquarium desk
  { x: 90, y: 345, w: 270, h: 125 }, // Desk D — bottom-left single desk
  { x: 720, y: 160, w: 190, h: 270 }, // Aloha Brew bar + stools
  { x: 560, y: 425, w: 205, h: 115 }, // Hammock stand
  { x: 790, y: 450, w: 155, h: 90 }, // Shelf/speaker unit, bottom-right
  { x: 950, y: 245, w: 74, h: 90 }, // Corner shelf/statue, right wall
];

export function obstaclesInStageSpace(): Rect[] {
  return OBSTACLES_IMAGE_SPACE.map((r) => {
    const topLeft = imageToStage(r.x, r.y);
    return { x: topLeft.x, y: topLeft.y, w: r.w * BG_SCALE, h: r.h * BG_SCALE };
  });
}

// Keep agents off the wall trim generally (catches the many small
// wall-adjacent plants without boxing each one individually).
export const WALKABLE_BOUNDS: Rect = { x: 40, y: 40, w: STAGE_WIDTH - 80, h: STAGE_HEIGHT - 80 };
