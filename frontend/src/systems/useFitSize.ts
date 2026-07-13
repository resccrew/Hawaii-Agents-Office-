"use client";

import { useEffect, useRef, useState } from "react";

const ASPECT_RATIO = 3 / 2; // matches STAGE_WIDTH / STAGE_HEIGHT in StudioGame.tsx

// Cover-crop cap: how much bigger than the "contain" size the frame may
// grow to fill the wrapper. 1.5 means at most ~33% of one axis is cropped
// past the edges; beyond that (extreme ultrawide/tall windows) we stop
// growing and let the styled letterbox backdrop show instead of cropping
// half the office away.
const MAX_OVERSCAN = 1.5;

export interface FitSize {
  /** Frame (canvas) pixel size — always 3:2. */
  width: number;
  height: number;
  /** How many px of the frame are clipped past ONE horizontal/vertical edge
   * of the wrapper (frame is centered, so total hidden = 2×crop). Used to
   * keep overlays (chat popup) inside the *visible* part of the frame. */
  cropX: number;
  cropY: number;
}

// COVER fit (not contain): the office canvas scales up to fill the whole
// wrapper, cropping its own edges symmetrically, instead of leaving dead
// letterbox bands. Done in JS via ResizeObserver for the same reason the
// old contain-fit was (see git history): CSS aspect-ratio + percentage
// max-height resolved inconsistently across real Chrome builds, while an
// explicit pixel size renders identically everywhere.
export function useFitSize(containerRef: React.RefObject<HTMLElement | null>): FitSize {
  const [size, setSize] = useState<FitSize>({ width: 960, height: 640, cropX: 0, cropY: 0 });
  const frame = useRef<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const measure = (availW: number, availH: number) => {
      const containW = Math.min(availW, availH * ASPECT_RATIO);
      const coverW = Math.max(availW, availH * ASPECT_RATIO);
      const width = Math.min(coverW, containW * MAX_OVERSCAN);
      const height = width / ASPECT_RATIO;
      setSize({
        width: Math.max(0, Math.round(width)),
        height: Math.max(0, Math.round(height)),
        cropX: Math.max(0, Math.round((width - availW) / 2)),
        cropY: Math.max(0, Math.round((height - availH) / 2)),
      });
    };

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      // rAF-batch so rapid resize events don't thrash React state.
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        measure(entry.contentRect.width, entry.contentRect.height);
      });
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [containerRef]);

  return size;
}
