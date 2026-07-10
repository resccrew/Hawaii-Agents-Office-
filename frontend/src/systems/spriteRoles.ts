// Shared role -> sprite path map. Extracted out of DevCapsule.tsx
// (bugfix pass) so LeadCapsule.tsx can render a spawned peer agent's own
// role/sprite too, instead of duplicating this map — a Lead with `role`
// set (see backend/app/models/agents.py) IS a spawned agent and should
// look like one, not the generic producer.
export const SPRITE_PATH_BY_ROLE: Record<string, string> = {
  programmer: "/sprites/programmer_front_idle.png",
  game_designer: "/sprites/game_designer_front_idle.png",
  artist: "/sprites/artist_front_idle.png",
  qa_tester: "/sprites/qa_tester_front_idle.png",
  producer: "/sprites/producer_front_idle.png",
};
