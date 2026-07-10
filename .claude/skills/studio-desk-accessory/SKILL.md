---
name: studio-desk-accessory
description: >
  Generate desk accessories for the Studio Ops visualizer. Creates small
  studio items (energy drinks, drawing tablets, controller pads, build
  status indicators, etc.) that sit on Dev desks. Items are grayscale/white
  by default so they can be tinted different colors for variety.
triggers:
  - create desk accessory
  - studio desk item
  - dev desk decoration
---

# Studio Desk Accessory Generator

Adapted from claude-office's `desk-accessory` skill — identical mechanics
and tinting philosophy, re-themed item list.

## Philosophy: tintable variety (unchanged from reference)

Common items = WHITE/GRAYSCALE so they can be tinted at runtime (one sprite,
many desk colors). Unique items can have baked-in color.

## Item list

**Tintable (WHITE/GRAYSCALE)**:
- Energy drink can
- Drawing tablet + stylus
- Game controller pad
- Sprite-sheet printout (small paper stack)
- Bug-report sticky note pad
- Coffee mug (kept from reference — still a valid studio item)

**Unique (full color OK)**:
- Build-status LED indicator (green "passing" / red "failing" — bake in
  both color states as two separate sprites, `build-status-pass.png` /
  `build-status-fail.png`, since it's not meaningfully tintable)
- "PIXEL QUEST" branded desk nameplate

## Prompt template (tintable items)

```
Pixel art [ITEM], 16-bit retro game style, WHITE colored, simple clean
design, facing north-west, on solid magenta background #FF00FF, game
sprite asset, centered composition, no shadows on background, clean edges,
chunky pixel art with thick lines and bold shapes, this will be scaled
down significantly so use thick prominent features
```

Facing north-west rule is unchanged from the reference (top-down
perspective, items face away from camera toward upper-left).

## Processing

```bash
.claude/skills/studio-desk-accessory/scripts/process_tintable.sh \
  generated.png frontend/public/sprites/[item-name].png
```

Same multi-pass removal + desaturate + scale-to-128px pipeline as the
reference's `process_tintable.sh` (copied verbatim).

## Output location

`frontend/public/sprites/[item-name].png`, lowercase-with-dashes naming
(`energy-drink.png`, `controller-pad.png`, `bug-report-pad.png`).

## Anti-patterns

Same as the reference: don't generate colored common items (kills tinting
variety), don't use flood-fill for items with enclosed holes (mug handles,
controller grips), always convert to `TrueColorAlpha` after desaturation.
