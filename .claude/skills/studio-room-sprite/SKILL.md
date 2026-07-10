---
name: studio-room-sprite
description: >
  Generate game-ready department/room sprites for the Studio Ops
  visualizer using an AI image model and ImageMagick. Uses 45-degree
  front/top-down perspective (NOT isometric) with retro 16-bit pixel art
  style. Includes validation step before processing and a shared
  background-removal script.
triggers:
  - create department sprite
  - generate studio room
  - make sprite for studio
  - studio room asset
---

# Studio Room Sprite Generator

Adapted from claude-office's `office-sprite` skill — identical mechanics
(45° front/top-down, NOT isometric, magenta chroma-key, multi-pass removal),
re-themed for game-dev department rooms instead of generic office rooms.

## Project context

Same perspective rule as the reference: front view with a slight top-down
angle, similar to classic 2D RPGs — not isometric, no multiple visible side
faces.

## Departments (matches `backend/studio.toml`)

| Department | Room concept |
|------------|------|
| Engineering | Bullpen with server racks, dual-monitor desks, tangled cables |
| Art | Drawing tablets, concept-art corkboards pinned with sketches, color swatches |
| Design | Whiteboards covered in game-mechanic diagrams, level-flow charts |
| QA | Playtest room — TVs with controllers, bug-tracker board, sticky notes |
| Production | Stand-up corner — kanban board, sprint burndown chart, "PIXEL QUEST" release calendar |

## Workflow

### Step 1: Generate

```
[ROOM ELEMENT DESCRIPTION], front view with slight top-down angle, NOT
isometric, pixel art style, retro 16-bit game sprite, isolated on solid
magenta background #FF00FF, clean edges, no shadows on background, game
sprite asset, centered composition, no text, no watermarks, simple design
```

Example `[ROOM ELEMENT DESCRIPTION]`: "Server rack tower with blinking LED
lights and tangled cat5 cables, dark metal casing" or "Corkboard covered in
pinned concept-art sketches and color swatches, wooden frame" or "Kanban
board on wheeled stand with colored sticky notes in To Do / In Progress /
Done columns".

Save to `frontend/public/sprites/[name]_raw.png`.

### Step 2: VALIDATE before processing

View with the Read tool, confirm: perspective is front/top-down (not
isometric), subject centered and fully visible, background solid magenta,
art style matches 16-bit pixel art. Regenerate if the perspective drifted
to isometric — this is the most common failure mode per the reference
skill's field notes.

### Step 3: Process

```bash
.claude/skills/studio-room-sprite/scripts/process_sprite.sh \
  frontend/public/sprites/[name]_raw.png \
  frontend/public/sprites/[name].png
```

Multi-pass FFmpeg + ImageMagick removal, identical to the reference's
`process_sprite.sh` (copied verbatim — the mechanics are theme-agnostic).

### Step 4: Verify, Step 5: wire into StudioGame.tsx

Same pattern as the reference's `OfficeGameV2.tsx` integration — load via
`Assets.load`, render as `<pixiSprite texture={...} anchor={0.5} scale={...}>`
with a `<pixiGraphics>` placeholder fallback, inside `StudioGame.tsx`'s
`DepartmentBackdrop` component (currently flat colored rects — swap for
sprite tiles once assets are approved).

## Output location

`frontend/public/sprites/[name]_raw.png` (keep) / `[name].png` (processed).

## Anti-patterns

Same as the reference `office-sprite` skill: don't skip validation, don't
accept isometric drift, don't use white/black as chroma key, always trim
and verify transparency before wiring into the frontend.
