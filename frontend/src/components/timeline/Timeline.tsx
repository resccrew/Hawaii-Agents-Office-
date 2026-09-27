"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useActivityLogStore, selectLogEntries, type LogEntry } from "@/stores/activityLogStore";
import { useUiSettingsStore } from "@/stores/uiSettingsStore";
import {
  buildTicks,
  categoryForType,
  CATEGORY_COLOR_VAR,
  eventTimeMs,
  formatClockTime,
  indexAtOrBefore,
  isAtLiveEdge,
  nextPlayRate,
  advancePlayback,
  summaryForTick,
  timeAtPosition,
  type PlayRate,
} from "@/systems/timeline";

// Timeline / Replay: a compact scrubber under the office/activity-log panel
// that lets you drag back through everything that's happened this studio
// session — every hook event, tool call, permission request, subagent
// start/stop and error — instead of only ever seeing the live tail the way
// ActivityLog.tsx shows it. Reuses that same store (useActivityLogStore) as
// its data source, so a session's whole capped history (currently 2000
// entries server-side — see backend/app/core/state_machine.py) is already
// here: WS delivers it incrementally, and this component just adds a way
// to look backward through what's already arrived.
//
// Replay here means "scrub the event log and see what was happening at
// time t" (selected tick + its neighbors highlighted, tooltip on hover) —
// it deliberately does not reach into gameStore/pixi to rewind character
// sprites; that would need the backend to snapshot full GameState per
// event rather than just a HistoryEntry, which is a bigger lift than this
// pass covers.
export function Timeline() {
  const entries = useActivityLogStore(selectLogEntries);
  const reduceMotion = useUiSettingsStore((s) => s.reduceMotion);

  const ticks = useMemo(() => buildTicks(entries), [entries]);
  const latestMs = ticks.length > 0 ? ticks[ticks.length - 1].timeMs : 0;

  // null = "live": always track the newest entry, exactly like ActivityLog.
  const [scrubMs, setScrubMs] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [playRate, setPlayRate] = useState<PlayRate | null>(null); // null = not playing
  const trackRef = useRef<HTMLDivElement>(null);

  const live = scrubMs === null || isAtLiveEdge(scrubMs, latestMs);
  const effectiveMs = live ? latestMs : (scrubMs as number);
  const selectedIndex = indexAtOrBefore(entries, effectiveMs);
  const selectedTick = selectedIndex >= 0 ? ticks[selectedIndex] : null;

  // A newly-arriving live event should keep the scrubber pinned to "now"
  // instead of freezing it at whatever the head used to be.
  useEffect(() => {
    if (live && scrubMs !== null) setScrubMs(null);
  }, [latestMs, live, scrubMs]);

  const goLive = useCallback(() => {
    setScrubMs(null);
    setPlayRate(null);
  }, []);

  const seekToFraction = useCallback(
    (fraction: number) => {
      const t = timeAtPosition(entries, fraction);
      setPlayRate(null);
      if (isAtLiveEdge(t, latestMs)) {
        setScrubMs(null);
      } else {
        setScrubMs(t);
      }
    },
    [entries, latestMs],
  );

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = trackRef.current;
    if (!el || entries.length === 0) return;
    const rect = el.getBoundingClientRect();
    const fraction = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0;
    seekToFraction(fraction);
  };

  const step = useCallback(
    (direction: 1 | -1) => {
      if (entries.length === 0) return;
      const base = live ? entries.length - 1 : Math.max(0, selectedIndex);
      const nextIndex = Math.min(entries.length - 1, Math.max(0, base + direction));
      setPlayRate(null);
      const t = eventTimeMs(entries[nextIndex]);
      setScrubMs(isAtLiveEdge(t, latestMs) ? null : t);
    },
    [entries, live, selectedIndex, latestMs],
  );

  const togglePlay = useCallback(() => {
    setPlayRate((r) => {
      if (r !== null) return null;
      // Starting playback from "live" rewinds to the earliest entry first —
      // playing forward from the end wouldn't go anywhere.
      if (live && entries.length > 0) setScrubMs(eventTimeMs(entries[0]));
      return 1;
    });
  }, [live, entries]);

  const cyclePlayRate = useCallback(() => {
    setPlayRate((r) => (r === null ? 1 : nextPlayRate(r)));
  }, []);

  // Playback loop — advances scrubMs by wall-clock delta * rate every
  // frame, via requestAnimationFrame so it respects the tab's paint cadence
  // (and pauses automatically when the tab isn't visible, same as any RAF
  // loop). Skips entirely under reduceMotion: play is presented disabled
  // rather than silently doing nothing, see the button below.
  useEffect(() => {
    if (playRate === null || reduceMotion) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const delta = now - last;
      last = now;
      setScrubMs((prev) => {
        const cur = prev ?? (entries.length > 0 ? eventTimeMs(entries[0]) : 0);
        const next = advancePlayback(cur, delta, playRate, latestMs);
        if (next >= latestMs) {
          setPlayRate(null);
          return null; // reached live edge — snap back to live tracking
        }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playRate, reduceMotion, latestMs, entries]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      step(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      step(1);
    } else if (e.key === " ") {
      e.preventDefault();
      togglePlay();
    }
  };

  const hoverTick = hoverIndex !== null ? ticks[hoverIndex] : null;

  return (
    <div className="timeline">
      <div className="timeline-header">
        <span>timeline</span>
        <div className="timeline-controls">
          <button
            type="button"
            className="timeline-btn"
            onClick={togglePlay}
            disabled={entries.length === 0 || reduceMotion}
            aria-label={playRate !== null ? "pause replay" : "play replay"}
            title={reduceMotion ? "disabled (reduce motion is on)" : undefined}
          >
            {playRate !== null ? "⏸" : "▶"}
          </button>
          <button
            type="button"
            className="timeline-btn"
            onClick={cyclePlayRate}
            disabled={entries.length === 0 || reduceMotion}
            aria-label="playback speed"
          >
            ×{playRate ?? 1}
          </button>
          <button
            type="button"
            className={`timeline-live-btn${live ? " timeline-live-active" : ""}`}
            onClick={goLive}
            aria-pressed={live}
          >
            <span className="timeline-live-dot" aria-hidden="true" /> live
          </button>
        </div>
      </div>

      <div
        className="timeline-track"
        ref={trackRef}
        onClick={handleTrackClick}
        onMouseLeave={() => setHoverIndex(null)}
        role="slider"
        tabIndex={0}
        aria-label="event timeline scrubber"
        aria-valuemin={0}
        aria-valuemax={Math.max(0, entries.length - 1)}
        aria-valuenow={selectedIndex >= 0 ? selectedIndex : 0}
        aria-valuetext={selectedTick ? summaryForTick(selectedTick.entry) : "no events"}
        onKeyDown={handleKeyDown}
      >
        {ticks.length === 0 && <span className="timeline-empty">no events yet</span>}
        {ticks.map((t) => (
          <div
            key={`${t.entry.id}-${t.index}`}
            className={`timeline-tick${t.index === selectedIndex ? " timeline-tick-selected" : ""}`}
            style={{
              left: `${t.position * 100}%`,
              background: `var(${CATEGORY_COLOR_VAR[t.category]})`,
            }}
            onMouseEnter={() => setHoverIndex(t.index)}
          />
        ))}
        {live && ticks.length > 0 && <div className="timeline-live-marker" style={{ left: "100%" }} />}
      </div>

      <div className="timeline-footer">
        <span className="timeline-time">{formatClockTime(effectiveMs)}</span>
        {hoverTick ? (
          <span className="timeline-tooltip">
            [{categoryForType(hoverTick.entry.type)}] {summaryForTick(hoverTick.entry)}
            {(hoverTick.entry as LogEntry).agentName ? ` · @${(hoverTick.entry as LogEntry).agentName}` : ""}
          </span>
        ) : (
          selectedTick && <span className="timeline-tooltip">{summaryForTick(selectedTick.entry)}</span>
        )}
      </div>
    </div>
  );
}
