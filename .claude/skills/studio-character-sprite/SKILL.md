---
name: studio-character-sprite
description: >
  Generate complete character sprite sheets for the Studio Ops game-dev studio
  visualizer's Dev/Lead characters. Creates all animation frames (idle,
  walking, typing, handoff, coffee/energy-drink) with consistent character
  design across all sheets. Uses iterative approval workflow and
  reference-based generation for consistency.
triggers:
  - create dev sprite
  - create studio character sprite
  - new studio character
  - generate dev animations
---

# Studio Character Sprite Generator

Adapted from claude-office's `character-sprite` skill — same mechanics (Nano
Banana-class image model + ImageMagick), re-themed for a game-dev studio.
The generation mechanics (grid layout, frame specs, multi-pass magenta
removal) are unchanged from the reference; only the character roster and
prompt subject matter differ.

## Reference art direction

The user supplied a target reference image: 16-bit pixel art, front-facing
character portraits (not full isometric), bold chunky proportions, each
character holding a role-specific prop, standing on/near a desk with a
"PIXEL QUEST" game box and "DEV TEAM" binder in the background. Match that
palette and proportion style — sharp pixel edges, no anti-aliasing, warm
saturated colors, readable silhouettes at small scale.

**Character Constraints** (unchanged from reference): max 60px wide × 75px
tall on-screen, magenta (#FF00FF) chroma-key background for generation.

## Roster (5 roles, matches `backend/app/models/agents.py` DevRole + Lead)

| Role | Look (from user's reference image + DevRole enum) |
|------|------|
| Programmer | Hoodie with "CODE" print, dual monitors vibe, holding a keyboard, brown hair, glasses optional |
| Game Designer | Curly red/orange hair, vest over shirt, holding a game controller, "DESIGN" note tucked at waist |
| Artist | Purple ponytail, overalls over green shirt, holding a drawing tablet + stylus |
| QA Tester | Beanie, plain t-shirt with "TESTER" print, holding a phone/tablet with a bug icon |
| Producer/Lead | Headset + megaphone, rainbow lanyard with ID badge, coordinating pose — this is the `Lead`/`Producer` character, rendered larger (64×100 vs 48×80 for Devs) |

## Sprite sheet technical specs (unchanged from reference — port verbatim)

| Sheet Type | Total Size | Grid | Cell Size | Frames |
|------------|------------|------|-----------|--------|
| **Idle** | 928 × 1152 px | 8 cols × 8 rows | 116 × 144 px | 64 total |
| **Walking** | 928 × 1152 px | 8 cols × 8 rows | 116 × 144 px | 64 total |
| **Typing** | 928 × 144 px | 8 cols × 1 row | 116 × 144 px | 8 frames |
| **Handoff** | 928 × 1152 px | 4 cols × 1 row | 232 × 411 px* | 4 frames |
| **Break** (coffee/energy-drink) | 928 × 1152 px | 4 cols × 1 row | 232 × 699 px* | 4 frames |

8 directions per row (S, SW, W, NW, N, NE, E, SE), same grid discipline as
the reference: **zero padding/spacing, no grid lines, fill every cell.**

## Workflow

### Step 1: Generate the canonical reference pose

One front-facing idle pose per role, to lock in the design before spending
generation budget on full animation sheets:

```
16-bit pixel art game sprite of a [ROLE DESCRIPTION FROM TABLE ABOVE], front
view facing camera, [SPECIFIC CLOTHING/PROP FROM TABLE], simple friendly
face, small character suitable for a top-down game-dev studio game, retro
SNES/Genesis style pixel art, standing idle pose, isolated on solid magenta
background #FF00FF, SHARP CRISP PIXEL EDGES WITH ABSOLUTELY NO
ANTI-ALIASING NO SMOOTHING NO BLENDING, each pixel is a solid color with
hard edges, centered composition, no text except any prop labels named
above, no shadows on background, 64x80 pixels scale
```

Save as `frontend/public/sprites/[role]_front_idle_raw.png` (e.g.
`programmer_front_idle_raw.png`, `producer_front_idle_raw.png`).

### Step 2: VALIDATE AND ITERATE — get approval before mass-generating

1. View the raw image (Read tool) and present it.
2. Check: matches the reference image's art direction, proportions read
   well at small scale, prop is recognizable, no anti-aliasing.
3. If rejected, adjust the prompt and regenerate. **Do not skip this gate**
   — every subsequent sheet for this role reuses this image as a
   consistency reference, so an approved bad design propagates to 5 more
   generations before anyone notices.

### Step 3: Generate the 5 animation sheets per role

Same prompt template as `character-sprite` (idle/walk/typing/handoff/break),
substituting `[ROLE DESCRIPTION]` and using **both** the approved Step 1
image and, for every role after the first, a previously-approved sheet of
the *same type* as the second reference image (e.g. programmer's walk sheet
references artist's approved walk sheet) — this is what keeps frame
positions/proportions consistent across the whole roster, not just within
one character.

Prompt skeleton (idle sheet shown; walk/typing/handoff/break follow the
same substitution pattern as claude-office's `character-sprite/SKILL.md` —
consult it for the other four verbatim, only swapping character wording):

```
16-bit pixel art sprite sheet, EXACTLY 928x1152 pixels total, divided into
8 columns and 8 rows grid, each cell is EXACTLY 116x144 pixels with NO
borders NO padding NO gaps between cells, character is [ROLE DESCRIPTION]
(EXACTLY as shown in first reference image), 8 DIRECTIONS IN EXACT ORDER
from top to bottom: ROW 0 south facing toward camera, ROW 1 south-west
diagonal, ROW 2 west facing left profile, ROW 3 north-west diagonal, ROW 4
north facing away back view, ROW 5 north-east diagonal, ROW 6 east facing
right profile, ROW 7 south-east diagonal, each row has 8 frames of subtle
idle breathing animation, cells touch edge-to-edge with no visible grid
lines, retro SNES Genesis 16-bit pixel art, SHARP CRISP PIXEL EDGES WITH
ABSOLUTELY NO ANTI-ALIASING NO SMOOTHING NO BLENDING, each pixel is a solid
color with hard edges, consistent character in every cell matching
reference, solid magenta #FF00FF background fills all empty space in each
cell, game sprite sheet asset, no text no watermarks
```

Negative prompt (all sheets): `blurry, 3D, realistic, anti-aliasing,
anti-aliased edges, smoothing, blending, soft edges, gradients, shadows on
background, inconsistent character, different characters, text, watermark,
grid lines, cell borders, padding between frames, gaps between cells`

"Break" sheet (energy-drink/coffee instead of the reference's generic
coffee) — 4-frame animation: frame 1 holding can at chest, frame 2 raising
can, frame 3 drinking, frame 4 satisfied lowering. "Handoff" sheet — 4-frame
side-profile handing over a folder/build report.

### Step 4: Validate each sheet, then Step 5: process

Identical to claude-office's `character-sprite` Steps 4–5 — verify
dimensions with `magick`, check for grid-line/anti-aliasing artifacts, then
batch-process with the shared multi-pass magenta remover:

```bash
cd frontend/public/sprites
SCRIPT="../../../.claude/skills/shared/scripts/remove_magenta.sh"
for sheet in [role]_idle_sheet [role]_walk_sheet [role]_typing_sheet [role]_handoff_sheet [role]_break_sheet; do
  "$SCRIPT" "${sheet}_raw.png" "${sheet}.png" --skip-trim
done
```

## Output location

`frontend/public/sprites/[role]_[type]_[raw|].png` — same convention as the
reference. `[role]` ∈ `programmer, game_designer, artist, qa_tester,
producer` (matches `DevRole`/Lead in `backend/app/models/agents.py`).

## Anti-patterns

Same as claude-office's `character-sprite` skill verbatim: don't skip the
Step 2 approval gate, don't generate a sheet without both reference images,
don't accept grid lines or anti-aliased edges, don't proceed with
inconsistent character design across the roster.
