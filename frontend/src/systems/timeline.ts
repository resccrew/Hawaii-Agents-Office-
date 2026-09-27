"use client";

import type { HistoryEntry } from "@/lib/types";
import { authedFetch } from "./apiAuth";
import { getHttpBase } from "./backendUrl";

// Pure helpers behind the Timeline/Replay feature (components/timeline/Timeline.tsx).
// Kept free of React/zustand so they're trivial to reason about and to
// exercise with `tsc --noEmit` alone (no test runner configured on this
// frontend — see CLAUDE.md). All time math works on epoch milliseconds
// derived from HistoryEntry.timestamp (an ISO string from the backend).

/** Coarse category used for tick color + tooltip grouping. Anything not
 * explicitly listed falls into "other" rather than throwing, since hooks
 * add new event_type values over time (see backend EventType). */
export type TimelineCategory = "session" | "tool" | "permission" | "subagent" | "error" | "other";

const CATEGORY_BY_TYPE: Record<string, TimelineCategory> = {
  session_start: "session",
  session_end: "session",
  stop: "session",
  pre_tool_use: "tool",
  post_tool_use: "tool",
  permission_request: "permission",
  notification: "permission",
  subagent_start: "subagent",
  subagent_info: "subagent",
  subagent_stop: "subagent",
  agent_update: "subagent",
  cleanup: "subagent",
  error: "error",
};

export function categoryForType(type: string): TimelineCategory {
  return CATEGORY_BY_TYPE[type] ?? "other";
}

// Design-system colors (see globals.css) — read as CSS var names, resolved
// by the component at render time, not hardcoded hex here, so a theme
// change doesn't require touching this file.
export const CATEGORY_COLOR_VAR: Record<TimelineCategory, string> = {
  session: "--ocean",
  tool: "--text-2",
  permission: "--sunset-2",
  subagent: "--sunset",
  error: "--sunset",
  other: "--text-3",
};

export function eventTimeMs(entry: HistoryEntry): number {
  const ms = Date.parse(entry.timestamp);
  return Number.isNaN(ms) ? 0 : ms;
}

/** True once `entry` is at least the current head of the buffer, i.e. the
 * scrubber sitting on the last event and the user hasn't dragged it back —
 * the condition the "Live" button toggles. A small epsilon protects against
 * float/parse jitter between the selected timestamp and the true latest one. */
export function isAtLiveEdge(selectedMs: number, latestMs: number): boolean {
  if (latestMs === 0) return true;
  return latestMs - selectedMs <= 250;
}

/** Binary search for the index of the latest entry whose time is <= targetMs.
 * Entries are assumed sorted oldest-first (true both for the REST endpoint's
 * response and for activityLogStore's incremental append). Returns -1 if
 * every entry is after targetMs (nothing to show yet). */
export function indexAtOrBefore(entries: HistoryEntry[], targetMs: number): number {
  let lo = 0;
  let hi = entries.length - 1;
  let result = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (eventTimeMs(entries[mid]) <= targetMs) {
      result = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return result;
}

/** For each agentId seen up to (and including) `index`, the most recent
 * HistoryEntry for that agent — i.e. "what was the last thing we saw this
 * character do, as of this point on the scrubber". This is the core of
 * Replay: the office panel renders each agent's bubble/label off of this
 * map instead of the live GameState while replaying. */
export function lastEntryPerAgent(entries: HistoryEntry[], index: number): Map<string, HistoryEntry> {
  const result = new Map<string, HistoryEntry>();
  for (let i = 0; i <= index && i < entries.length; i++) {
    result.set(entries[i].agentId, entries[i]);
  }
  return result;
}

export interface TimelineTick {
  index: number;
  entry: HistoryEntry;
  category: TimelineCategory;
  timeMs: number;
  /** 0..1 position along the track, relative to [firstMs, lastMs]. */
  position: number;
}

/** Precomputes tick layout once per history-array change, so the component
 * doesn't redo Date.parse + division on every pointer-move while dragging. */
export function buildTicks(entries: HistoryEntry[]): TimelineTick[] {
  if (entries.length === 0) return [];
  const firstMs = eventTimeMs(entries[0]);
  const lastMs = eventTimeMs(entries[entries.length - 1]);
  const span = lastMs - firstMs;
  return entries.map((entry, index) => {
    const timeMs = eventTimeMs(entry);
    return {
      index,
      entry,
      category: categoryForType(entry.type),
      timeMs,
      position: span > 0 ? (timeMs - firstMs) / span : 0,
    };
  });
}

/** Maps a pointer's fractional position (0..1 along the track) back to the
 * nearest tick's time, for click-to-jump / drag. */
export function timeAtPosition(entries: HistoryEntry[], fraction: number): number {
  if (entries.length === 0) return 0;
  const firstMs = eventTimeMs(entries[0]);
  const lastMs = eventTimeMs(entries[entries.length - 1]);
  const clamped = Math.min(1, Math.max(0, fraction));
  return firstMs + clamped * (lastMs - firstMs);
}

export function formatClockTime(ms: number): string {
  if (!ms) return "--:--:--";
  const d = new Date(ms);
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function summaryForTick(entry: HistoryEntry): string {
  return entry.summary || entry.type;
}

const PLAY_RATES = [1, 4] as const;
export type PlayRate = (typeof PLAY_RATES)[number];

export function nextPlayRate(rate: PlayRate): PlayRate {
  const idx = PLAY_RATES.indexOf(rate);
  return PLAY_RATES[(idx + 1) % PLAY_RATES.length];
}

/** Advances the scrubber by one tick of wall-clock time, scaled by `rate`,
 * clamped to the latest known event — pure so the play-loop's per-frame
 * math is testable without faking timers/RAF. */
export function advancePlayback(currentMs: number, deltaWallMs: number, rate: PlayRate, latestMs: number): number {
  const next = currentMs + deltaWallMs * rate;
  return Math.min(next, latestMs);
}

/** Initial catch-up fetch for a session's ring buffer (REST — see
 * GET /api/v1/sessions/{id}/timeline). The live WS stream keeps the buffer
 * warm after that; this only covers history that predates the component
 * mounting (e.g. Timeline opened well into a long session). Returns [] on
 * 404 (session not seen yet) or any network failure — the WS feed will
 * populate it shortly either way, so this is best-effort, not load-bearing. */
export async function fetchInitialTimeline(sessionId: string): Promise<HistoryEntry[]> {
  try {
    const res = await authedFetch(`${getHttpBase()}/api/v1/sessions/${encodeURIComponent(sessionId)}/timeline`);
    if (!res.ok) return [];
    const body = (await res.json()) as { events?: HistoryEntry[] };
    return body.events ?? [];
  } catch {
    return [];
  }
}
