// Obstacle map for the office background (public/backgrounds/studio-office.png,
// 2816x1536 source — the CURRENT image; an earlier 1024x559 version was
// replaced and this file's rects were re-mapped against the new art).
// Rectangles are hand-mapped furniture agents must walk around rather than
// through: desks, the aquarium block, surfboards standing on the floor, the
// Aloha Brew bar, the hammock, shelving. Chairs/stools are deliberately NOT
// obstacles — they're the seats agents walk to and "occupy" (see layout.ts
// WORK_SEATS / IDLE_SEATS). Wall-adjacent decor is covered by the perimeter
// margin (WALKABLE_BOUNDS) plus the cover-fit crop (the outer ~256px of the
// image on each side never reach the stage at all).

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const BG_IMAGE_WIDTH = 2816;
export const BG_IMAGE_HEIGHT = 1536;

export const STAGE_WIDTH = 1200;
export const STAGE_HEIGHT = 800;

// Cover-fit transform — must match OfficeBackground's scaling in
// StudioGame.tsx exactly, since obstacle coordinates are meaningless if
// this drifts out of sync with how the image is actually drawn.
const BG_SCALE = Math.max(STAGE_WIDTH / BG_IMAGE_WIDTH, STAGE_HEIGHT / BG_IMAGE_HEIGHT);
const BG_OFFSET_X = (STAGE_WIDTH - BG_IMAGE_WIDTH * BG_SCALE) / 2;
const BG_OFFSET_Y = (STAGE_HEIGHT - BG_IMAGE_HEIGHT * BG_SCALE) / 2;

export function imageToStage(ix: number, iy: number): { x: number; y: number } {
  return { x: ix * BG_SCALE + BG_OFFSET_X, y: iy * BG_SCALE + BG_OFFSET_Y };
}

// Image-space obstacle rectangles (furniture), 2816x1536 space.
const OBSTACLES_IMAGE_SPACE: Rect[] = [
  { x: 260, y: 370, w: 580, h: 334 }, // Desk A — top-left double desk (front chairs left walkable as seats)
  { x: 1211, y: 437, w: 521, h: 225 }, // Desk B — top-center double-monitor desk
  { x: 1204, y: 662, w: 331, h: 324 }, // Desk C1 — aquarium + left part of the aquarium desk
  { x: 1535, y: 838, w: 204, h: 148 }, // Desk C2 — right part of the aquarium desk (chair notch above stays open)
  { x: 275, y: 1140, w: 556, h: 338 }, // Desk D — bottom-left desk (its chair on the right is a seat)
  { x: 289, y: 1049, w: 105, h: 95 }, // dark chair behind Desk D (faces away — decor, not a seat)
  { x: 553, y: 779, w: 106, h: 366 }, // standing surfboard (blue), mid-left
  { x: 828, y: 855, w: 118, h: 353 }, // standing surfboard (orange), mid-left
  { x: 2000, y: 493, w: 600, h: 577 }, // Aloha Brew bar (U-counter + back bar + speaker; stools below are seats)
  { x: 1570, y: 1260, w: 500, h: 218 }, // hammock
  { x: 2175, y: 1295, w: 409, h: 239 }, // bottom-right shelf + speakers
  { x: 1042, y: 1239, w: 127, h: 275 }, // potted plants, bottom-center
  { x: 465, y: 1246, w: 148, h: 275 }, // potted plant right of Desk D
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
