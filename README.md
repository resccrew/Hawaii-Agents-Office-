# 🌴 Hawaii Agents Office

[![CI](https://github.com/resccrew/Hawaii-Agents-Office-/actions/workflows/ci.yml/badge.svg)](https://github.com/resccrew/Hawaii-Agents-Office-/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A pixel-art game-dev studio visualizer for [Claude Code](https://claude.com/claude-code)
sessions, packaged as a native **macOS desktop app** (built with
[Tauri](https://tauri.app)). Every agent you spawn — or any interactive
Claude Code session running on your machine — shows up as an animated
character walking around a beach-office, sitting at a desk, grabbing a
coffee, or queuing up for a chat. Task-tool subagents spawned *inside* a
session show up too, as cats wandering near their owner's desk.

![Hawaii Agents Office screenshot](docs/screenshot.png)
*(office canvas shown in browser dev-mode — a screenshot of the packaged
desktop app, with its in-window terminals, is coming once that UI settles)*

## What it does

- **Live office view** — every Claude Code session on your machine (interactive
  terminal sessions, headless spawned agents, or both) is rendered as a
  character with real-time state (idle / working / waiting on permission /
  arriving / leaving), driven by Claude Code's own hook events.
- **In-app terminals** — real Claude Code sessions running in xterm.js panes
  inside the app itself (a real PTY, via the backend's terminal service),
  alongside the office canvas in the sidebar.
- **Spawn & chat with agents** — click **+ agent**, give it a name, role, and
  a "brain" (Claude, OpenAI, Gemini, or Ollama), and it appears in the office.
  Open a draggable chat window and talk to it directly; per-message model and
  effort selection is available for Claude agents.
- **File attachments in chat** — drag-and-drop or pick a file to attach to a
  chat message; images are sent as real vision input, text files are inlined.
- **Sub-agent cats** — when a session spawns its own Task-tool sub-agents,
  they appear as cats sitting near their owner, wandering the office while
  busy.
- **Activity log & task board** — a live feed of every hook event
  (session start/stop, tool use, permission requests, subagent lifecycle),
  plus a lightweight task board agents can post to via MCP tools.
- **One-click GitHub push** — pick a local repo (or clone one straight from
  your GitHub account) and push from the git bar under the office.
- **Settings UI** — configure API keys (OpenAI, Gemini, Ollama, Nano Banana)
  and general app preferences from an in-app settings panel; no restart
  required for most changes.

## How it was built

*(placeholder — filled in once the app is feature-complete: the short
version is every piece of this, including this README and its CI, was built
by orchestrating Claude Code agents against `CLAUDE.md` as shared memory.)*

## Architecture

```
src-tauri/  Tauri 2 (Rust) — the native window, and the backend bundled as a
            PyInstaller sidecar binary so the packaged .app has no external
            Python dependency
frontend/   Next.js + React + pixi.js — the office canvas, in-app terminals,
            chat windows, activity log, settings UI; statically exported
            (`next build`, output: 'export') into the Tauri bundle
backend/    FastAPI — hook event ingestion, session state machine, WebSocket
            broadcast, chat bridge, provider dispatch, terminal PTYs, git ops
hooks/      A small Python package installed as the `studio-ops-hook` CLI, wired into
            Claude Code's own hooks (SessionStart, PreToolUse, Stop, SubagentStart, …) via ~/.claude/settings.json
```

The frontend and backend talk over REST + WebSocket, both to `localhost:8010`
whether the backend is running as a plain `uvicorn` process (dev mode) or as
the sidecar Tauri launches and manages (packaged app). The backend never
talks to Claude Code directly for the *observation* side — it only ever
receives events that Claude Code's hooks push to it. For *chat* (sending a
message to a spawned agent), the backend shells out to `claude -p --resume`
(or the relevant provider's API) and streams the reply back over its own
`/ws/chat/{session_id}` channel.

## Install

### Option A — download the app (recommended)

Grab the latest `.dmg` from [Releases](https://github.com/resccrew/Hawaii-Agents-Office-/releases),
open it, and drag **Hawaii Agents Office** into Applications.

**Gatekeeper will warn on first launch** — the build is ad-hoc signed, not
notarized with a paid Apple Developer ID. Right-click the app in
Applications and choose **Open** once; after that it launches normally.

You still need the hooks step below so the office isn't empty, and the
[Claude Code CLI](https://claude.com/claude-code) installed and logged in
(`claude` must work from a plain terminal).

### Option B — build from source

Needs, on top of the [Claude Code CLI](https://claude.com/claude-code):
Node.js 20+, Python 3.12+, [uv](https://docs.astral.sh/uv/), Rust (for
`cargo`), and the Tauri CLI (`cargo install tauri-cli`).

```bash
git clone https://github.com/resccrew/Hawaii-Agents-Office-.git
cd Hawaii-Agents-Office-
make desktop
```

`make desktop` runs the whole pipeline: sets up `backend/.venv` and
`frontend/node_modules` if missing, builds the backend into a PyInstaller
sidecar binary, statically exports the frontend, then runs `cargo tauri
build`. The result is under
`src-tauri/target/release/bundle/macos/Hawaii Agents Office.app` (and a
`.dmg` next to it in `bundle/dmg/`, same Gatekeeper note as Option A). See
`scripts/build-desktop.sh` if you want to run the steps individually.

### Hooks (either option — this is what makes agents appear in the office at all)

The hooks package registers itself as a `studio-ops-hook` CLI tool, then
wires that CLI into Claude Code's global hook config
(`~/.claude/settings.json`). Without this step the app will start, but the
office will stay empty — nothing tells it a Claude Code session exists.

```bash
cd hooks
uv tool install --editable .
uv tool update-shell   # only needed once, if `studio-ops-hook` isn't found on PATH afterwards
python manage_hooks.py install --hook-cmd studio-ops-hook
```

This is safe to run alongside other hook-based tools — it only *appends* a
`studio-ops-hook <event>` entry per hook type, backing up your existing
`settings.json` to `settings.json.bak` the first time it touches it. Run
`python manage_hooks.py uninstall --hook-cmd studio-ops-hook` to remove it
later.

## Dev mode (browser, hot-reloading)

```bash
make dev
```

Runs the backend (`uvicorn --reload`, `:8010`) and frontend (`next dev`,
`:3010`) together; Ctrl+C stops both. Sets up `backend/.venv` and
`frontend/node_modules` on first run if missing, same as `make desktop`.
Open **http://localhost:3010**.

> **Ports are not arbitrary.** The backend's CORS policy only allows
> `http://localhost:3010`, the frontend's default backend URL (Settings →
> General) is hardcoded to `http://localhost:8010`, and `src-tauri/tauri.conf.json`'s
> `devUrl` also points at `:3010` for `tauri dev`. If you already have
> something else running on 3010/8010, either free the port or change all
> three places together, plus the CORS `allow_origins` list in
> `backend/app/main.py`.

## Configuring API keys

Open **settings** in the toolbar and fill in whichever providers you want to
use — keys are saved to `~/studio-ops/state/settings.json` (outside the repo,
never committed). Equivalently, set environment variables before starting the
backend (an env var is used as a fallback whenever no value is saved in
Settings):

```
STUDIO_OPS_OPENAI_API_KEY
STUDIO_OPS_OPENAI_MODEL
STUDIO_OPS_GEMINI_API_KEY
STUDIO_OPS_GEMINI_MODEL
STUDIO_OPS_OLLAMA_BASE_URL
STUDIO_OPS_OLLAMA_MODEL
STUDIO_OPS_NANOBANANA_API_KEY
```

Claude agents need no key here — they run through your existing `claude` CLI
login.

## Running the tests

```bash
make test
```

Runs backend `pytest` and frontend `npm run typecheck` (setting up
`backend/.venv`/`frontend/node_modules` first if missing). CI runs the same
two checks plus `cargo check` for `src-tauri/` on every push and PR — see
the badge at the top of this file.

> `test_chat_bridge.py` has two tests that exercise a real `claude -p`
> subprocess against a live server on `:8010` — since that's often already
> running (this is a personal daily-use app), they're gated behind an
> explicit opt-in so a plain `make test`/`pytest` run doesn't accidentally
> hit whatever's already listening there: `STUDIO_OPS_LIVE_TESTS=1 pytest
> -k <name>` (individually — they're documented as order-sensitive
> back-to-back in one session).

## Troubleshooting

- **Gatekeeper says the app is damaged / can't be opened** — right-click the
  app in Applications and choose **Open** once (see Install above); this is
  expected for an ad-hoc-signed, non-notarized build.
- **"The office is empty / nothing shows up"** — the hooks probably aren't
  installed, or `~/.claude/settings.json` points `studio-ops-hook` at a
  binary that isn't on PATH. Re-run the hooks step, or check
  `which studio-ops-hook`.
- **Chat / file attachments silently do nothing, or "Failed to fetch"** (dev
  mode) — make sure you're on **http://localhost:3010**, not some other port
  a different local project happens to be using. If you've worked on other
  Next.js apps on this machine, it's easy to land on the wrong one at the
  default port 3000.
- **Chat calls hang for ~2 minutes then error out** — `claude -p` has no TTY
  to answer a permission prompt with; this only happens for hook-observed
  interactive sessions (spawned agents run with `bypassPermissions` in their
  own isolated workspace and don't hit this).
- **A cat/dev sprite never disappears from the office** — known open issue:
  `SubagentStop` occasionally fails to match the `agent_id` from
  `SubagentStart`, leaving that sub-agent's state stuck. Restarting the
  backend clears it.
- **`make desktop` fails on the `.dmg` bundling step, but the `.app` built
  fine** — that step drives Finder over AppleScript to lay out icons, which
  can time out in a non-interactive/background shell (no real GUI session
  to deliver the AppleEvent to). Run it from a normal Terminal window; the
  `.app` under `bundle/macos/` is already usable even if the `.dmg` step
  fails.

## Dev-mode platform notes

The dev-mode frontend/backend (Option B above, or `make dev`) have no
macOS-only code — no `osascript`, no POSIX-only syscalls, all paths go
through `pathlib.Path.home()` — and run fine on Linux, or on Windows inside
**WSL**. The packaged desktop app (`make desktop`, and the Releases `.dmg`)
is macOS-only for now; `src-tauri/tauri.conf.json`'s bundle config and this
project's CI only target macOS. On **native** Windows Python (dev mode,
outside WSL), the backend invokes the `claude` CLI via
`asyncio.create_subprocess_exec("claude", ...)` — Windows' `CreateProcess`
doesn't resolve `PATHEXT` the way a shell does, so an npm-installed
`claude.cmd` shim may not be found even though `claude` works fine from a
normal terminal; `backend/app/services/claude_cli_service.py` would need a
small fix to resolve the full shim path explicitly.

## License

[MIT](LICENSE).
