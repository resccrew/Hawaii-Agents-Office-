"use client";

import { useEffect, useState } from "react";
import { Assets, type Texture } from "pixi.js";

// Loads a sprite texture with graceful fallback — callers render a
// <pixiGraphics> placeholder while texture is null (asset missing, still
// loading, or generation not done yet for that role). Matches the
// office-sprite skill's documented integration pattern (Assets.load +
// state + fallback), ported to a shared hook since multiple components
// (DevCapsule, LeadCapsule) need the same logic.
export function useSpriteTexture(path: string | null): Texture | null {
  const [texture, setTexture] = useState<Texture | null>(null);

  useEffect(() => {
    if (!path) {
      setTexture(null);
      return;
    }
    let cancelled = false;
    Assets.load(path)
      .then((tex: Texture) => {
        if (!cancelled) setTexture(tex);
      })
      .catch(() => {
        if (!cancelled) setTexture(null);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return texture;
}
