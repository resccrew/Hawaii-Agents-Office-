import type { DevState, LeadState, Position, DevRole } from "@/lib/types";

// Visual animation phase, separate from backend DevState — this is what lets
// processBackendState() update backendState without clobbering an in-flight
// walk/arrival animation (ported pattern from claude-office's
// AgentAnimationState / processBackendState reconciliation).
export type DevPhase =
  | "arriving"
  | "walking"
  | "working"
  | "leaving"
  | "idle";

export interface DevAnimationState {
  id: string;
  name: string | null;
  color: string;
  number: number;
  role: DevRole;
  backendState: DevState;
  phase: DevPhase;
  position: Position;
  targetPosition: Position | null;
  // Waypoints from entrance to desk, routed around furniture by A* —
  // DevCapsule steps `position` along these each frame instead of
  // snapping directly to targetPosition. Empty once arrived.
  path: Position[];
  currentTask: string | null;
  chatAvailable: boolean;
}

export interface LeadAnimationState {
  backendState: LeadState;
  phase: "idle" | "working" | "delegating";
  position: Position;
  currentTask: string | null;
  chatAvailable: boolean;
}
