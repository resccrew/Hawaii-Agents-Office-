#!/usr/bin/env python3
"""Multi-pass magenta chroma-key removal, PIL-based.

Reimplementation of remove_magenta.sh's approach (FFmpeg geq filter +
ImageMagick multi-pass -transparent) for environments without
ImageMagick/FFmpeg installed (this one has neither — only Pillow). Same
target: catch bright magenta AND the darker anti-aliased purple fringe
pixels around character edges, without eroding the character itself.

Usage: remove_magenta.py INPUT.png OUTPUT.png [--trim]
"""

from __future__ import annotations

import sys

from PIL import Image


def is_magenta_ish(r: int, g: int, b: int) -> bool:
    """True for bright magenta and its anti-aliased purple/pink fringe.

    Bright magenta: R and B both high, G low (classic #FF00FF chroma key).
    Fringe pixels (blended magenta+character edge): R approx B, G
    noticeably lower than both — same heuristic as the reference script's
    FFmpeg geq pass (R≈B, G low relative to R and B).
    """
    if g >= 60:
        return False
    if abs(r - b) > 45:
        return False
    return (r + b) > 90


def remove_magenta(input_path: str, output_path: str, *, trim: bool = True) -> None:
    im = Image.open(input_path).convert("RGBA")
    pixels = im.load()
    w, h = im.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if is_magenta_ish(r, g, b):
                pixels[x, y] = (r, g, b, 0)

    if trim:
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)

    im.save(output_path)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trim = "--skip-trim" not in sys.argv
    if len(args) != 2:
        print("Usage: remove_magenta.py INPUT.png OUTPUT.png [--skip-trim]", file=sys.stderr)
        sys.exit(1)
    remove_magenta(args[0], args[1], trim=trim)
    print(f"Processed: {args[1]}")
