import type { Position } from "@/lib/types";
import { pathBetween } from "./layout";
import { nearestWalkable, stageToCell, cellToStage } from "./navigationGrid";

// Movement for Task-tool subagents (rendered as cats — see CatCapsule.tsx)
// spawned WITHIN a Lead's session. Unlike officeMovement.ts's Leads (which
// travel across the whole office: lounge → CEO → desk), a cat never leaves
// its owner's side — it either curls up right next to them (idle) or paces
// a small radius around them (working), re-anchoring whenever the owner
// moves somewhere new. This is deliberately simple (no A* stop/dwell
// choreography) since a cat is flavor conveying "something is happening
// here", not a character with its own errands.

export interface CatPlan {
  position: Position; // where the walk starts (the cat's previous location)
  path: Position[];
  targetKey: string; // identity — capsule only re-walks when this changes
  label: string; // status text shown under the cat
}

interface CatMemo {
  lastPos: Position;
  plan: CatPlan;
  nextWanderAt: number; // ms timestamp; only meaningful while busy
}

const memo = new Map<string, CatMemo>();

const SIT_RADIUS = 40; // curled up right beside the owner
const WANDER_RADIUS = 60; // pacing distance while the owner is working
const WANDER_INTERVAL_MS: [number, number] = [4000, 9000];
const OWNER_DRIFT_TOLERANCE = 130; // re-anchor if the owner wanders this far off

function randomOffset(center: Position, radius: number): Position {
  const angle = Math.random() * Math.PI * 2;
  const dist = radius * (0.35 + Math.random() * 0.65);
  return { x: center.x + Math.cos(angle) * dist, y: center.y + Math.sin(angle) * dist };
}

function snapWalkable(p: Position): Position {
  const [gx, gy] = stageToCell(p.x, p.y);
  const [wgx, wgy] = nearestWalkable(gx, gy);
  return cellToStage(wgx, wgy);
}

/** `catId` should be stable per subagent (Dev.id). `ownerPos` is the
 * owner Lead's current stage-space position (its latest walk target — see
 * officeMovement.ts's lastTargetOf). `busy` mirrors the Dev's own backend
 * state (WORKING vs IDLE/WAITING/ARRIVING/LEAVING collapse to "sitting"). */
export function planForCat(catId: string, ownerPos: Position, busy: boolean): CatPlan {
  const now = Date.now();
  const existing = memo.get(catId);

  if (!busy) {
    // Idle: sit near the owner. Only re-path when the owner has actually
    // moved to a new spot (bucketed so small jitter doesn't cause a
    // constant twitchy re-seat).
    const bucket = `${Math.round(ownerPos.x / 24)}:${Math.round(ownerPos.y / 24)}`;
    const targetKey = `sit:${bucket}`;
    if (existing && existing.plan.targetKey === targetKey) return existing.plan;

    const seat = snapWalkable(randomOffset(ownerPos, SIT_RADIUS));
    const from = existing?.lastPos ?? seat;
    const plan: CatPlan = { position: from, path: pathBetween(from, seat), targetKey, label: "curled up" };
    memo.set(catId, { lastPos: seat, plan, nextWanderAt: 0 });
    return plan;
  }

  // Working: pace a little loop near the owner, picking a fresh nearby spot
  // periodically so it visibly keeps busy instead of freezing in place —
  // and re-anchoring immediately if the owner has moved on without it.
  const driftedTooFar =
    existing && Math.hypot(existing.lastPos.x - ownerPos.x, existing.lastPos.y - ownerPos.y) > OWNER_DRIFT_TOLERANCE;
  const dueForWander = !existing || now >= existing.nextWanderAt;

  if (!existing || dueForWander || driftedTooFar) {
    const dest = snapWalkable(randomOffset(ownerPos, WANDER_RADIUS));
    const from = existing?.lastPos ?? dest;
    const targetKey = `wander:${Math.round(dest.x)}:${Math.round(dest.y)}:${now}`;
    const plan: CatPlan = { position: from, path: pathBetween(from, dest), targetKey, label: "pacing" };
    const [lo, hi] = WANDER_INTERVAL_MS;
    memo.set(catId, { lastPos: dest, plan, nextWanderAt: now + lo + Math.random() * (hi - lo) });
    return plan;
  }

  return existing.plan;
}

/** Drop movement memory for a subagent that finished/left, so a reused id
 * doesn't inherit a stale position. */
export function forgetCat(catId: string): void {
  memo.delete(catId);
}
