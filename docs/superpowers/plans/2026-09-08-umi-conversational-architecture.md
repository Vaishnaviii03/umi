# Umi Conversational Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Umi feel like a persistent personal assistant: one reliable, *spoken* greeting at startup (never dropped, never repeated on every reload), continuous context across turns and app restarts, natural conversation instead of strict Q&A, optional idle/proactive conversation with configurable thresholds, a voice loop that keeps listening without self-echo, and honest observability — all without breaking Electron, the Next.js UI, Supabase persistence, Google integrations, local TTS, Web Speech/ElevenLabs STT, Telegram/Discord, or the tools permission model.

## Root Causes (confirmed by code audit, 2026-09-08)

1. **Greeting is dropped (race).** `desktop/index.js:108` → `StartupOrchestrator.start()` (`desktop/startup/orchestrator.js:25`) calls `this._push(STATES.GREETING, …)` → `emitStartupState` → `mainWindow.webContents.send("umi:startup-state", …)` **immediately after** `frontend.ensureRunning()` returns. `FrontendService.ensureRunning` only waits for an HTTP 200 (`desktop/services/frontend.js`). Next.js hydration (which registers the `window.umi.onStartupState` IPC listener in `frontend/app/UmiInterface.tsx:44`) runs *after* the 200 is served, so the GREETING (and READY_TO_GREET/STARTUP_MEDIA/READY) events are sent before any listener exists and are silently dropped.
2. **Greeting is never spoken.** The desktop `player` is the `MusicPlayer` (startup.wav only). The frontend GREETING branch (`UmiInterface.tsx:213`) only *displays* text and requires a manual "Dismiss"; there is no `tts.speak(greeting)` anywhere. The voice session is never started at boot.
3. **Greeting recurs / wrong gating.** Backend treats `conversation_id is None` as "new conversation" (`orchestrator/core.py:208`, `stream_message` :259) and injects `[Greeting: …]` into the LLM context, even though `get_or_create_conversation(db, None)` **reuses** the latest desktop conversation. Because the frontend starts with `conversationIdRef = null` on every page load (hydration never captures the id — `useChat.ts:59`), the *first turn after every restart* is mislabeled "new" and the model is told it's greeting.
4. **Conversation continuity break.** `useChat.ts:52` keeps `conversationIdRef` in memory only; it is not persisted or restored, and the hydration fetch (`/conversations/active/messages`) returns messages without the conversation id. After an app restart the first turn goes out as `conversation_id: null` (context *does* resume server-side because that resolves the latest desktop conversation, but the greeting mislabel from #3 applies).
5. **No idle/proactive anything.** Grep confirms zero idle/proactive/trigger code in backend, frontend, or desktop. Umi is strictly Q&A by construction.
6. **Fast/casual/voice turns are memory-starved.** `fast = voice or len(message) <= CASUAL_MESSAGE_MAX_CHARS` (`orchestrator/core.py:205`) forces `include_memories=False`, so the most common short turns (including voice) never get `retrieve_relevant_memories`. There is also **no automatic memory capture** anywhere — memories exist only via the manual `POST /memories` route.
7. **Voice self-echo path.** During `SPEAKING` the STT session typically stays live (`micPausedRef` is only a flag; `resumeListening` is called in `finishTurn`, `UmiInterface.tsx:93`). Umi can echo-capture her own TTS as a fake user turn.

**Design decisions (flagged for quick adjustment):**
- Greeting **stays a desktop-owned, once-per-launch event**, delivered over a readiness handshake, and **spoken by the frontend via `/tts`** when the GREETING state is entered. The backend greeting *injection* becomes "only when a conversation was actually created in this turn."
- Continuity = **persist `conversation_id` in `sessionStorage`** + a new `GET /session` endpoint that (a) reports the active conversation, (b) tells the frontend whether this is a fresh launch, and (c) hands it the idle policy values.
- Idle/proactive = **frontend-timed trigger** calling a new `proactive` mode on the existing `/chat` pipeline (no new threads on the backend). Backend exposes a pure, unit-tested policy module for the threshold/cooldown math and accepts `proactive` turns through `handle_message`.
- No new tables. One additive column: `Conversation.last_greeted_at` (migration `0003`), used by the greeting-once check. No schema changes to `messages`/`memories`.

## Global Constraints

- Secrets live ONLY in `backend/.env`. Never print/log/commit tokens or auth codes. (Carried from prior phases.)
- Do NOT modify/break: Google/Gmail/Calendar/Drive/Sheets/Docs, voice system, local TTS, Web Speech/ElevenLabs STT, double-clap launcher, tools permission model, desktop process management, Telegram/Discord (incl. their `include_greeting=False` contract).
- The desktop can never be the source of truth for "was this spoken" entitlement — the backend enforces greeting-once; the desktop only *renders/speaks* it.
- Idle turns must share the exact same persist/stream pipeline as normal turns (same conversation, same memory context, `proactive=True` only).
- No UI regressions: `StatusIndicator`, `StartupOverlay`, `VoiceControl`, `Conversation` keep their props/behavior.
- TDD Iron Law: no production code without a failing test first. Frequent small commits. Verification before completion claims.
- Test commands: backend `cd backend && .venv/bin/python3.11 -m pytest -q` (303 baseline); frontend `cd frontend && npm test && npm run lint && npm run build`; desktop `cd desktop && npm test`.
- Config tests reload `app.config` at class-body time; never mutate ambient env without restoring (see `backend/tests/test_config_integrations.py` pattern).

---

## Task 1: Greeting-once entitlement (backend)

Make the backend the authority on *whether* a greeting is owed, and stop mislabeling resumed conversations as new.

**Files:**
- Modify: `backend/app/db/models.py` (`Conversation.last_greeted_at`)
- Create: `backend/migrations/0003_add_last_greeted_at.sql`
- Modify: `backend/app/db/repositories.py` (`get_or_create_conversation` → also return whether it created the row)
- Modify: `backend/app/api/routes.py` (new `GET /session`, greeting claim)
- Modify: `backend/app/orchestrator/core.py` (greeting gating)
- Test: `backend/tests/test_session.py` (new)

**Interfaces:**
- `get_or_create_conversation(...) -> Conversation` + new `greeting_owed(db, conversation) -> bool` helper: True only when the conversation row was created on this request, or `conversation.id` existed but `last_greeted_at IS NULL` and `now - created_at < GREETING_WINDOW_S` (default 90s, config `umi.greeting_window_s`).
- `claim_greeting(db, conversation) -> None` sets `last_greeted_at = utcnow()`.
- `GET /session` → `{"conversation_id": str, "resumed": bool, "greeting": {"text": str|null, "period": str}, "idle": {"enabled": bool, "threshold_seconds": int, "cooldown_seconds": int} | null, "server_time": str}`. `resumed=True` means the resolved conversation already had messages before this call.
- Orchestrator: `is_new_conversation = conversation was just created` (from the repository flag), *not* `conversation_id is None`. `stream_message`/`handle_message` gain `greeting: str | None = None` — when supplied it overrides the auto-computed greeting.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_session.py`: repository `greeting_owed` True on brand-new conv then False after `claim_greeting`; False for an old untouched conversation after `GREETING_WINDOW_S`; `/session` returns `conversation_id` + `resumed` + `idle` policy; a resumed conversation yields `greeting.text` only when owed).
- [ ] **Step 2: Run tests — verify they fail.**
- [ ] **Step 3: Implement** (model + migration + repository flag + `greeting_owed`/`claim_greeting` + `/session` route + orchestrator gating).
- [ ] **Step 4: Run tests — PASS.** Also run `tests/test_api.py`, `tests/test_voice_chat.py`, `tests/test_platform_orchestrator.py`, `tests/test_integrations_*` to confirm greeting-once didn't break platform `include_greeting=False`.
- [ ] **Step 5: Commit** — `feat(session): greeting-once entitlement and GET /session`.

---

## Task 2: Frontend session capture + conversation continuity

Persist and restore the active conversation so restarts continue the same thread and the first turn never goes out as `conversation_id: null`.

**Files:**
- Modify: `frontend/app/hooks/useChat.ts` (hydration already fetches `/conversations/active/messages`; also fetch `GET /session`, capture id into `conversationIdRef` + `sessionStorage`, expose the resume flag; `reset` clears storage)
- Modify: `frontend/app/lib/chat.ts` (any request-body helper consumers)
- Test: `frontend/tests/useChat-session.test.mjs` (new; pure helpers only — keep fetch/React out, mirror existing mjs style)

**Interfaces:**
- `useChat` adds `session: { conversationId: string | null; resumed: boolean }`; on mount: `GET /session` → set ref + storage; fall back to `/conversations/active/messages` for message list as today.
- `reset()` clears `sessionStorage["umi_conversation_id"]` and POSTs `conversation_id: null` on next send (existing behavior) — so a fresh chat legitimately resolves the latest desktop conversation and, if truly empty, greets.

- [ ] **Step 1: Write failing tests** (storage round-trip, fallback when `/session` fails, resumed flag propagation).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run — PASS** (`npm test && npm run lint && npm run build`).
- [ ] **Step 5: Commit** — `feat(frontend): resume active conversation across reloads`.

---

## Task 3: Desktop readiness handshake + spoken greeting

Fix the drop race and actually *say* the greeting.

**Files:**
- Modify: `desktop/preload.js` (add `getStartupState()` via `ipcRenderer.invoke`; add `notifyStartupReady()` via `ipcRenderer.send`)
- Modify: `desktop/index.js` (hold last startup-state payload in main; `ipcMain.handle("umi:get-startup-state")`; on `umi:startup-ready` from the webview, replay buffered payload; also after `webContents 'did-finish-load'` attach the ready listener)
- Modify: `desktop/startup/orchestrator.js` (emit is buffered — pass through a `waitForWebviewReady` seam with a default that waits for the frontend ACK up to N seconds before pushing GREETING/READY)
- Modify: `frontend/app/UmiInterface.tsx` (GREETING branch: `void tts.speak(greetingText).then(endGreeting)` with a 1.5s silence guard before first audio; auto-end once spoken; keep explicit Dismiss to mute)
- Test: `desktop/tests/startup.test.js` + `desktop/tests/orchestrator.test.js` (extend: buffered-emit waits for ready before GREETING; replay works), `frontend/tests/speech.test.mjs` (greeting ≤ MAX_TTS_CHARS)

**Interfaces:**
- `window.umi.getStartupState(): Promise<{state, greeting, context, softErrors}|null>` (pull), plus existing push `onStartupState`.
- Orchestrator: `_push` writes to a shared last-state buffer (the `emit` wrapper in `index.js`), and the webview ACK (`notifyStartupReady`) triggers a final flush of the buffered payload — so a payload sent before hydration is *re-delivered*, not lost.
- `UmiExperience` greeting effect: prefer `await getStartupState()` (pull) and also subscribe to push (race-immune either way).

- [ ] **Step 1: Desktop failing tests** (emit buffers until ready; orchestration sequence asserts GREETING delivered after ACK).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** preload + main + orchestrator seams.
- [ ] **Step 4: Run — PASS** (`cd desktop && npm test`).
- [ ] **Step 5: Spoken greeting**: write failing check that greeting text flows through `tts.speak` on GREETING (frontend hook-level, small `frontend/tests/greeting.test.mjs`), implement in `UmiInterface.tsx`.
- [ ] **Step 6: Frontend suite PASS** (`npm test && npm run lint && npm run build`).
- [ ] **Step 7: Commit** — `feat(startup): readiness-handshaked, spoken greeting`.

---

## Task 4: Idle policy module (backend, pure + tests)

Deterministic, configurable rules for when Umi may *start* a conversation.

**Files:**
- Modify: `backend/app/config.py` (`umi_idle_enabled` default true, `umi_idle_threshold_seconds` default 45, `umi_idle_cooldown_seconds` default 120, `umi_idle_max_prompts_per_hour` default 4)
- Create: `backend/app/services/idle.py`
- Test: `backend/tests/test_idle_policy.py`

**Interfaces:**
- `IdlePolicy` dataclass (`enabled`, `threshold_s`, `cooldown_s`, `max_per_hour`).
- `should_start(tp: IdlePolicy, last_activity_at: float, prompts_last_hour: int, now: float) -> bool`.
- `bump_cooldown(last_activity_at: float, now: float) -> float` (returns new last-activity baseline so cooldown spans the exchange).
- Deadline clamp: idle turns only between `umi_idle_start_hour`/`umi_idle_end_hour` (default 8:00–23:00, `local_time`).

- [ ] **Step 1: Failing tests** (below threshold blocks; ≥threshold + space in hourly budget allows; cooldown blocks; out-of-hours blocks; disabled blocks).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** policy + config fields (+ `backend/.env.example` block, config tests appended to `backend/tests/test_config_integrations.py`).
- [ ] **Step 4: Run — PASS** (new + config tests).
- [ ] **Step 5: Commit** — `feat(config): idle conversation policy`.

---

## Task 5: Proactive turns through the orchestrator

Idle *messages* ride the exact same pipeline as user turns.

**Files:**
- Modify: `backend/app/api/routes.py` (`ChatRequest.proactive: bool = False`; pass through)
- Modify: `backend/app/orchestrator/core.py` (`handle_message(..., proactive=False)` / `stream_message(...)`: when proactive, `fast=True`, and replace the user-message slot with an internal opener instruction so the LLM produces a brief, unprompted, context-aware line — never a question-bomb, ≤2 sentences)
- Modify: `backend/app/orchestrator/core.py` latency metrics: log `proactive`, `conversation_id`, `greeted` flags
- Test: `backend/tests/test_voice_chat.py`/`tests/test_session.py` (extend: proactive turn persists to same conversation, uses fast path, injects opener, does not increment greeting)

**Interfaces:**
- `handle_message(db, message, conversation_id, voice, *, proactive=False, ...)`.
- Proactive opener constant `PROACTIVE_OPENER` in core.py (system-level instruction appended to context, not a fake user line in history).

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** (routes + orchestrator).
- [ ] **Step 4: Run — PASS** (new + existing chat/voice/api tests).
- [ ] **Step 5: Commit** — `feat(orchestrator): proactive conversation turns`.

---

## Task 6: Frontend idle monitor + policy wiring

Detect quiet time and start one gentle conversation per policy, in the current conversation.

**Files:**
- Create: `frontend/app/hooks/useIdleConversation.ts`
- Modify: `frontend/app/UmiInterface.tsx` (wire hook; pass `onPrompt` → `chat.send(prompt, token, voice=false, proactive? → new `chat.sendIdle(...)` wrapper that sets `proactive: true`)`
- Modify: `frontend/app/hooks/useChat.ts` (expose `send(text, token, voice, proactive?)`; include `proactive` in `chatRequestBody`)
- Modify: `frontend/app/lib/chat.ts` (`chatRequestBody` gains `proactive` field)
- Test: `frontend/tests/idle-conversation.test.mjs` (pure policy harness shared with backend shape; guard: never fires while THINKING/SPEAKING/LISTENING-startup; cooldown respected; respects voice-session-active so a reply is *spoken*)

**Interfaces:**
- `useIdleConversation({ enabled, thresholdSeconds, cooldownSeconds, onPrompt, busy: () => boolean, lastActivityRef })`.
- Activity heartbeat sources: turn completion (`onDone`/`finishTurn`), any user text send, any STT commit, greeting spoken.
- Proactive reply flows through `onSentence` → `tts.speak` (spoken) → state READY when idle and voice off, LISTENING when voice on.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** hook + wiring + request field.
- [ ] **Step 4: Run — PASS** (`npm test && npm run lint && npm run build`).
- [ ] **Step 5: Commit** — `feat(frontend): idle conversation monitor`.

---

## Task 7: Memory layering + voice continuity

Feed memories to casual turns, capture reusable facts, and stop Umi from hearing her own voice.

**Files:**
- Modify: `backend/app/orchestrator/core.py` (memory inclusion: `include_memories = not voice` — casual *text* turns keep memories; keep `fast` for routing/model choice)
- Modify: `backend/app/orchestrator/core.py` (post-turn auto-capture: after persisting, run a cheap heuristic — if the user turn looks like a durable fact (regex on "remember|my X is|i will|i'm going to|goal|plan"), call `create_memory`; bounded to 1 capture/turn; no LLM call)
- Modify: `frontend/app/UmiInterface.tsx` (actually `pauseListening()` while first sentence is being spoken and `resumeListening()` when the turn's audio finishes, only when the voice session is active)
- Test: `backend/tests/test_voice_chat.py`/`tests/test_session.py` (casual-with-memory retrieval; auto-capture creates a Memory row), `frontend/tests/echo-pause.test.mjs` (pause/resume sequencing)

**Interfaces:**
- `io` markers: keep `fast` exclusive to model choice; memory block = whatever `include_memories=True` provides.
- `_maybe_autocapture(db, conversation, user_message, user_id) -> Memory | None`.

- [ ] **Step 1: Failing tests.**
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run — PASS** (backend + frontend suites).
- [ ] **Step 5: Commit** — `feat(memory,voice): memory for casual turns, auto-capture, echo-pause`.

---

## Task 8: Observability + docs + final live verification

**Files:**
- Modify: `backend/app/orchestrator/core.py` (log `conversation_id`, `greeted`, `proactive`, `fast`, `messages_in_history` on each turn)
- Modify: `backend/app/api/routes.py` (`/chat/stream` done event logs the same + `reply_chars`, `conversation_id`)
- Create: `docs/startup-and-session-lifecycle.md` (exact startup flow, conversation/session lifecycle, idle behavior, config table, remaining limitations)

**Verification (before any completion claim):**
- [ ] Live: restart backend + desktop; confirm textual AND spoken single greeting; confirm no greeting on a second restart of the same conversation within window.
- [ ] Live: multi-turn `/chat` with persisted id — context carried (turn 2 references turn 1) and `conversation_id` stable across frontend reload.
- [ ] Live: leave idle; Umi starts a conversation within threshold, once, within cooldown; spoken when voice on.
- [ ] Live: voice session — Umi speaks, mic stays paused during speech, no echo turn, resume after.
- [ ] Suites green: backend (303 + new), frontend, desktop.
- [ ] Final 13-point report to the user (root causes; why context lost; why greeting failed; why Q&A; architecture changes; files changed; tests created; tests executed; exact startup flow; conversation/session lifecycle; idle behavior; new config values; remaining limitations) with live evidence.

---

## Config table (new settings)

| Env var | Default | Meaning |
|---|---|---|
| `UMI_IDLE_CONVERSATION_ENABLED` | `1` | Master idle switch |
| `UMI_IDLE_THRESHOLD_SECONDS` | `45` | Quiet time before Umi may start a conversation |
| `UMI_IDLE_COOLDOWN_SECONDS` | `120` | Min gap between proactive turns |
| `UMI_IDLE_MAX_PROMPTS_PER_HOUR` | `4` | Hourly proactive budget |
| `UMI_IDLE_START_HOUR` / `UMI_IDLE_END_HOUR` | `8` / `23` | Local-hour window |
| `UMI_GREETING_WINDOW_SECONDS` | `90` | Fresh-launch window in which an ungreated conversation may greet |