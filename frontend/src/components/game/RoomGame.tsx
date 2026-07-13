"use client";

import { useEffect, useRef } from "react";
import { Application, extend } from "@pixi/react";
import { Container, Graphics, Sprite, Text } from "pixi.js";
import { useRoomStore, selectRoomSessions } from "@/stores/roomStore";
import { useAgentsStore, selectAgents } from "@/stores/agentsStore";
import { WORK_SEATS } from "@/systems/layout";
import { planFor, forgetAgent } from "@/systems/officeMovement";
import { planForCat, forgetCat } from "@/systems/catMovement";
import { LeadCapsule } from "./LeadCapsule";
import { CatCapsule } from "./CatCapsule";
import { LabelTag } from "./LabelTag";
import { ZoneDebugOverlay } from "./ZoneDebugOverlay";
import { OfficeBackground, STAGE_WIDTH, STAGE_HEIGHT } from "./StudioGame";

extend({ Container, Graphics, Sprite, Text });

// The office has one work seat per desk, so at most that many workers can
// have a desk to walk to. Beyond that, agents are summarised as "+N more"
// rather than piling onto the same seat illegibly.
const MAX_WORKERS = WORK_SEATS.length;

// Task-tool subagents (rendered as cats) count as "working" for exactly
// these backend DevStates — everything else (arriving/leaving/waiting/idle)
// collapses to "curled up beside the owner" (see catMovement.ts).
const CAT_BUSY_STATES = new Set(["working", "waiting_permission"]);

export function RoomGame({ onAgentClick }: { onAgentClick?: (sessionId: string) => void }) {
  const sessions = useRoomStore(selectRoomSessions);
  const agents = useAgentsStore(selectAgents);
  // Plain window.location read, not next/navigation's useSearchParams —
  // that hook requires a <Suspense> boundary during static prerendering
  // and this is a dev-only visual QA toggle, not something that needs to
  // react to client-side navigation.
  const debug = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("debug") === "1";

  // Which sessions are the CEO — matched via the registry (role "ceo"),
  // since the CEO's Lead has no DevRole sprite-role and can't be told apart
  // by lead.role alone.
  const ceoSessions = new Set(
    agents.filter((a) => a.role === "ceo" && a.sessionId).map((a) => a.sessionId as string),
  );

  const entries = Array.from(sessions.values());
  // Stable worker ordering (→ stable desk assignment) independent of Map
  // iteration quirks: sort non-CEO sessions by id.
  const workers = entries
    .filter((e) => !ceoSessions.has(e.sessionId))
    .sort((a, b) => a.sessionId.localeCompare(b.sessionId));
  const ceos = entries.filter((e) => ceoSessions.has(e.sessionId));

  const visibleWorkers = workers.slice(0, MAX_WORKERS);
  const overflow = workers.length - visibleWorkers.length;

  // Drop movement memory for sessions/subagents that left, so a future
  // session id reuse (unlikely, but cheap to guard) doesn't inherit a
  // stale start position — see officeMovement.ts/catMovement.ts's memoization.
  const liveIds = useRef(new Set<string>());
  const liveCatIds = useRef(new Set<string>());
  useEffect(() => {
    const current = new Set(entries.map((e) => e.sessionId));
    for (const id of liveIds.current) {
      if (!current.has(id)) forgetAgent(id);
    }
    liveIds.current = current;

    const currentCats = new Set(entries.flatMap((e) => e.devs.map((d) => d.id)));
    for (const id of liveCatIds.current) {
      if (!currentCats.has(id)) forgetCat(id);
    }
    liveCatIds.current = currentCats;
  });

  const rendered = [
    ...ceos.map((session) => ({ session, isCeo: true, workerIndex: 0 })),
    ...visibleWorkers.map((session, i) => ({ session, isCeo: false, workerIndex: i })),
  ];

  return (
    <Application
      width={STAGE_WIDTH}
      height={STAGE_HEIGHT}
      background="#1a1030"
      resolution={typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1}
      autoDensity
    >
      <pixiContainer>
        <OfficeBackground />
        {debug && <ZoneDebugOverlay />}
        {rendered.map(({ session, isCeo, workerIndex }) => {
          const lead = session.lead;
          const busy = lead.state !== "idle";
          const plan = planFor({ sessionId: session.sessionId, isCeo, workerIndex, busy });
          // Where this Lead is walking to (or already at) — cats trail
          // this rather than a frame-perfect live position, which
          // LeadCapsule keeps privately internal.
          const ownerPos = plan.path[plan.path.length - 1] ?? plan.position;
          return (
            <pixiContainer key={session.sessionId}>
              <LeadCapsule
                plan={plan}
                role={lead.role ?? null}
                name={lead.name ?? null}
                chatAvailable={lead.chatAvailable}
                onClick={() => onAgentClick?.(session.sessionId)}
              />
              {session.devs.map((dev) => (
                <CatCapsule
                  key={dev.id}
                  catIndex={dev.number}
                  plan={planForCat(dev.id, ownerPos, CAT_BUSY_STATES.has(dev.state))}
                />
              ))}
            </pixiContainer>
          );
        })}
        {overflow > 0 && (
          <pixiContainer x={STAGE_WIDTH - 130} y={STAGE_HEIGHT - 26}>
            <LabelTag text={`+${overflow} more`} fontSize={14} color="#ffe08a" width={110} />
          </pixiContainer>
        )}
      </pixiContainer>
    </Application>
  );
}
