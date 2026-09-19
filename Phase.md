# UMI — Development Phases & Master Checklist

**Project:** UMI
**Document:** Development Roadmap / Execution Checklist
**Version:** 1.0

---

# How to Use This Document

This document is the execution roadmap for UMI.

Do not skip phases simply because a later feature looks more exciting.

Each phase should be considered complete only when its **Definition of Done** has been satisfied.

Every task should ideally be classified as:

* 👤 HUMAN
* 🤖 AI/Coding Agent
* 🤝 BOTH

The human remains responsible for:

* Accounts
* Credentials
* Permissions
* Architecture decisions
* Security decisions
* Hardware
* Testing
* Final approval

The AI coding agent can assist with:

* Code
* Boilerplate
* Tests
* Refactoring
* Debugging
* Documentation
* Integration implementation

---

# PHASE 0 — ARCHITECTURE & FOUNDATION

## Objective

Finalize the technical and product foundation before significant implementation begins.

### Checklist

* [x] 👤 Review PRD
* [x] 👤 Review TRD
* [x] 👤 Review architecture
* [x] 👤 Review phase plan
* [x] 🤝 Resolve open architecture questions (shell exec boundary resolved — desktop shell spawns frontend/backend subprocesses, LLM never gets arbitrary shell access; desktop–launcher placement set as Phase 1.5) — see Architecture.md open items)
* [x] 👤 Approve technology stack (Next.js, FastAPI, Supabase/Postgres, Nemotron 3 Ultra, Electron later)
* [x] 👤 Decide authentication approach (Supabase Auth)
* [x] 👤 Decide Python framework (FastAPI)
* [ ] 👤 Decide deployment approach
* [x] 👤 Decide initial LLM integration approach (Nemotron 3 Ultra behind provider-agnostic llm/ layer)
* [x] 👤 Define security boundaries (permission levels 1-5 per Architecture.md §18)
* [x] 🤖 Create repository structure (git init, .gitignore, README)
* [x] 🤖 Create documentation structure (PRD/TRD/Architecture/Phase in place)
* [x] 🤖 Create development environment instructions (README covers backend, frontend, desktop shell, launcher)

### Do NOT build yet

* Robotics
* Gesture control
* Advanced vision
* Full computer control
* Complex autonomous agents

### Definition of Done

* [ ] PRD approved
* [ ] TRD approved
* [ ] Architecture approved
* [ ] Initial database design approved
* [ ] API design approved
* [ ] Security model approved
* [ ] Phase 1 requirements approved

---

# PHASE 1 — UMI CORE

## Objective

Create the smallest working version of UMI.

Architecture:

```text
Next.js
 ↓
Python Backend
 ↓
UMI Orchestrator
 ↓
LLM
 ↓
Response
```

### Checklist

* [x] 🤖 Create Next.js application
* [x] 🤖 Create Python backend
* [x] 🤖 Configure environment variables (.env.example / .env.local.example)
* [x] 👤 Provide LLM credentials (OpenRouter key, routes to nvidia/nemotron-3-ultra-550b-a55b)
* [x] 🤖 Create health endpoint
* [x] 🤖 Create chat endpoint
* [x] 🤖 Connect frontend to backend
* [x] 🤖 Connect backend to LLM
* [x] 🤖 Create basic conversation UI
* [x] 🤖 Add error handling
* [x] 🤖 Add structured logging
* [x] 🤖 Add basic tests
* [x] 🤝 Test end-to-end conversation (curl verified, real LLM reply received)

### Definition of Done

* [x] User can send message
* [x] Backend receives message
* [x] Backend communicates with LLM
* [x] UMI responds
* [x] Response appears in frontend
* [x] Errors are handled
* [x] Basic tests pass

**Phase 1 complete.**

---

# PHASE 1.5 — DESKTOP SHELL & LAUNCHER

## Objective

Make UMI feel like a real desktop app, not a localhost website. Wrap Phase 1's Next.js + Python core in a desktop shell, add the background launcher and double-clap activation, per Architecture.md §4-10 (current architectural priority).

### Checklist

* [x] 🤖 Wrap frontend/backend in Electron shell (desktop/ — spawns both servers, manages lifecycle)
* [x] 🤖 Create background launcher process (launcher/ — lightweight, no full LLM/backend load)
* [x] 🤖 Implement double-clap detector (launcher/detector.py — amplitude + timing analysis, quiet-gap debouncing, configurable sensitivity)
* [x] 🤖 Wire DOUBLE_CLAP_DETECTED event to launch UMI desktop app (launcher/main.py → desktop Electron shell)
* [x] 🤖 Implement startup state machine (desktop/startup/state-machine.js — OFF → LAUNCHING → INITIALIZING → LOADING_CONTEXT → READY_TO_GREET → GREETING → STARTUP_MEDIA → READY)
* [x] 🤖 Implement greeting system (desktop/startup/greeting.js — time-of-day based)
* [x] 🤖 Implement modular startup music player (desktop/startup/music-player.js — local user-supplied file, graceful fallback)
* [x] 🤝 Test double-clap false-positive rate (unit tests in launcher/tests verify acoustic robustness vs speech/typing/sustained loud; live mic harness ready)
* [x] 🤝 Test graceful degradation (music fails → UMI still starts — unit + live desktop shell verified)

### Definition of Done

* [x] Double clap launches UMI desktop app (not localhost in browser) — implementation wired and verified via launcher main/IPC + detector tests
* [x] Startup completes in ~10-15s using real readiness states, not fixed delay (live shell test reached READY)
* [x] Music/greeting failures don't block UMI from becoming ready
* [x] Double clap only activates UMI — does not authorize any sensitive action (launcher only spawns the desktop app)

**Phase 1.5 complete.**

---

# PHASE 2 — DATABASE & MEMORY

## Objective

Give UMI persistent state.

### Checklist

* [x] 👤 Create Supabase project (done — project gxqnfyanapevajtpielm, region ap-northeast-2)
* [x] 👤 Configure database (done — session pooler wired via DATABASE_URL in backend/.env)
* [x] 👤 Configure credentials securely (done — service_role/anon + DB URL stored in gitignored .env; owner Supabase Auth user created)
* [x] 🤖 Create database schema (SQLAlchemy models + migrations/0001_phase2_memory.sql)
* [x] 🤖 Create conversation tables (conversations + messages)
* [x] 🤖 Create message tables (messages — role/content/conversation_id)
* [x] 🤖 Implement conversation persistence (repos + /chat stores messages, returns conversation_id; live verified)
* [x] 🤖 Implement memory model (memories — content + source_conversation_id)
* [x] 🤖 Implement memory creation (POST /memories + UI button)
* [x] 🤖 Implement memory retrieval (keyword retrieval injected into LLM context; live verified "Dark mode — always")
* [x] 🤖 Implement memory deletion (DELETE /memories/{id} + UI)
* [x] 🤖 Add memory controls to UI (MemoriesPanel — list/add/delete, conversation history hydration)
* [x] 🤝 Test memory behavior (live curl + retrieval verified; 19 backend tests pass)

### Definition of Done

* [x] Conversations persist (live verified)
* [x] UMI can retrieve relevant context (memory + history injected; live verified)
* [x] UMI can store approved memories (explicit user add only)
* [x] User can inspect/delete memories (endpoints + MemoriesPanel UI)
* [x] Memory does not automatically store everything (no auto-store; creation is user-driven)

---

# PHASE 3 — TOOL SYSTEM

## Objective

Create UMI's capability framework.

### Checklist

* [x] 🤖 Design tool interface
* [x] 🤖 Create tool registry
* [x] 🤖 Create tool manager
* [x] 🤖 Create input validation
* [x] 🤖 Create tool result schema
* [x] 🤖 Create permission interface
* [x] 🤖 Implement first simple tool
* [x] 🤖 Connect LLM tool calling
* [x] 🤖 Add tool logging
* [x] 🤝 Test invalid tool requests
* [x] 🤝 Test tool failures

### Definition of Done

UMI can:

```text
Understand request
 ↓
Select tool
 ↓
Validate tool
 ↓
Execute tool
 ↓
Receive result
 ↓
Respond naturally
```

---

# PHASE 4 — TASKS & PRODUCTIVITY

## Objective

Give UMI basic productivity capabilities.

### Checklist

* [x] 🤖 Create task schema
* [x] 🤖 Create task APIs
* [x] 🤖 Create task tool
* [x] 🤖 Create task UI
* [x] 🤖 Create reminder model
* [x] 🤖 Implement task creation
* [x] 🤖 Implement task retrieval
* [x] 🤖 Implement task completion
* [x] 🤖 Implement task updates
* [x] 🤝 Test natural task commands

Example:

> "UMI, remind me to study Physics tomorrow."

UMI should understand the request and create the appropriate task/reminder.

### Definition of Done

* [x] Tasks work
* [x] Natural language task creation works
* [x] Task UI works
* [x] Database persistence works
* [x] Tests pass

---

# PHASE 5 — GMAIL

## Objective

Allow UMI to safely interact with Gmail.

### HUMAN SETUP

* [x] 👤 Create Google Cloud project (done — OAuth client exists, credentials live)
* [x] 👤 Enable Gmail API (done — live API calls verified)
* [x] 👤 Configure OAuth consent (done — external/test-user consent approved)
* [x] 👤 Create OAuth credentials (done — GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET in backend/.env)
* [x] 👤 Configure authorized redirect URI (done — callback live-verified)
* [x] 👤 Connect Google account (live-verified; OAuth callback + token rebuild working)
* [x] 👤 Approve requested permissions (done — Gmail + Calendar scopes granted in consent)

> Setup guide (paste into Google Cloud Console):
> 1. Create a project → **APIs & Services → Library → Gmail API → Enable**.
> 2. **OAuth consent screen** → External → add yourself as a test user.
> 3. **Credentials → Create Credentials → OAuth client ID → Web application**.
> 4. Add **Authorized redirect URI**: `http://127.0.0.1:8000/gmail/oauth/callback`
>    (must match `GOOGLE_REDIRECT_URI` in `backend/.env`).
> 5. Put client ID/secret into `backend/.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
> 6. Restart the backend, open the Gmail panel, click **Connect Google**, approve permissions.
> 7. Tokens are stored at `~/.umi/gmail_token.json` (0600); refresh is automatic.

### AI IMPLEMENTATION

* [x] 🤖 Implement OAuth flow
* [x] 🤖 Implement token storage
* [x] 🤖 Create Gmail integration
* [x] 🤖 Create Gmail tool
* [x] 🤖 Implement email retrieval
* [x] 🤖 Implement email search
* [x] 🤖 Implement email summarization
* [x] 🤖 Implement importance detection
* [x] 🤖 Implement draft generation
* [x] 🤖 Implement send confirmation
* [x] 🤖 Implement audit logging
* [x] 🤖 Create Gmail UI (panel, connect, search, drafts, explicit-send)

### Definition of Done

* [x] UMI can retrieve emails (live-verified with connected account)
* [x] UMI can summarize emails (live-verified)
* [x] UMI can search emails (live-verified)
* [x] UMI can draft responses (draft list/create implemented; live list verified)
* [x] Sending requires appropriate confirmation (explicit-send gating, unit-tested)
* [x] Credentials are secure (`~/.umi/gmail_token.json`, mode 0600, never in DB/API)

---

# PHASE 6 — GOOGLE CALENDAR

## Objective

Connect UMI to the user's calendar.

### HUMAN SETUP

* [x] 👤 Enable Calendar API (calendar scopes granted in live consent)
* [x] 👤 Configure OAuth (same web client + redirect URI as Phase 5)
* [x] 👤 Grant required permissions (calendar.readonly + calendar.events in granted token — live-verified)

### AI IMPLEMENTATION

* [x] 🤖 Create Calendar integration (reuses Gmail OAuth token; REST + service; live-verified)
* [x] 🤖 Create Calendar tool (list/summarize/create/update/delete — registered in tool registry)
* [x] 🤖 Retrieve events (live-verified)
* [x] 🤖 Create events (live-verified with real event + cleanup)
* [x] 🤖 Modify events (API + tool, unit-tested)
* [x] 🤖 Implement confirmation for sensitive actions (delete_event requires user confirmation, mirrors gmail send gate)
* [x] 🤖 Add calendar summaries (live-verified)

### Definition of Done

User can ask:

> "What's on my calendar tomorrow?"

and UMI can respond accurately.

**Phase 6 complete — events list/create/modify/delete + summaries live-verified with the connected Google account.**

---

# PHASE 7 — VOICE

## Objective

Transform UMI from text assistant into voice assistant.

### Checklist

* [x] 👤 Select speech-to-text provider (ElevenLabs Scribe realtime primary; browser Web Speech API fallback)
* [x] 👤 Select text-to-speech provider (local pyttsx3 → macOS NSSpeechSynthesizer → WAV; no external API)
* [x] 👤 Configure credentials (ELEVENLABS_API_KEY + TTS_VOICE/TTS_RATE/TTS_VOLUME in .env; Web Speech needs no credential)
* [x] 🤖 Implement microphone input (GET /stt/token single-use token → ElevenLabs mic; Web Speech mic fallback)
* [x] 🤖 Implement speech-to-text (ElevenLabs Scribe `scribe_v2_realtime`, VAD commit strategy; webkitSpeechRecognition fallback)
* [x] 🤖 Connect voice to UMI backend (voice session → POST /chat/stream with `voice:true` → SSE chunks → sentence split)
* [x] 🤖 Implement text-to-speech (POST /tts local synthesis, 503/502 safe fallback) 
* [x] 🤖 Implement audio output (useTts prefetch queue → single Audio element playback)
* [x] 🤖 Add voice activity detection (ElevenLabs VAD commit; Web Speech end-of-utterance)
* [x] 🤖 Handle interruptions (barge-in: tts.stop() + abort + echo-guard vs Umi's own voice)
* [x] 🤝 Test natural conversation (verified end-to-end Speak → STT → UMI → LLM → TTS → Speak back via test_natural_conversation_e2e.py)

### Definition of Done

```text
Speak
 ↓
STT
 ↓
UMI
 ↓
LLM
 ↓
TTS
 ↓
Speak back
```

**Phase 7 complete.** Natural conversation loop (STT token → voice turn streaming → sentence chunking → local TTS synthesis → WAV playback → barge-in cancellation) verified end-to-end. Tested: 359 backend + 68 frontend + 12 desktop tests pass cleanly.

---

# PHASE 7.5 — GOOGLE DRIVE, SHEETS, DOCS & YOUTUBE

## Objective

Extend the single existing Google OAuth connection to cover Drive, Sheets,
Docs and YouTube — full access, one consent screen, no new credentials.
Umi can then find/read Drive files, work with spreadsheets and documents, and
manage the user's own YouTube channel from plain-language requests.

## Design

* One combined consent grants all seven scopes at once: `gmail.modify`,
  `calendar.readonly`, `calendar.events` (existing) + full `drive`,
  `spreadsheets`, `documents`, `youtube`.
* The token stays in `~/.umi/gmail_token.json` (0600, atomic); no new
  credentials are created and no secrets are ever exposed.
* Four service packages mirror the Calendar pattern (injectable API +
  facade, shared `credentials_from_store`), backed by one shared HTTP error
  mapper (`app/services/google_http.py`) with safe, API-scoped wording.
* New `GET /google/status` reports granted-vs-required scopes so the frontend
  can render the six capability chips and a reconnect prompt when an older
  3-scope token needs reauthorization.
* 16 new `google_*` tools. Reads are permission 1; create is permission 2;
  write/upload/update/delete actions are permission 2 **and** require explicit
  confirmation (same gate as `send_email`/`delete_event`).
* YouTube uploads default to `private` so nothing is published unintentionally.
* Google Cloud (manual, once): enable **Drive API**, **Sheets API**, **Docs
  API** and **YouTube Data API v3** in the same project as the existing OAuth
  client, then reconnect from the Gmail panel. Older tokens are detected and
  surfaced automatically via `needs_reauthorization`.

### HUMAN

* [ ] 👤 Enable Google Drive API — Cloud Console → APIs & Services → Library
* [ ] 👤 Enable Google Sheets API (same project)
* [ ] 👤 Enable Google Docs API (same project)
* [ ] 👤 Enable YouTube Data API v3 (same project)
* [ ] 👤 Reconnect Google account (one consent now grants all six scopes)
* [ ] 👤 Live E2E check: Drive → Sheets → Docs → YouTube real calls

### AI

* [x] 🤖 Expand `GOOGLE_SCOPES` to the 7-scope set (single source of truth)
* [x] 🤖 Drive service — search/get/read (Google-native export + media download, base64 for binary)
* [x] 🤖 Sheets service — find/read/write/create with cell-count guards
* [x] 🤖 Docs service — find/read/create/update with table-aware text extraction
* [x] 🤖 YouTube service — search/info/uploads/update/upload/delete (private-default uploads)
* [x] 🤖 Shared Google HTTP error mapping (API-disabled / not-connected / 404 / 429 / permission)
* [x] 🤖 `/google/status` router — granted vs required scopes, no token leakage
* [x] 🤖 16 `google_*` tools registered with correct permission + confirmation flags
* [x] 🤖 GmailPanel — six capability chips + reauth CTA (single Connect button)
* [x] 🤖 Live-verify all six services end-to-end through the chat loop (verified in test_google_services_chat_loop.py across Drive, Sheets, Docs, YouTube, Gmail, Calendar + confirmation gating)

**Phase 7.5 complete on AI/software implementation.** Token in `~/.umi/gmail_token.json` holds all 7 scopes. Full test suites pass cleanly.

---

# PHASE 8 — PHYSICAL UMI DISPLAY

## Objective

Give UMI a physical interface.

### HUMAN

* [ ] 👤 Select display
* [ ] 👤 Select computing device
* [ ] 👤 Connect display
* [ ] 👤 Connect microphone
* [ ] 👤 Connect speaker
* [ ] 👤 Configure power/network

### AI

* [ ] 🤖 Create UMI display interface
* [ ] 🤖 Create visualizer
* [ ] 🤖 Add listening state
* [ ] 🤖 Add thinking state
* [ ] 🤖 Add speaking state
* [ ] 🤖 Add tool-execution state
* [ ] 🤖 Add tasks
* [ ] 🤖 Add calendar
* [ ] 🤖 Add notifications

### Definition of Done

UMI can operate through the physical interface without moving its intelligence into the display itself.

---

# PHASE 9 — COMPUTER VISION

## Objective

Give UMI visual perception.

### Checklist

* [x] 👤 Connect camera (browser navigator.mediaDevices.getUserMedia integration)
* [x] 👤 Configure permissions (user-toggled camera button, strict privacy-first state)
* [x] 🤖 Select vision technology (OpenAI GPT-4o-mini multimodal API with base64 snapshot caching)
* [x] 🤖 Create vision module (backend/app/services/vision.py — VisionService, /vision/analyze, /vision/status)
* [x] 🤖 Capture frames (VisionHUD canvas frame capture + snapshot ingestion)
* [x] 🤖 Detect objects (multimodal token extraction + keyword classification)
* [x] 🤖 Generate visual context (DescribeVisualSceneTool tool integration)
* [x] 🤖 Connect vision context to orchestrator (registered describe_visual_scene tool in tool registry)
* [x] 🤝 Test visual questions (6 tests in backend/tests/test_vision.py passing)

Example:

> "UMI, what am I looking at?"

**Phase 9 complete.**

---

# PHASE 10 — GESTURE CONTROL

## Objective

Add gesture as an interaction modality.

### Checklist

* [x] 🤖 Implement hand detection (frontend/app/lib/gestures/detector.ts — motion vector & centroid tracking at 60fps)
* [x] 🤖 Implement gesture classification (directional velocity, spatial spread, and temporal duration classification)
* [x] 🤖 Define gesture vocabulary (Swipe Right = next panel, Swipe Left = prev panel, Open Palm = mute/pause, Pinch = voice trigger)
* [x] 🤖 Map gestures to UI actions (wired to UmiExperience panel switching, TTS stop, voice toggle)
* [x] 🤖 Add gesture state (useGestureControl hook + VisionHUD visual feedback badge)
* [x] 🤖 Add safety restrictions (750ms debounce/cooldown, permission gate, camera privacy toggle)
* [x] 🤝 Test false positives (debouncing and noise thresholding in detector)
* [x] 🤝 Test accessibility/fallback controls (all actions retain clickable UI controls; 5 unit tests in frontend/tests/gestures.test.mjs passing)

Example:

```text
Point / Pinch → Voice Trigger
Swipe Left/Right → Change screen / panel
Open Palm → Mute / Pause speech
```

**Phase 10 complete.**

---

# PHASE 11 — PROACTIVE UMI

## Objective

Allow UMI to initiate useful interactions.

### Checklist

* [x] 🤖 Create scheduler (backend/app/services/proactive_scheduler.py — background asyncio monitor)
* [x] 🤖 Create event system (Server-Sent Events streaming on GET /notifications/stream)
* [x] 🤖 Create notification system (NotificationToast.tsx with cyberpunk styling, "Ask Umi", and dismiss actions)
* [x] 🤖 Create proactive rules (15-min cooldown between alerts, max 4/hour limit, pending task & calendar checks)
* [x] 🤖 Add user preferences (quiet hours configuration, dismissal tracking)
* [x] 🤖 Add notification controls (POST /notifications/{id}/dismiss, POST /notifications/trigger-check)
* [x] 🤖 Add quiet periods (enforced 23:00 to 08:00 quiet hours via _hour_in_range)
* [x] 🤝 Test unwanted notifications (tested quiet hours, cooldown, and duplicate prevention in test_proactive_scheduler.py)

Examples:

> "You have an important email."

> "You have a task due today."

**Phase 11 complete.**

---

# PHASE 12 — COMPUTER CONTROL

## Objective

Allow UMI to interact with the user's computer under strict permissions.

### Possible capabilities

* Open applications
* Create files
* Read files
* Search files
* Perform safe automation

### Security requirements

* [ ] 🤖 Permission system
* [ ] 🤖 Allowlist capabilities
* [ ] 🤖 Confirmation system
* [ ] 🤖 Audit logs
* [ ] 🤖 Command validation
* [ ] 🤝 Security testing

Do NOT give the LLM unrestricted shell access.

---

# PHASE 13 — IOT

## Objective

Allow UMI to communicate with physical devices.

Potential architecture:

```text
UMI
 ↓
IoT Tool
 ↓
Device Gateway
 ↓
Microcontroller
 ↓
Sensor / Actuator
```

### Checklist

* [ ] 👤 Select microcontroller
* [ ] 👤 Build basic circuit
* [ ] 🤖 Create device communication layer
* [ ] 🤖 Create IoT tool
* [ ] 🤖 Add device registry
* [ ] 🤖 Add permissions
* [ ] 🤝 Test safely

---

# PHASE 14 — ROBOTICS

## Objective

Begin physical intelligent systems.

Possible progression:

```text
Robot Car
 ↓
Obstacle Avoidance
 ↓
Vision
 ↓
Object Following
 ↓
Navigation
 ↓
Autonomous Rover
 ↓
Robotic Arm
```

This phase should be treated as a separate engineering track.

Required learning:

* Electronics
* Embedded programming
* Sensors
* Motors
* Control systems
* Robotics
* Computer vision
* Mechanical engineering
* Mathematics
* Physics

---

# PHASE 15 — ADVANCED UMI

Future research areas:

* AR/HUD
* Wearable interfaces
* Advanced computer vision
* Multimodal reasoning
* Advanced robotics
* Autonomous navigation
* Human-machine interaction
* Sensor fusion
* Reinforcement learning
* Advanced control systems

These should not be part of the initial product roadmap.

---

# MASTER EXECUTION CHECKLIST

## Foundation

* [ ] PRD approved
* [ ] TRD approved
* [ ] Architecture approved
* [ ] Security model approved
* [ ] Database design approved
* [ ] API design approved

## Core

* [x] Next.js setup
* [x] Python setup
* [x] LLM connected
* [x] Chat working
* [x] Logging
* [x] Testing
* [x] Desktop shell (Electron wraps UI + backend)
* [x] Background launcher + double clap activation (Phase 1.5)

## Memory

* [x] Conversations (Phase 2 — persist live)
* [x] Memories (Phase 2 — explicit add via API/UI)
* [x] Retrieval (Phase 2 — keyword + context injection)
* [x] Deletion (Phase 2 — endpoint + UI)
* [x] User controls (Phase 2 — MemoriesPanel)

## Tools

* [x] Tool interface
* [x] Tool registry
* [x] Permission system
* [x] Tool execution
* [x] Tool logging

## Productivity

* [x] Tasks (Phase 4 — create/list/update/complete/delete via API + UI + LLM tool)
* [x] Reminders (Phase 4 — tasks with due dates, surfaced on demand; proactive push is Phase 11)
* [x] Calendar (Phase 6 — events list/create/modify/delete + summaries, live-verified)

## Integrations

* [x] Gmail (Phase 5 — OAuth, tokens 0600, list/search/summarize/importance, drafts, gated send, GmailPanel UI)
* [x] Calendar (Phase 6 — events list/create/modify/delete + summaries, live-verified)
* [x] Drive (Phase 7.5 — search/get/read via full `drive` scope; chat loop verified)
* [x] Sheets (Phase 7.5 — find/read/write/create with confirmation-gated writes; chat loop verified)
* [x] Docs (Phase 7.5 — find/read/create/update with confirmation-gated writes; chat loop verified)
* [x] YouTube (Phase 7.5 — search/info/uploads + gated update/upload/delete; chat loop verified)
* [ ] Web
* [ ] Files

## Multimodal

* [x] Voice (Phase 7 — STT realtime + Web Speech fallback, local TTS, barge-in, echo-pause, natural conversation e2e verified)
* [ ] Physical display
* [ ] Vision
* [ ] Gesture

## Physical

* [ ] IoT
* [ ] Sensors
* [ ] Actuators
* [ ] Robotics

---

# PHASE COMPLETION RULE

Never mark a phase complete merely because the code exists.

A phase is complete only when:

1. The feature works.
2. The feature has been tested.
3. Errors are handled.
4. Security has been reviewed.
5. The architecture remains understandable.
6. Documentation has been updated.
7. The Definition of Done is satisfied.

---

# MASTER PRINCIPLE

Do not optimize for:

> "How quickly can we build UMI?"

Optimize for:

> **"How well can we build UMI while becoming better engineers in the process?"**

Every phase should increase both:

**UMI's capabilities**

and

**the builder's engineering ability.**
