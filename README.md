# UMI

Personal multimodal AI assistant. LLM is the reasoning engine, not the app — backend/orchestrator controls all access to tools, filesystem, email, hardware.

Source of truth docs:
- [PRD.md](PRD.md) — product scope
- [TRD.md](TRD.md) — technical requirements
- [Architecture.md](Architecture.md) — system design
- [Phase.md](Phase.md) — execution roadmap, phase-by-phase

## Status

Phase 0 (foundation) complete. Phase 1 (UMI Core) complete — verified end-to-end with a real LLM reply. **Phase 1.5 (Desktop Shell & Launcher)** — Electron shell, startup state machine, greeting, modular startup music, background launcher and double-clap detector implemented. **Phase 2 (Database & Memory)** implemented and live — conversations and memories persist to Supabase/PostgreSQL, UMI injects retrieved memories + history into LLM context. **Phase 3 (Tool System)** implemented — registry → validation → permission → execution pipeline with calculate/get_time/task tools. **Phase 4 (Tasks & Productivity)** complete — tasks with optional due dates via REST API, TasksPanel UI, and natural-language LLM tools (`create_task`/`list_tasks`/`complete_task`/`update_task`/`delete_task`). **Phase 5 (Gmail)** implemented — OAuth connect, `~/.umi/gmail_token.json` (0600), email list/search/summarize with importance ranking, drafts, explicit-send confirmation, and a GmailPanel UI; Gmail + Calendar live-verified with connected Google account. **Phase 6 (Google Calendar) complete** — events list/create/modify/delete + summaries with confirmation-gated deletes, reusing the shared OAuth token. **Phase 7 (Voice) implemented** — continuous one-click voice session: ElevenLabs Scribe realtime STT (single-use token via `/stt/token`) with Web Speech fallback, local pyttsx3 TTS (`/tts` → WAV), SSE-streamed replies split into sentences and spoken with barge-in + echo guard, and voice-tuned replies (`voice:true` → 200-token fast model). Live-verified TTS/token/streaming; the natural-conversation mic test is the final manual gate. **Phase 7.5 (Google Drive/Sheets/Docs/YouTube) implemented** — the one existing OAuth connection now grants all seven scopes (full `drive`, `spreadsheets`, `documents`, `youtube`) in a single consent; 16 new `google_*` tools (reads pr-1, creates pr-2, writes/publishes/destroys gated by confirmation) across four services mirroring the Calendar pattern; `GET /google/status` reports granted-vs-required scopes and a reconnect prompt appears automatically for older 3-scope tokens; YouTube uploads default to `private`. Live E2E across Services pending one reconnect. 259 backend + 40 frontend + 8 desktop tests pass. **Phase 7.8 (Discord + Telegram integrations) implemented** — Umi is reachable as a strictly owner-only second channel from Discord DMs/servers and Telegram private chats: adapter workers (discord.py 2.4.0 thread; httpx long-poll) normalize messages into `PlatformMessage`s and reuse the exact desktop pipeline (same LLM, Boss profile, tools, memory), each platform gets its own conversation thread (new `source`/`conversation_key` columns, migration `0002`), unknown senders are refused politely with zero LLM/database/tool interaction, and confirm-gated actions stay blocked (no bypass). `GET /integrations/status` + two GmailPanel chips surface live state without exposing tokens; credentials live only in `backend/.env` and are never logged. Backend 297 tests incl. all integration suites; frontend 43; desktop 8; lint + build clean. Live smoke tests pending the Boss adding real credentials.

## Stack

- Frontend: Next.js (`/frontend`)
- Backend: Python / FastAPI (`/backend`)
- Desktop shell: Electron (`/desktop`) — spawns/manages both servers, drives the startup state machine
- Launcher: Python / sounddevice (`/launcher`) — double-clap activation (lightweight, no LLM/backend load)
- DB: Supabase / PostgreSQL (Phase 2)
- LLM: NVIDIA Nemotron 3 Ultra, via OpenRouter, behind a provider-agnostic abstraction (`backend/app/llm/manager.py`)

## Development workflow (Claude Code)

Claude Code uses the [Superpowers](https://github.com/obra/superpowers) plugin as its engineering methodology, installed from Anthropic's official marketplace (`superpowers@claude-plugins-official`, user scope). It is a **development methodology only** — it is not part of Umi's runtime and adds no runtime dependencies. The stack above is unchanged.

The workflow it encourages: understand the goal → brainstorm/clarify → confirm the spec → implementation plan → write tests first (TDD) → implement → review → run tests → verify actual behavior → report evidence.

## Dev setup

### Backend

```
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in LLM_API_KEY + Phase 2 Supabase values (below)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Run tests: `.venv/bin/python -m pytest tests/ -q`

### Phase 2 — Supabase setup (backend)

1. Create a project in the [Supabase dashboard](https://supabase.com/).
2. **Project Settings → Database → Connection string → Session pooler**: copy the `postgresql://...` string into `backend/.env` as `DATABASE_URL` (keep `?sslmode=require`).
3. **Project Settings → API**: copy Project URL → `SUPABASE_URL`, and the anon + service_role keys as `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`.
4. Create the local owner as a real Supabase Auth user (the DB FKs point at `auth.users`): run the admin create-user call with the service role key, or add one in Dashboard → Authentication → Users. Put its UUID in `UMI_OWNER_ID`.
5. The schema creates itself on first backend startup (`init_db`). Extra scaffold migrations live in `backend/migrations/`.
6. Leave `DATABASE_URL` empty to run without persistence — chat keeps working, memory/conversation endpoints return 503.

### Frontend

```
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Opens on `http://localhost:3000`, talks to backend on `http://localhost:8000`.

### Desktop shell (Phase 1.5)

```
cd desktop
npm install        # pulls Electron (binary downloads on first run)
npm start          # launches UMI as a desktop app
```

The shell serves the Next.js UI (build with `npm run build` in `frontend/` first for production mode) and starts the Python backend automatically. Set `UMI_MUSIC_FILE=/path/to/track.mp3` in `desktop/.env` (copy `.env.example`) to enable a user-supplied startup track.

Run tests: `npm test`

### Background launcher + double clap (Phase 1.5)

```
cd launcher
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python main.py --test      # dry run: log detections, don't launch
.venv/bin/python main.py --calibrate # print live mic peak levels to tune sensitivity
.venv/bin/python main.py             # live: double clap launches the desktop app
```
