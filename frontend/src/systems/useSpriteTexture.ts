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
        // Bugfix: the background (1024x559) is upscaled ~1.14x to cover the
        // 960x640 stage, and every character sprite is scaled too — PixiJS
        // defaults to bilinear ("linear") filtering, which blurs pixel art
        // on any non-1:1 scale. "nearest" keeps hard pixel edges at any
        // scale, which is what a pixel-art game actually wants.
        tex.source.scaleMode = "nearest";
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
