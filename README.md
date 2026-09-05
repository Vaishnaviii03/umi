# UMI

Personal multimodal AI assistant. LLM is the reasoning engine, not the app — backend/orchestrator controls all access to tools, filesystem, email, hardware.

Source of truth docs:
- [PRD.md](PRD.md) — product scope
- [TRD.md](TRD.md) — technical requirements
- [Architecture.md](Architecture.md) — system design
- [Phase.md](Phase.md) — execution roadmap, phase-by-phase

## Status

Phase 0 (foundation) complete. Phase 1 (UMI Core) complete — verified end-to-end with a real LLM reply. **Phase 1.5 (Desktop Shell & Launcher)** in progress — Electron shell, startup state machine, greeting, modular startup music, background launcher and double-clap detector implemented. **Phase 2 (Database & Memory)** implemented and live — conversations persist to Supabase/PostgreSQL, UMI injects retrieved memories + history into LLM context, memory add/delete via API and UI, 19 backend tests pass.

## Stack

- Frontend: Next.js (`/frontend`)
- Backend: Python / FastAPI (`/backend`)
- Desktop shell: Electron (`/desktop`) — spawns/manages both servers, drives the startup state machine
- Launcher: Python / sounddevice (`/launcher`) — double-clap activation (lightweight, no LLM/backend load)
- DB: Supabase / PostgreSQL (Phase 2)
- LLM: NVIDIA Nemotron 3 Ultra, via OpenRouter, behind a provider-agnostic abstraction (`backend/app/llm/manager.py`)

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
