# Hawaii Agents Office

## Описание и цель
Пиксельный офис-визуализатор сессий Claude Code: каждая сессия на машине (интерактивная или
заспавненная) — персонаж в пляжном офисе; сабагенты Task-tool — коты возле хозяина. Можно спавнить
агентов с разными «мозгами» (Claude / OpenAI / Gemini / Ollama), чатиться с ними, вести доску задач.
Цель: довести до уровня портфолио — показать работодателю оркестрацию агентов и md-память, и чтобы
в приложении было приятно находиться.

GitHub: https://github.com/resccrew/Hawaii-Agents-Office- · локально `~/studio-ops`.

**Продукт — десктопное приложение (Tauri), не браузерная версия.** Браузер (localhost:3010) — только режим разработки.
Рабочая копия — `~/studio-ops`. Копия `~/Desktop/Hawaii-Agents-Office-` лежит в iCloud (git там виснет) — не использовать.

## Стек
- `src-tauri/` — Tauri 2 (Rust): окно, фронт из `frontend/out`, backend как sidecar-бинарь `studio-ops-backend`.
  Установленная сборка: `/Applications/Hawaii Agents Office.app` (bundle id `com.studioops.desktop`).
- Терминалы xterm с Claude-агентами в приложении; офис-канвас — в сайдбаре.
- `backend/` — Python 3.12+, FastAPI, uv, pytest. Порт **8010** (CORS только `http://localhost:3010`).
- `frontend/` — Next.js 16, React 19, pixi.js 8 (+ @pixi/react), xstate 5, zustand 5, TypeScript. Порт **3010**.
- `hooks/` — пакет `studio-ops-hook` (uv tool), прописывается в `~/.claude/settings.json`
  через `hooks/manage_hooks.py install|uninstall` (append + бэкап `settings.json.bak`).
- Рантайм-данные вне git: `state/` (реестр агентов, доска задач, `settings.json` с API-ключами),
  `agent-workspaces/`, `chat-uploads/`. `repos/` — чужой клон (Overlay-Agent-Claude), не часть проекта.

## Архитектура
- Наблюдение: хуки Claude Code → `studio-ops-hook` → POST в backend → `event_processor` →
  `state_machine` (idle/working/waiting/arriving/leaving) → WebSocket → frontend.
  Backend сам к Claude Code не ходит ради наблюдения — только принимает события.
- Чат: `chat_bridge` → `claude -p --resume` (или API провайдера) → стрим по `/ws/chat/{session_id}`.
- Агенты/задачи: `agent_registry`, `agent_spawner` (изолированный workspace, bypassPermissions),
  `task_board`, MCP-сервер `app/mcp/studio_ops_mcp.py` (агенты постят задачи), `git_ops` (push в GitHub),
  `ceo`, `autopilot`.
- Frontend: `components/game/*` (pixi-сцена, Dev/Lead/Cat-капсулы), `systems/*` (A*, движение, layout,
  WS-контроллеры), `stores/*` (zustand), `machines/*` (xstate персонажей).

## Правила кодирования
- Тесты после каждого изменения: `cd backend && .venv/bin/python -m pytest -q`, `cd frontend && npx tsc --noEmit`.
  Существующие тесты не менять ради прохождения.
- Ранние return; ошибки провайдеров/CLI не валят WebSocket — graceful fallback.
- Никаких секретов в git (ключи только в `state/settings.json` или env `STUDIO_OPS_*`).
- Ветки: `feat/...`, `fix/...`; merge `--no-ff` в main только при зелёных тестах; без force-push.
- Каждый агент — своя ветка/свои файлы.

## Известные ограничения и риски
- `SubagentStop` иногда не матчит `agent_id` → кот «зависает» до рестарта backend.
- Чат с наблюдаемой интерактивной сессией через `claude -p` может висеть ~2 мин на permission-промпте.
- `test_chat_bridge.py` — 2 теста с живым Claude CLI, чувствительны к порядку (обычно skipped).
- Порты 8010/3010 захардкожены в трёх местах (package.json, CORS в main.py, uiSettingsStore.ts).

## Текущий статус (2026-09-27, вечер)
В main и на GitHub:
- `feat/dx-build-ci` — `make dev|desktop|test`, CI (pytest+tsc+cargo check), release .dmg по тегу, README под десктоп.
- `fix/backend-auth` — токен `~/.studio-ops/api-token` (0600, атомарно) на всех REST/WS, Origin-allowlist на WS,
  токен замаскирован в access-логах, git/workspaces только внутри $HOME, sidecar гасится на всех путях выхода,
  CSP, понятная ошибка при занятом 8010. Фронт ходит только через `systems/apiAuth.ts` (authedFetch, wsUrlWithToken).
- `feat/ux-polish` — окно ≥1100×700, пояснение перед TCC-запросом терминала, доступные модалки (`useFocusTrap`),
  речевые пузыри над персонажами, token-бейдж на карточке (без денег), xstate удалён.
- `feat/agent-memory` — память агентов `agent-workspaces/{id}/MEMORY.md` + факты с frontmatter и общая
  `state/office-memory/`; `core/memory_store.py` (flock, санитизация индекса), REST `/api/v1/memory`, MCP
  `studio_memory_list|read|write` (scope только свой или "office"), при спавне блок инструкций в CLAUDE.md
  воркспейса между маркерами `studio-ops:memory:begin/end`, UI — кнопка 🧠 в чате (MemoryPanel).
- Тесты: backend 74 passed / 2 skipped (live-CLI, включаются `STUDIO_OPS_LIVE_TESTS=1`), tsc и `npm run build` чистые.
  Autouse-фикстура `isolate_real_user_state` в conftest.py — тесты не трогают реальный `~/studio-ops/state`.
В работе: `feat/desktop-native` (уведомления, dock-бейдж, tray, глобальный хоткей).
Известное: `mcp` запинен `<2` (2.x переименовал FastMCP) — нужна миграция; `Cmd+Q` → sidecar гаснет проверено
только SIGTERM'ом, не живым GUI-нажатием. Ревью-отчёты хранятся вне репо (`~/review-private/`) — в них были
приватные данные.
Грабли: `pkill -f <паттерн>` из шелла агента убивает сам шелл; в worktree делать свои venv/node_modules;
общую `~/studio-ops` не переключать на ветки — каждый агент в `~/studio-ops-wt/<имя>`.

## План (по итогам ревью, отчёты вне репо в `~/review-private/`)
Этап 1 — безопасность и фундамент (✅ сделано):
- `fix/backend-auth` (-88): токен `~/.studio-ops/api-token` (0600) на всех REST+WS, проверка Origin на WS,
  валидация cwd терминала — **PTY-терминалы без auth = RCE для любого локального процесса**; allowlist путей
  для git/workspaces; race в broadcast; CSP в Tauri.
- `feat/dx-build-ci` (-2a): path traversal в attachments, .gitignore (repos/), `make dev|desktop|test`,
  pyinstaller в зависимостях, CI (pytest+tsc+cargo check), release .dmg по тегу, README под десктоп, License=MIT.
Этап 2 — фронтенд/UX (✅ сделано, кроме десктоп-фич — в работе): модалки a11y, минимальный размер окна/адаптив, xstate —
  удалить или использовать; речевые пузыри, token/cost-бейджи, десктопные фичи (уведомления, трей).
Этап 3 — «вау» и память: md-память агентов (`agent-workspaces/{id}/MEMORY.md` + MCP read/write), timeline/replay,
  доработка WIP (`wip/jul16-autopilot`: багфиксы и гигиена — брать; CEO-provider → openai — продуктовое решение;
  CORS localhost:3000 — не брать), раздел «How it was built».

## Агенты и зоны ответственности
- **Orchestrator** (главная сессия) — план, раздача задач, merge в main, финальные тесты, этот файл.
- **pravorovnikita-88** — backend/ и hooks/.
- **pravorovnikita-e6** — frontend/ и UX.
- **pravorovnikita-2a** — безопасность, установка (DX), CI, README/подача.
