import type { DevState } from "@/lib/types";
import type { DevPhase } from "@/stores/slices/types";

// Ported in spirit from claude-office's agentMachine.ts phase graph
// (arriving -> walking -> working -> leaving), renamed to studio theme.
// v1 (Phase 2 of the studio-ops plan) drives phase directly off the backend
// DevState rather than a full XState machine with pathfinding-triggered
// transitions — pathfinding/A* wiring is deferred until placeholder-Graphics
// visualization is proven end-to-end, per the approved plan.
export function phaseForDevState(state: DevState): DevPhase {
  switch (state) {
    case "arriving":
    case "reporting":
      return "arriving";
    case "walking_to_desk":
    case "in_elevator":
      return "walking";
    case "working":
    case "thinking":
    case "waiting_permission":
    case "waiting":
      return "working";
    case "leaving":
    case "reporting_done":
      return "leaving";
    case "completed":
    case "idle":
      return "idle";
    default:
      return "idle";
  }
}
