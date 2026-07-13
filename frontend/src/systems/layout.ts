// Named places in the office, hand-mapped from the background image
// (public/backgrounds/studio-office.png, 2816x1536 — coordinates below are
// in that image space, converted to stage space via the same cover-fit
// transform obstacles.ts uses). Three kinds of zones drive the whole
// "who's doing what" choreography:
//
//   WORK_SEATS      — the actual chairs at desks; an agent WORKING walks
//                     here and stays "seated" at their workstation.
//   THINKING_SPOTS  — open floor by the arch window; after picking up a
//                     task from the CEO an agent pauses here to "plan"
//                     before heading to their desk.
//   IDLE_SEATS      — the Aloha Brew bar stools, the wicker armchair, the
//                     spot beside the hammock; free agents hang out here,
//                     visibly away from the desks.
//
// The CEO stands on the round rug in the centre — workers walk to it to
// "receive" their task.
import { imageToStage } from "./obstacles";
import { nearestWalkable, stageToCell, cellToStage } from "./navigationGrid";
import { findPath } from "./astar";

function snappedStageSpot(ix: number, iy: number): { x: number; y: number } {
  const stage = imageToStage(ix, iy);
  const [gx, gy] = stageToCell(stage.x, stage.y);
  const [wgx, wgy] = nearestWalkable(gx, gy);
  return cellToStage(wgx, wgy);
}

// -- work seats: chairs at desks (image space) -------------------------
const WORK_SEATS_IMAGE_SPACE: { x: number; y: number }[] = [
  { x: 1176, y: 634 }, // Desk B, left chair (top-center double desk)
  { x: 1600, y: 745 }, // Desk C, chair between desk B and the aquarium desk
  { x: 725, y: 745 }, // Desk A, front-right chair
  { x: 397, y: 774 }, // Desk A, front-left chair
  { x: 876, y: 1337 }, // Desk D, chair (bottom-left desk)
];

// -- thinking / planning: open floor gaps between desk clusters ---------
// (each point checked against obstacles.ts's rects to land clear of every
// desk — nearestWalkable would silently rescue a point that overlapped
// furniture, but landing exactly on open floor keeps the "pause and think"
// pose from reading as "standing on the desk edge").
const THINKING_SPOTS_IMAGE_SPACE: { x: number; y: number }[] = [
  { x: 1408, y: 300 }, // open floor directly under the arch window
  { x: 1020, y: 500 }, // gap between Desk A and Desk B
  { x: 1870, y: 550 }, // gap between the center desk cluster and the bar
];

// -- idle: bar stools, armchair, hammock side ---------------------------
const IDLE_SEATS_IMAGE_SPACE: { x: number; y: number }[] = [
  { x: 2077, y: 1145 }, // bar stool 1
  { x: 2199, y: 1145 }, // bar stool 2
  { x: 2323, y: 1145 }, // bar stool 3
  { x: 2447, y: 1145 }, // bar stool 4
  { x: 2016, y: 383 }, // wicker armchair, top-right
  { x: 1500, y: 1390 }, // floor beside the hammock
];

const CEO_SPOT_IMAGE_SPACE = { x: 1401, y: 1190 }; // round rug, centre
const ENTRANCE_IMAGE_SPACE = { x: 1408, y: 359 }; // door mat under the arch window

export const WORK_SEATS = WORK_SEATS_IMAGE_SPACE.map((p) => snappedStageSpot(p.x, p.y));
export const THINKING_SPOTS = THINKING_SPOTS_IMAGE_SPACE.map((p) => snappedStageSpot(p.x, p.y));
export const IDLE_SEATS = IDLE_SEATS_IMAGE_SPACE.map((p) => snappedStageSpot(p.x, p.y));
export const CEO_SPOT = snappedStageSpot(CEO_SPOT_IMAGE_SPACE.x, CEO_SPOT_IMAGE_SPACE.y);
export const ENTRANCE_SPOT = snappedStageSpot(ENTRANCE_IMAGE_SPACE.x, ENTRANCE_IMAGE_SPACE.y);

// Back-compat aliases (devSlice/leadSlice's single-session view predates
// the zone system and thinks in "desks" + "producer spot").
export const DESK_SPOTS = WORK_SEATS;
export const PRODUCER_SPOT = CEO_SPOT;

export function gridSlot(index: number): { x: number; y: number } {
  return WORK_SEATS[index % WORK_SEATS.length];
}

export function deskForWorker(index: number): { x: number; y: number } {
  return WORK_SEATS[index % WORK_SEATS.length];
}

export function thinkingForWorker(index: number): { x: number; y: number } {
  return THINKING_SPOTS[index % THINKING_SPOTS.length];
}

export function idleForWorker(index: number): { x: number; y: number } {
  return IDLE_SEATS[index % IDLE_SEATS.length];
}

/** A* route between two arbitrary points, routed around furniture. Falls
 * back to a direct two-point line if A* can't find a route (shouldn't
 * happen with the current obstacle map, but a straight line beats a crash
 * if the map ever changes and orphans a cell). */
export function pathBetween(
  from: { x: number; y: number },
  to: { x: number; y: number },
): { x: number; y: number }[] {
  const path = findPath(from.x, from.y, to.x, to.y);
  return path ?? [from, to];
}

/** Path from the entrance to a target (kept for the original arrival flow). */
export function pathToSpot(target: { x: number; y: number }): { x: number; y: number }[] {
  return pathBetween(ENTRANCE_SPOT, target);
}
