// Mirrors backend/app/models/{agents,sessions,common}.py wire format
// (Pydantic to_camel alias_generator, model_dump(by_alias=True)).

export type DevState =
  | "arriving"
  | "reporting"
  | "walking_to_desk"
  | "working"
  | "thinking"
  | "waiting_permission"
  | "completed"
  | "waiting"
  | "reporting_done"
  | "leaving"
  | "in_elevator"
  | "idle";

export type LeadState =
  | "idle"
  | "phone_ringing"
  | "on_phone"
  | "receiving"
  | "working"
  | "delegating"
  | "waiting_permission"
  | "reviewing"
  | "completing";

export type DevRole =
  | "programmer"
  | "game_designer"
  | "artist"
  | "qa_tester"
  | "producer";

export interface BubbleContent {
  type: "thought" | "speech";
  text: string;
  icon?: string | null;
  persistent: boolean;
}

export interface Position {
  x: number;
  y: number;
}

export interface Dev {
  id: string;
  nativeId?: string | null;
  name?: string | null;
  color: string;
  number: number;
  role: DevRole;
  state: DevState;
  desk?: number | null;
  bubble?: BubbleContent | null;
  currentTask?: string | null;
  position: Position;
  characterType?: string | null;
  parentSessionId?: string | null;
  parentId?: string | null;
  chatAvailable: boolean;
}

export interface Lead {
  state: LeadState;
  currentTask?: string | null;
  bubble?: BubbleContent | null;
  position: Position;
  chatAvailable: boolean;
}

export interface StudioState {
  deskCount: number;
  standupState: "closed" | "arriving" | "open" | "departing";
  buildState: "idle" | "ringing" | "in_use";
  contextUtilization: number;
  toolUsesSinceCompaction: number;
  printReport: boolean;
}

export interface ConversationEntry {
  id: string;
  role: "user" | "assistant" | "thinking" | "tool";
  agentId: string;
  text: string;
  timestamp: string;
  source?: "interactive" | "chat";
  toolName?: string;
}

export interface HistoryEntry {
  id: string;
  type: string;
  agentId: string;
  summary: string;
  timestamp: string;
  detail: Record<string, unknown>;
}

export interface GameState {
  sessionId: string;
  lead: Lead;
  devs: Dev[];
  studio: StudioState;
  lastUpdated: string;
  history: HistoryEntry[];
  todos: unknown[];
  arrivalQueue: string[];
  departureQueue: string[];
  conversation: ConversationEntry[];
  departmentId?: string | null;
  roomId?: string | null;
}

export interface WebSocketMessage {
  type: "state_update" | "event" | "reload" | "session_deleted" | "error";
  timestamp: string;
  session_id?: string;
  state?: GameState;
  message?: string;
}
