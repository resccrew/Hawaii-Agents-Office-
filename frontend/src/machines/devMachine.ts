import type { DevState } from "@/lib/types";
import type { DevPhase } from "@/stores/slices/types";

// Ported in spirit from claude-office's agentMachine.ts phase graph
// (arriving -> walking -> working -> leaving), renamed to studio theme.
// Plain function, not a state machine library: it maps the backend's
// DevState directly onto a DevPhase for rendering. There is no `xstate`
// dependency in this project (removed — it was listed in package.json but
// never imported/called anywhere, see PR history) and no plan to add one;
// if pathfinding-triggered transitions ever need real guards/side-effects
// beyond this switch, reach for a plain reducer here before reaching for a
// state-machine library.
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
