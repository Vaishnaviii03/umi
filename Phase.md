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
* [ ] 🤝 Test double-clap false-positive rate (unit tests in launcher/tests + `main.py --test` / `--calibrate` harness ready; real-mic manual test pending)
* [x] 🤝 Test graceful degradation (music fails → UMI still starts — unit + live desktop shell verified)

### Definition of Done

* [ ] Double clap launches UMI desktop app (not localhost in browser) — implementation wired; real-mic verify pending
* [x] Startup completes in ~10-15s using real readiness states, not fixed delay (live shell test reached READY)
* [x] Music/greeting failures don't block UMI from becoming ready
* [x] Double clap only activates UMI — does not authorize any sensitive action (launcher only spawns the desktop app)

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

* [ ] 🤖 Create task schema
* [ ] 🤖 Create task APIs
* [ ] 🤖 Create task tool
* [ ] 🤖 Create task UI
* [ ] 🤖 Create reminder model
* [ ] 🤖 Implement task creation
* [ ] 🤖 Implement task retrieval
* [ ] 🤖 Implement task completion
* [ ] 🤖 Implement task updates
* [ ] 🤝 Test natural task commands

Example:

> "UMI, remind me to study Physics tomorrow."

UMI should understand the request and create the appropriate task/reminder.

### Definition of Done

* [ ] Tasks work
* [ ] Natural language task creation works
* [ ] Task UI works
* [ ] Database persistence works
* [ ] Tests pass

---

# PHASE 5 — GMAIL

## Objective

Allow UMI to safely interact with Gmail.

### HUMAN SETUP

* [ ] 👤 Create Google Cloud project
* [ ] 👤 Enable Gmail API
* [ ] 👤 Configure OAuth consent
* [ ] 👤 Create OAuth credentials
* [ ] 👤 Configure authorized redirect URI
* [ ] 👤 Connect Google account
* [ ] 👤 Approve requested permissions

### AI IMPLEMENTATION

* [ ] 🤖 Implement OAuth flow
* [ ] 🤖 Implement token storage
* [ ] 🤖 Create Gmail integration
* [ ] 🤖 Create Gmail tool
* [ ] 🤖 Implement email retrieval
* [ ] 🤖 Implement email search
* [ ] 🤖 Implement email summarization
* [ ] 🤖 Implement importance detection
* [ ] 🤖 Implement draft generation
* [ ] 🤖 Implement send confirmation
* [ ] 🤖 Implement audit logging

### Definition of Done

* [ ] UMI can retrieve emails
* [ ] UMI can summarize emails
* [ ] UMI can search emails
* [ ] UMI can draft responses
* [ ] Sending requires appropriate confirmation
* [ ] Credentials are secure

---

# PHASE 6 — GOOGLE CALENDAR

## Objective

Connect UMI to the user's calendar.

### HUMAN SETUP

* [ ] 👤 Enable Calendar API
* [ ] 👤 Configure OAuth
* [ ] 👤 Grant required permissions

### AI IMPLEMENTATION

* [ ] 🤖 Create Calendar integration
* [ ] 🤖 Create Calendar tool
* [ ] 🤖 Retrieve events
* [ ] 🤖 Create events
* [ ] 🤖 Modify events
* [ ] 🤖 Implement confirmation for sensitive actions
* [ ] 🤖 Add calendar summaries

### Definition of Done

User can ask:

> "What's on my calendar tomorrow?"

and UMI can respond accurately.

---

# PHASE 7 — VOICE

## Objective

Transform UMI from text assistant into voice assistant.

### Checklist

* [ ] 👤 Select speech-to-text provider
* [ ] 👤 Select text-to-speech provider
* [ ] 👤 Configure credentials
* [ ] 🤖 Implement microphone input
* [ ] 🤖 Implement speech-to-text
* [ ] 🤖 Connect voice to UMI backend
* [ ] 🤖 Implement text-to-speech
* [ ] 🤖 Implement audio output
* [ ] 🤖 Add voice activity detection
* [ ] 🤖 Handle interruptions
* [ ] 🤝 Test natural conversation

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

works reliably.

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

* [ ] 👤 Connect camera
* [ ] 👤 Configure permissions
* [ ] 🤖 Select vision technology
* [ ] 🤖 Create vision module
* [ ] 🤖 Capture frames
* [ ] 🤖 Detect objects
* [ ] 🤖 Generate visual context
* [ ] 🤖 Connect vision context to orchestrator
* [ ] 🤝 Test visual questions

Example:

> "UMI, what am I looking at?"

---

# PHASE 10 — GESTURE CONTROL

## Objective

Add gesture as an interaction modality.

### Checklist

* [ ] 🤖 Implement hand detection
* [ ] 🤖 Implement gesture classification
* [ ] 🤖 Define gesture vocabulary
* [ ] 🤖 Map gestures to UI actions
* [ ] 🤖 Add gesture state
* [ ] 🤖 Add safety restrictions
* [ ] 🤝 Test false positives
* [ ] 🤝 Test accessibility/fallback controls

Example:

```text
Point → Select
Swipe → Change screen
Pinch → Click
```

---

# PHASE 11 — PROACTIVE UMI

## Objective

Allow UMI to initiate useful interactions.

### Checklist

* [ ] 🤖 Create scheduler
* [ ] 🤖 Create event system
* [ ] 🤖 Create notification system
* [ ] 🤖 Create proactive rules
* [ ] 🤖 Add user preferences
* [ ] 🤖 Add notification controls
* [ ] 🤖 Add quiet periods
* [ ] 🤝 Test unwanted notifications

Examples:

> "You have an important email."

> "You have a task due today."

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

* [ ] Tool interface
* [ ] Tool registry
* [ ] Permission system
* [ ] Tool execution
* [ ] Tool logging

## Productivity

* [ ] Tasks
* [ ] Reminders
* [ ] Calendar

## Integrations

* [ ] Gmail
* [ ] Calendar
* [ ] Web
* [ ] Files

## Multimodal

* [ ] Voice
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
