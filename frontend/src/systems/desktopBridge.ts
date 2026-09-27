"use client";

import { useChatStore } from "@/stores/chatStore";
import { useRoomStore, type RoomSessionState } from "@/stores/roomStore";
import { useActivityLogStore } from "@/stores/activityLogStore";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import { DEFAULT_UI_SETTINGS } from "@/stores/uiSettingsStore";

// Bridges the existing WS-fed stores (roomStore, activityLogStore) to the
// desktop-native affordances added in src-tauri/src/lib.rs: notifications,
// dock badge, tray menu, global hotkey. Deliberately does NOT open its own
// WebSocket connection — /ws/overview is already connected by
// roomSocketController.connectOverview() (see app/page.tsx) and roomStore
// is the shared, authoritative view of every live session; duplicating that
// connection here would just be two sources of truth for the same data.
//
// No-ops completely outside a packaged/dev Tauri window (plain browser
// `next dev`) — every native call goes through `invokeTauri`, which returns
// undefined when `window.__TAURI__` isn't present, same pattern as
// apiAuth.ts's `getApiToken`.

function tauriBridge() {
  if (typeof window === "undefined") return null;
  return window.__TAURI__ ?? null;
}

async function invokeTauri<T>(cmd: string, args?: Record<string, unknown>): Promise<T | undefined> {
  const bridge = tauriBridge();
  if (!bridge?.core) return undefined;
  try {
    return await bridge.core.invoke<T>(cmd, args);
  } catch (err) {
    console.error(`desktopBridge: invoke("${cmd}") failed`, err);
    return undefined;
  }
}

// Lead states that count as "the agent is actively doing something" for
// notification/badge purposes — anything not in this set and not
// "waiting_permission" is treated as idle. Mirrors the LeadState union in
// lib/types.ts.
const LEAD_ACTIVE_STATES = new Set([
  "receiving",
  "working",
  "delegating",
  "reviewing",
  "completing",
  "on_phone",
  "phone_ringing",
]);

interface WaitingAgent {
  sessionId: string;
  label: string;
  since: number; // Date.now() of when it first entered waiting_permission.
}

// Per-session bookkeeping the diffing loop needs across ticks — module
// level (like activityLogStore's seenCount) since it's derived bookkeeping,
// not UI state any component renders directly.
const prevLeadState = new Map<string, string>();
const waitingSince = new Map<string, number>();
const lastNotifiedAt = new Map<string, number>(); // key: `${kind}:${sessionId}`

// Don't notify more than once per this window for the same (kind, session)
// pair — a flapping connection or a burst of tool-use events shouldn't
// turn into a burst of OS notifications for the same underlying fact.
const NOTIFY_THROTTLE_MS = 30_000;

function shouldNotify(kind: string, sessionId: string): boolean {
  const key = `${kind}:${sessionId}`;
  const last = lastNotifiedAt.get(key) ?? 0;
  const now = Date.now();
  if (now - last < NOTIFY_THROTTLE_MS) return false;
  lastNotifiedAt.set(key, now);
  return true;
}

function labelFor(session: RoomSessionState): string {
  return session.lead.name || session.lead.role || `session ${session.sessionId.slice(0, 8)}`;
}

function notify(title: string, body: string) {
  if (!useUiSettingsStore.getState().desktopNotificationsEnabled) return;
  void invokeTauri("show_agent_notification", { title, body });
}

function pushTrayAndBadge(waiting: WaitingAgent[], workingCount: number) {
  void invokeTauri("set_waiting_badge_count", { count: waiting.length });
  void invokeTauri("update_tray_status", {
    working: workingCount,
    waiting: waiting.length,
    agents: waiting
      .slice()
      .sort((a, b) => a.since - b.since) // longest-waiting first in the menu too
      .map((w) => ({ id: w.sessionId, label: w.label })),
  });
}

function handleRoomSnapshot(sessions: Map<string, RoomSessionState>) {
  const waiting: WaitingAgent[] = [];
  let workingCount = 0;

  for (const session of sessions.values()) {
    const { sessionId } = session;
    const state = session.lead.state;
    const prev = prevLeadState.get(sessionId);

    if (state === "waiting_permission") {
      if (!waitingSince.has(sessionId)) waitingSince.set(sessionId, Date.now());
      waiting.push({ sessionId, label: labelFor(session), since: waitingSince.get(sessionId)! });
      if (prev !== "waiting_permission" && shouldNotify("permission", sessionId)) {
        notify("Ждёт разрешения", `Агент ${labelFor(session)} ждёт разрешения`);
      }
    } else {
      waitingSince.delete(sessionId);
      if (LEAD_ACTIVE_STATES.has(state)) workingCount += 1;
      // "Finished a task" = was actively working, is now idle. Only fires
      // once prevLeadState has a recorded value for this session, so the
      // very first snapshot after connecting (or a freshly spawned agent
      // starting from "idle") never fires a false "finished" notification.
      if (prev !== undefined && prev !== state && state === "idle" && LEAD_ACTIVE_STATES.has(prev)) {
        if (shouldNotify("done", sessionId)) {
          notify("Задача завершена", `Агент ${labelFor(session)} закончил задачу`);
        }
      }
    }

    prevLeadState.set(sessionId, state);
  }

  // Drop bookkeeping for sessions that disappeared (session_deleted) so
  // these Maps don't grow forever across a long-running app session.
  for (const key of prevLeadState.keys()) {
    if (!sessions.has(key)) {
      prevLeadState.delete(key);
      waitingSince.delete(key);
    }
  }

  pushTrayAndBadge(waiting, workingCount);
  return waiting;
}

// Latest computed waiting list, kept for the hotkey handler ("open the
// most-overdue waiting agent") without recomputing from roomStore again —
// handleRoomSnapshot already produced it on every store change.
let latestWaiting: WaitingAgent[] = [];

function openMostOverdueWaitingAgent() {
  if (latestWaiting.length === 0) return;
  const oldest = latestWaiting.reduce((a, b) => (a.since <= b.since ? a : b));
  useChatStore.getState().openPanel(oldest.sessionId);
}

let started = false;
let unlistenTrayAgent: (() => void) | null = null;
let unlistenHotkey: (() => void) | null = null;

/** Wires roomStore/activityLogStore into the native side. Call once, e.g.
 * from app/page.tsx alongside connectOverview() — idempotent, so a
 * double-mount (React strict mode) is harmless. */
export function startDesktopBridge(): () => void {
  if (started) return () => {};
  started = true;

  const unsubRoom = useRoomStore.subscribe((state) => {
    latestWaiting = handleRoomSnapshot(state.sessions);
  });
  // Fire once immediately for whatever's already connected (e.g. hot
  // reload, or the bridge starting after the first WS snapshot arrived).
  latestWaiting = handleRoomSnapshot(useRoomStore.getState().sessions);

  let seenLogCount = 0;
  const unsubLog = useActivityLogStore.subscribe((state) => {
    const fresh = state.entries.slice(seenLogCount);
    seenLogCount = state.entries.length;
    for (const entry of fresh) {
      if (entry.type !== "error") continue;
      const label = entry.agentName || entry.agentId;
      if (!shouldNotify("error", entry.agentId)) continue;
      notify("Ошибка агента", `${label}: ${entry.summary}`.slice(0, 200));
    }
  });

  void invokeTauri("set_global_shortcut", { shortcut: useUiSettingsStore.getState().desktopHotkey });

  const bridge = tauriBridge();
  if (bridge?.event) {
    void bridge.event.listen<string>("tray-open-agent", (e) => {
      useChatStore.getState().openPanel(e.payload);
    }).then((un) => {
      unlistenTrayAgent = un;
    });
    void bridge.event.listen<void>("hotkey-open-waiting", () => {
      openMostOverdueWaitingAgent();
    }).then((un) => {
      unlistenHotkey = un;
    });
  }

  return () => {
    started = false;
    unsubRoom();
    unsubLog();
    unlistenTrayAgent?.();
    unlistenHotkey?.();
  };
}

/** Called from SettingsModal when the user changes the hotkey field —
 * re-registers on the Rust side (unregistering the previous combo first)
 * and never throws into the UI: a bad/conflicting combo just logs and
 * leaves the previous one (or none) registered, per the "don't crash on a
 * hotkey conflict" requirement. */
export async function applyDesktopHotkey(next: string, previous: string): Promise<string | null> {
  if (!tauriBridge()?.core) return null; // plain browser dev session — nothing to register
  const bridge = window.__TAURI__!.core!;
  try {
    await bridge.invoke("set_global_shortcut", { shortcut: next || DEFAULT_UI_SETTINGS.desktopHotkey, previous });
    return null;
  } catch (err) {
    return err instanceof Error ? err.message : "could not register that shortcut (it may already be in use)";
  }
}
