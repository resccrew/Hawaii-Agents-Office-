// Desk/workstation positions, hand-mapped from the office background
// image (public/backgrounds/studio-office.png) — one spot per visible
// chair/desk cluster, converted from image-space to stage-space via the
// same cover-fit transform obstacles.ts uses. Four desks match the four
// DevRole roles exactly; the fifth spot (round rug, open floor near the
// Aloha Brew bar) is the Producer/Lead's spot.
import { imageToStage } from "./obstacles";
import { nearestWalkable, stageToCell, cellToStage } from "./navigationGrid";
import { findPath } from "./astar";

const DESK_SPOTS_IMAGE_SPACE: { x: number; y: number }[] = [
  { x: 150, y: 175 }, // Desk A, left chair
  { x: 578, y: 225 }, // Desk B, mixer desk chair
  { x: 595, y: 300 }, // Desk C, aquarium desk chair
  { x: 230, y: 415 }, // Desk D, bottom-left desk chair
];

const PRODUCER_SPOT_IMAGE_SPACE = { x: 510, y: 420 }; // round rug, open floor

const ENTRANCE_IMAGE_SPACE = { x: 510, y: 140 }; // open floor under the arch window

function snappedStageSpot(ix: number, iy: number): { x: number; y: number } {
  const stage = imageToStage(ix, iy);
  const [gx, gy] = stageToCell(stage.x, stage.y);
  const [wgx, wgy] = nearestWalkable(gx, gy);
  return cellToStage(wgx, wgy);
}

export const DESK_SPOTS = DESK_SPOTS_IMAGE_SPACE.map((p) => snappedStageSpot(p.x, p.y));
export const PRODUCER_SPOT = snappedStageSpot(PRODUCER_SPOT_IMAGE_SPACE.x, PRODUCER_SPOT_IMAGE_SPACE.y);
export const ENTRANCE_SPOT = snappedStageSpot(ENTRANCE_IMAGE_SPACE.x, ENTRANCE_IMAGE_SPACE.y);

export function gridSlot(index: number): { x: number; y: number } {
  return DESK_SPOTS[index % DESK_SPOTS.length];
}

/** Path from the entrance to a target, routed around furniture. Falls
 * back to a direct two-point line if A* can't find a route (shouldn't
 * happen with the current obstacle map, but a straight line beats a
 * crash if the map ever changes and orphans a cell). */
export function pathToSpot(target: { x: number; y: number }): { x: number; y: number }[] {
  const path = findPath(ENTRANCE_SPOT.x, ENTRANCE_SPOT.y, target.x, target.y);
  return path ?? [ENTRANCE_SPOT, target];
}
