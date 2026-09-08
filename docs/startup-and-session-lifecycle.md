# Umi: startup, session lifecycle, idle behavior, and config

This document is the source of truth for how Umi launches, how a conversation
is (re)established, how greeting-once works, how idle/proactive conversations
are governed, and what knobs control it. It accompanies the architectural plan
in `docs/superpowers/plans/2026-09-08-umi-conversational-architecture.md`.

## 1. Exact startup flow

1. **Electron (desktop) boots.** `desktop/index.js` creates the window and
   wires IPC. A `StartupStateRelay` (`desktop/startup/state-relay.js`) tracks
   whether the frontend has ever signalled readiness.
2. **Main process prepares.** It waits for the backend to be reachable, loads
   per-user config, and sets up a spoken greeting task that must *not* run
   until the UI can receive it (no dropped or double greetings).
3. **Renderer loads.** `UmiInterface` mounts, starts TTS/STT, and — the moment
   it is interactive — sends `umi:startup-ready` to main. Main responds by
   replaying any pending startup state to the renderer
   (`umi:startup-state:get` invoke / `umi:startup-ready` send handshake).
4. **Session lookup.** The frontend calls `GET /session` after mount. The
   backend answers with:
   - the greeting entitlement for this launch window,
   - the active conversation id,
   - the current idle policy (or `null` when idle is disabled).
   The frontend restores the stored conversation id from `localStorage`
   (`umi_conversation_id`) so a reload never starts a brand-new thread.
5. **Greeting speaks (once).** If `GET /session` says a greeting is owed and
   the local TTS/AI voice is ready, Umi speaks the greeting *through the same
   TTS path as replies* and commits it; `claim_greeting` stamps
   `last_greeted_at` so a second restart inside the same window stays silent.
6. **Idle monitor arms.** The frontend starts a 5s sampler. When the user is
   quiet past the threshold, inside active hours, past the cooldown, and under
   the hourly budget, it calls `POST /chat` with `proactive: true`.

## 2. Conversation / session lifecycle

- **Conversation = the persisted thread.** Every turn resolves to a row in
  `conversations` (via `get_or_create_conversation`). The desktop conversation
  is matched by `conversation_id` or a per-source key; platform adapters
  (Telegram/Discord) get their own isolated threads via `conversation_key`.
- **The id is sticky across reloads.** `lib/chat.ts`
  (`readStoredConversationId` / `storeConversationId`) persists the id in
  `sessionStorage` under `umi_conversation_id`; `useChat` restores it on mount
  and updates it on every response, so a browser refresh continues the same
  conversation with full server-side context.
- **Greeting-once.** New conversations can greet within
  `UMI_GREETING_WINDOW_SECONDS` of creation; a claimed greeting
  (`conversations.last_greeted_at`) silences future launches until a genuinely
  new conversation appears. Resumed conversations never re-greet.
- **Every turn is attributed.** `core.py` and `/chat/stream` log one
  `turn conversation_id=… greeted=… proactive=… fast=… voice=… source=…
  messages_in_history=… reply_chars=…` line (plus latency metrics) so any
  conversation can be traced from log to persisted rows.

## 3. Memory layering & voice continuity

- **Casual text turns keep memories.** `handle_message`/`stream_message`
  pass `include_memories = not voice`: the most common short *text* turns are
  still given the 4 most relevant memories, while the fast voice loop skips the
  memory block to stay cheap.
- **Automatic capture.** After every non-proactive, non-voice reply, a cheap
  deterministic heuristic (`_maybe_autocapture`) checks the user's message for
  durable-fact signals (`remember`, `my X is`, `I will`/`I'm going to`,
  `goal`/`plan`, `I like/love/prefer`, `call me`, …). If it is long enough,
  is not a question, and is not an exact duplicate, it is stored as a `Memory`
  row (max one per turn, never an LLM call).
- **Echo-pause.** While Umi speaks, the mic is *actually* paused
  (`voice.pauseListening()`, not just a flag) via
  `lib/voice/echoPause.ts`; `resumeListening()` runs when the turn's audio
  finishes and voice is still active. Her own TTS can therefore never be
  captured as a fake user turn. The text-based echo guard remains as backstop.

## 4. Idle / proactive conversation behavior

- **Server-enforced.** `POST /chat`/`/chat/stream` with `proactive: true`
  first runs `evaluate_idle` / `evaluate_proactive_entitlement`. Refusals are
  `429` with a friendly reason (`not-idle-yet`, `outside-active-hours`,
  `within-cooldown`, `hourly-cap-reached`, `disabled`).
- **Active hours** use a local-hour window that supports overnight ranges
  (e.g. `22`–`6`).
- **Proactive turns** generate the opener from `PROACTIVE_OPENER`, persist only
  the assistant message (never a fabricated user message), record
  `last_proactive_at` + `proactive_count_last_hour` on the conversation, and
  roll the hourly counter back over a rolling hour.
- **Frontend guardrails.** The 5s sampler skips when a turn is in flight
  (`busy`), the tab is hidden, or Umi is `SPEAKING`/`THINKING`/`GREETING`.
  `proactive_count` is tracked client-side and hits the server cap before the
  server does, so a denied opener is rare.

## 5. Config table (new settings)

| Env var | Default | Meaning |
|---|---|---|
| `UMI_IDLE_CONVERSATION_ENABLED` | `1` | Master idle switch (0 fully disables) |
| `UMI_IDLE_THRESHOLD_SECONDS` | `45` | Quiet time before Umi may start a conversation |
| `UMI_IDLE_COOLDOWN_SECONDS` | `120` | Min gap between proactive turns |
| `UMI_IDLE_MAX_PROMPTS_PER_HOUR` | `4` | Hourly proactive budget (rolling hour) |
| `UMI_IDLE_START_HOUR` / `UMI_IDLE_END_HOUR` | `8` / `23` | Local-hour window (supports overnight) |
| `UMI_GREETING_WINDOW_SECONDS` | `90` | Fresh-launch window in which an ungreated conversation may greet |

## 6. Remaining limitations

- **Voice barge-in during speech is traded for echo silence.** Because the mic
  is muted while Umi talks (Task 7), a spoken interruption during her sentence
  is not captured; the boss can still interject with the double-clap launcher
  or text. The prior text-based echo guard stays as a fallback for the resume
  window.
- **Memory capture is heuristic, not semantic.** Facts that don't fit the
  pattern (or are phrased as questions) are not auto-captured; manual
  `POST /memories` remains the high-fidelity path.
- **Rolling idle window is evaluated at turn time.** Idleness is computed from
  the most recent user message (or conversation creation), not a continuous
  timer.