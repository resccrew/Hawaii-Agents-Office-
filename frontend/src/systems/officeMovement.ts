import type { Position } from "@/lib/types";
import {
  CEO_SPOT,
  deskForWorker,
  idleForWorker,
  thinkingForWorker,
  pathBetween,
} from "./layout";

// Per-agent movement planner. Turns "this agent is busy / idle" into an
// A*-routed walk through the office's named zones, and remembers where each
// agent last headed so the NEXT walk starts from there (continuity). The
// plan object is memoized per session and only rebuilt when the target
// actually changes (busy↔idle) — LeadCapsule resets its walk animation on
// plan identity (targetKey) change, so a stable reference while nothing
// changed is what keeps it from re-walking every render.
//
// Busy trip (the full pantomime, so work is legible at a glance):
//   lounge → CEO's rug ("getting task") → window ("planning") → desk chair
//   ("working").
// Idle trip: wherever they are → a bar stool / armchair / hammock spot.

export type ArrivedPhase = "working" | "idle" | "coordinating";

export interface PlanStop {
  index: number; // waypoint index to pause at
  ms: number; // how long to dwell
  label: string; // status label shown while dwelling
}

export interface OfficePlan {
  position: Position; // where the walk starts (the agent's previous location)
  path: Position[]; // waypoints to step through
  stops: PlanStop[]; // pauses along the way (CEO visit, planning by the window)
  arrivedPhase: ArrivedPhase; // label/pose once the path is finished
  targetKey: string; // identity — capsule re-walks only when this changes
}

interface AgentMemo {
  lastTarget: Position;
  plan: OfficePlan;
}

const memo = new Map<string, AgentMemo>();

export interface AgentInput {
  sessionId: string;
  isCeo: boolean;
  workerIndex: number; // 0-based among non-CEO agents (stable → stable desk)
  busy: boolean;
}

export function planFor({ sessionId, isCeo, workerIndex, busy }: AgentInput): OfficePlan {
  const existing = memo.get(sessionId);

  // CEO: stationary on the centre rug. Only the pose label changes.
  if (isCeo) {
    const targetKey = `ceo:${busy ? "busy" : "idle"}`;
    if (existing && existing.plan.targetKey === targetKey) return existing.plan;
    const plan: OfficePlan = {
      position: CEO_SPOT,
      path: [CEO_SPOT],
      stops: [],
      arrivedPhase: busy ? "coordinating" : "idle",
      targetKey,
    };
    memo.set(sessionId, { lastTarget: CEO_SPOT, plan });
    return plan;
  }

  const targetKey = busy ? "busy" : "idle";
  if (existing && existing.plan.targetKey === targetKey) return existing.plan;

  const desk = deskForWorker(workerIndex);
  const think = thinkingForWorker(workerIndex);
  const lounge = idleForWorker(workerIndex);
  const from = existing?.lastTarget ?? lounge; // first appearance: start at the lounge

  let path: Position[];
  const stops: PlanStop[] = [];
  let finalTarget: Position;
  let arrivedPhase: ArrivedPhase;

  if (busy) {
    // lounge → CEO (get the task) → window (plan it) → desk (do it).
    const toCeo = pathBetween(from, CEO_SPOT);
    const toThink = pathBetween(CEO_SPOT, think);
    const toDesk = pathBetween(think, desk);
    stops.push({ index: toCeo.length - 1, ms: 900, label: "getting task" });
    stops.push({ index: toCeo.length + toThink.length - 2, ms: 2400, label: "planning" });
    path = [...toCeo, ...toThink.slice(1), ...toDesk.slice(1)];
    finalTarget = desk;
    arrivedPhase = "working";
  } else {
    path = pathBetween(from, lounge);
    finalTarget = lounge;
    arrivedPhase = "idle";
  }

  const plan: OfficePlan = {
    position: path[0] ?? from,
    path,
    stops,
    arrivedPhase,
    targetKey,
  };
  memo.set(sessionId, { lastTarget: finalTarget, plan });
  return plan;
}

/** Where this agent is (headed) right now, in stage space — used to anchor
 * its chat window near the character instead of a stale fixed slot. */
export function lastTargetOf(sessionId: string): Position | null {
  return memo.get(sessionId)?.lastTarget ?? null;
}

/** Drop movement memory for an agent that left, so a re-used session id
 * doesn't inherit a stale start position. */
export function forgetAgent(sessionId: string): void {
  memo.delete(sessionId);
}
