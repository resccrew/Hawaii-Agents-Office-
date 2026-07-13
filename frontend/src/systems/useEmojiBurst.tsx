"use client";

import { useCallback, useState } from "react";

// Small "emoji burst" click flourish (inspired by originkit.dev/components/
// emojiburst) — a handful of emoji pop out from the trigger point, fly
// outward on random headings, and fade. Pure CSS keyframes (no animation
// library dependency): each particle's direction is precomputed in JS as an
// x/y offset (CSS alone has no sin/cos) and handed to the keyframe as
// custom properties.
interface Particle {
  id: number;
  emoji: string;
  dx: number;
  dy: number;
  delayMs: number;
  size: number;
}

const EMOJIS = ["🎮", "🕹️", "👾", "✨", "🎉", "💻"];
const PARTICLE_COUNT = 10;
const LIFETIME_MS = 800;

let nextId = 0;

export function useEmojiBurst() {
  const [particles, setParticles] = useState<Particle[]>([]);

  const burst = useCallback(() => {
    const batch: Particle[] = Array.from({ length: PARTICLE_COUNT }, () => {
      const angle = Math.random() * Math.PI * 2;
      const distance = 36 + Math.random() * 48;
      nextId += 1;
      return {
        id: nextId,
        emoji: EMOJIS[Math.floor(Math.random() * EMOJIS.length)],
        dx: Math.cos(angle) * distance,
        dy: Math.sin(angle) * distance,
        delayMs: Math.random() * 90,
        size: 14 + Math.random() * 10,
      };
    });
    setParticles((prev) => [...prev, ...batch]);
    const ids = new Set(batch.map((p) => p.id));
    window.setTimeout(() => {
      setParticles((prev) => prev.filter((p) => !ids.has(p.id)));
    }, LIFETIME_MS + 100);
  }, []);

  const layer = (
    <span className="emoji-burst-layer" aria-hidden="true">
      {particles.map((p) => (
        <span
          key={p.id}
          className="emoji-burst-particle"
          style={
            {
              "--dx": `${p.dx}px`,
              "--dy": `${p.dy}px`,
              animationDelay: `${p.delayMs}ms`,
              fontSize: p.size,
            } as React.CSSProperties
          }
        >
          {p.emoji}
        </span>
      ))}
    </span>
  );

  return { burst, layer };
}
