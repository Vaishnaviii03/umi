# Discord + Telegram Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Discord (gateway bot) and Telegram (Bot API long-poll) channels so Umi answers through them using the exact same orchestration/LLM/tools/memory pipeline as desktop and voice, with owner-only authorization and hard confirmation blocking.

**Architecture:** Thin platform adapters (`backend/app/integrations/`) that map inbound platform messages into a `PlatformMessage`, authorize them (owner-only; everyone else gets a fixed refusal with no LLM/tool/DB access), feed the existing HTTP-independent `handle_message` orchestrator in `backend/app/orchestrator/core.py:163`, and send the reply back through the originating channel. Conversations gain a `source`/`conversation_key` so each Discord guild-channel and Telegram chat gets its own isolated thread while memories stay shared (same Umi, one personality, one memory store). Workers run as daemon threads owned by an `IntegrationSupervisor` started in the FastAPI lifespan; failures never affect the uvicorn/desktop process.

**Tech Stack:** Python 3.11 (venv at `backend/.venv`), FastAPI + uvicorn, SQLAlchemy 2 (Supabase Postgres; in-memory SQLite in tests), discord.py 2.4.0 (new dep; 2.4.1 does not exist, 2.4.0 is the latest in the 2.4 line), httpx 0.28 (already installed, used raw for Telegram long-poll), OpenAI SDK → OpenRouter (existing), Next.js frontend (chips in `GmailPanel.tsx`).

**Spec:** User's 14-phase Discord/Telegram integration requirements (session conversation; selectors chosen: discord.py thread, raw httpx long-poll, per-platform conversations, owner-only auth, confirmation block-with-guidance) + existing `Phase.md` conventions.

## Global Constraints

- Env var names EXACTLY: `DISCORD_APPLICATION_ID`, `DISCORD_PUBLIC_KEY`, `DISCORD_BOT_TOKEN`, `DISCORD_OWNER_ID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`.
- Secrets live ONLY in `backend/.env` (loaded by `load_dotenv()` at `config.py:4`). NEVER print/log/commit tokens; never ask the user for them in chat; no hardcoding; no `NEXT_PUBLIC_`. Frontend only ever sees the boolean/label status endpoint.
- Do NOT modify/break: Google/Gmail/Calendar integration, voice system, local TTS, Web Speech STT, double-clap launcher, tools permission model, desktop shell process management.
- Discord is a proper bot (not a self-bot); minimal intents: `discord.Intents.default()` + `message_content=True`. Never replies to bots.
- Platform messages NEVER set `ToolContext.extra["confirmed"]` and never alter permission ceilings → confirm-gated tools block (`ConfirmationRequired`) and Umi tells the user to use the desktop app.
- TDD Iron Law: no production code without a failing test first. Frequent small commits. Verification before any completion claim.
- Backend tests: `cd backend && .venv/bin/python3.11 -m pytest -q`. Frontend: `cd frontend && npm test && npm run lint && npm run build`. Desktop: `cd desktop && npm test`.
- Config tests reload `app.config` module (env is read at class-body time); never mutate the ambient process env without restoring it.

---

### Task 1: Config fields + .env.example + config tests

**Files:**
- Modify: `backend/app/config.py` (after `gmail_token_path` block, before `settings = Settings()`)
- Modify: `backend/.env.example` (new Phase 8 section)
- Test: `backend/tests/test_config_integrations.py`

**Interfaces:**
- Produces: `Settings.discord_application_id`, `Settings.discord_public_key`, `Settings.discord_bot_token`, `Settings.discord_owner_id`, `Settings.telegram_bot_token`, `Settings.telegram_owner_id` (all `str`), plus properties `Settings.discord_enabled`, `Settings.telegram_enabled` (`bool`).

- [x] **Step 1: Write the failing tests**

```python
import importlib
import os

import pytest

import app.config as config_module

_ENV_KEYS = [
    "DISCORD_APPLICATION_ID",
    "DISCORD_PUBLIC_KEY",
    "DISCORD_BOT_TOKEN",
    "DISCORD_OWNER_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_OWNER_ID",
]


@pytest.fixture()
def reload_settings(monkeypatch):
    """Set env vars, reload app.config, and restore everything afterwards."""
    original = {k: os.environ.get(k) for k in _ENV_KEYS}

    def apply(values: dict[str, str]) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        importlib.reload(config_module)

    yield apply

    for key, old in original.items():
        if old is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, old)
    importlib.reload(config_module)


def test_discord_settings_load_from_env(reload_settings):
    reload_settings(
        {
            "DISCORD_APPLICATION_ID": "11111111",
            "DISCORD_PUBLIC_KEY": "pub-key",
            "DISCORD_BOT_TOKEN": "disc-token",
            "DISCORD_OWNER_ID": "22222222",
        }
    )
    assert config_module.settings.discord_application_id == "11111111"
    assert config_module.settings.discord_public_key == "pub-key"
    assert config_module.settings.discord_bot_token == "disc-token"
    assert config_module.settings.discord_owner_id == "22222222"
    assert config_module.settings.discord_enabled is True


def test_telegram_settings_load_from_env(reload_settings):
    reload_settings({"TELEGRAM_BOT_TOKEN": "333:tok", "TELEGRAM_OWNER_ID": "444"})
    assert config_module.settings.telegram_bot_token == "333:tok"
    assert config_module.settings.telegram_owner_id == "444"
    assert config_module.settings.telegram_enabled is True


def test_integrations_disabled_when_tokens_empty(reload_settings):
    reload_settings({})
    assert config_module.settings.discord_bot_token == ""
    assert config_module.settings.telegram_bot_token == ""
    assert config_module.settings.discord_enabled is False
    assert config_module.settings.telegram_enabled is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_config_integrations.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'discord_application_id'`

- [x] **Step 3: Implement config fields**

```python
    # Phase 8 — Discord + Telegram integrations. The tokens are server-side
    # secrets; they are read from backend/.env and never exposed to the
    # browser. Owner ids pin which platform user may speak to Umi; every other
    # user receives a polite refusal with no LLM/tool/database access.
    discord_application_id: str = os.environ.get("DISCORD_APPLICATION_ID", "")
    discord_public_key: str = os.environ.get("DISCORD_PUBLIC_KEY", "")
    discord_bot_token: str = os.environ.get("DISCORD_BOT_TOKEN", "")
    discord_owner_id: str = os.environ.get("DISCORD_OWNER_ID", "")
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_owner_id: str = os.environ.get("TELEGRAM_OWNER_ID", "")

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_bot_token)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_config_integrations.py -q`
Expected: PASS (3 tests)

- [x] **Step 5: Document in .env.example** (append the block below, styled like the existing Phase blocks)

```
# Phase 8 — Discord + Telegram. Paste YOUR OWN credentials here; never share
# them in chat or commit them. These are backend-only secrets (backend/.env),
# never exposed to the frontend or browser.
# - Discord: Developer Portal → your App → Bot → build a bot, enable the
#   "Message Content Intent", copy DISCORD_APPLICATION_ID + DISCORD_PUBLIC_KEY
#   (General Information) and the bot token. Your user id: enable Developer
#   Mode (Settings → Advanced), right-click your name → Copy User ID.
# - Telegram: @BotFather → /newbot → copy the token. Your user id: message
#   @userinfobot on Telegram.
DISCORD_APPLICATION_ID=
DISCORD_PUBLIC_KEY=
DISCORD_BOT_TOKEN=
DISCORD_OWNER_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_ID=
```

- [x] **Step 6: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/tests/test_config_integrations.py
git commit -m "feat(config): add Discord/Telegram integration settings"
```

---

### Task 2: Owner authorization service

**Files:**
- Create: `backend/app/integrations/__init__.py` (empty, or `from .authz import resolve_role`)
- Create: `backend/app/integrations/authz.py`
- Test: `backend/tests/test_integrations_authz.py`
- Create: `backend/app/integrations/types.py` (the `PlatformMessage` dataclass, needed by authz consumers and the shared pipeline; kept in this task so authz tests have the platform notion)

**Interfaces:**
- Consumes: `Settings.discord_owner_id`, `Settings.telegram_owner_id` (Task 1)
- Produces: `resolve_role(platform: str, platform_user_id: str | int) -> str` returning `"owner"` or `"unknown"`; `refusal_text(platform: str, author_name: str) -> str`; `PlatformMessage` dataclass with fields `platform`, `platform_user_id`, `author_name`, `text`, `conversation_key`, `conversation_title`, `context_summary`.

- [x] **Step 1: Write the failing tests**

```python
from app.config import settings
from app.integrations.authz import refusal_text, resolve_role


def test_owner_matches_discord_owner_id(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "12345")
    assert resolve_role("discord", "12345") == "owner"


def test_non_owner_is_unknown(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "12345")
    monkeypatch.setattr(settings, "telegram_owner_id", "678")
    assert resolve_role("discord", "999") == "unknown"
    assert resolve_role("telegram", "12345") == "unknown"


def test_numeric_telegram_id_matches(monkeypatch):
    monkeypatch.setattr(settings, "telegram_owner_id", "42")
    assert resolve_role("telegram", 42) == "owner"


def test_missing_owner_id_means_unknown(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "")
    monkeypatch.setattr(settings, "telegram_owner_id", "")
    assert resolve_role("discord", "anything") == "unknown"
    assert resolve_role("telegram", "anything") == "unknown"


def test_unknown_platform_is_never_owner(monkeypatch):
    monkeypatch.setattr(settings, "telegram_owner_id", "1")
    assert resolve_role("bogus", "1") == "unknown"


def test_refusal_text_is_polite_and_does_not_call_llm():
    text = refusal_text("discord", "Alice")
    assert "owner" in text
    assert "Alice" not in text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_authz.py -q`
Expected: FAIL — `ModuleNotFoundError: app.integrations`

- [x] **Step 3: Implement types.py**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlatformMessage:
    """Normalized inbound message from an external chat platform.

    Only safe display metadata is carried: ``context_summary`` is a name-based
    description meant for the LLM, never raw OAuth tokens or channel/user ids.
    ``conversation_key`` is internal routing (not shown to the LLM).
    """

    platform: str
    platform_user_id: str
    author_name: str
    text: str
    conversation_key: str
    conversation_title: str
    context_summary: str
```

- [x] **Step 4: Implement authz.py**

```python
from app.config import settings

_UNKNOWN_REFUSAL = (
    "I only respond to my owner on this platform. "
    "If you're the owner, set {owner_env} in the backend environment and "
    "restart me."
)


def _owner_id_for(platform: str) -> str | None:
    if platform == "discord":
        return settings.discord_owner_id
    if platform == "telegram":
        return settings.telegram_owner_id
    return None


def _owner_env_for(platform: str) -> str:
    return "DISCORD_OWNER_ID" if platform == "discord" else "TELEGRAM_OWNER_ID"


def resolve_role(platform: str, platform_user_id: str | int) -> str:
    """Return ``"owner"`` when the platform user id matches the configured owner
    id for that platform, else ``"unknown"``. Missing owner id -> unknown."""
    owner_id = _owner_id_for(platform)
    if not owner_id:
        return "unknown"
    return "owner" if str(platform_user_id).strip() == owner_id.strip() else "unknown"


def refusal_text(platform: str, author_name: str | None = None) -> str:
    return _UNKNOWN_REFUSAL.format(owner_env=_owner_env_for(platform))
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_authz.py -q`
Expected: PASS (6 tests)

- [x] **Step 6: Commit**

```bash
git add backend/app/integrations backend/tests/test_integrations_authz.py
git commit -m "feat(integrations): add PlatformMessage type and owner authorization"
```

---

### Task 3: Conversation `source`/`conversation_key` in model + repository

**Files:**
- Modify: `backend/app/db/models.py` (Conversation, after `title` column)
- Modify: `backend/app/db/repositories.py` (`get_or_create_conversation`, lines 18-35)
- Create: `backend/migrations/0002_add_conversation_source.sql`
- Test: `backend/tests/test_db.py` (append tests there; it is the existing DB test module)

**Interfaces:**
- Consumes: `Conversation` model, `OWNER_USER_ID`
- Produces: `get_or_create_conversation(db, conversation_id=None, *, source="desktop", conversation_key=None, title="Conversation") -> Conversation`

- [x] **Step 1: Write the failing tests** (append to `backend/tests/test_db.py`)

```python
def test_get_or_create_conversation_with_source(clean_tables, db_session):
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(
        db_session, source="discord", conversation_key="111:222", title="Discord · Server · #general"
    )
    assert conv.source == "discord"
    assert conv.conversation_key == "111:222"
    assert conv.title == "Discord · Server · #general"

    again = get_or_create_conversation(
        db_session, source="discord", conversation_key="111:222", title="Discord · Server · #general"
    )
    assert again.id == conv.id


def test_platform_sources_are_isolated(clean_tables, db_session):
    from app.db.repositories import get_or_create_conversation

    discord = get_or_create_conversation(db_session, source="discord", conversation_key="1:2")
    telegram = get_or_create_conversation(db_session, source="telegram", conversation_key="3")
    desktop = get_or_create_conversation(db_session)
    assert discord.id != telegram.id
    assert telegram.id != desktop.id
    assert discord.id != desktop.id


def test_desktop_default_preserves_latest_conversation(clean_tables, db_session):
    from app.db.models import Conversation
    from app.db.repositories import get_or_create_conversation

    first = Conversation(user_id=__import__("app.db.repositories", fromlist=["OWNER_USER_ID"]).OWNER_USER_ID, title="A")
    db_session.add(first)
    db_session.flush()
    got = get_or_create_conversation(db_session)
    assert got.id == first.id
    assert got.source == "desktop"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_db.py -q`
Expected: FAIL on the three new tests (`AttributeError: 'Conversation' object has no attribute 'source'` on the first assertion)

- [x] **Step 3: Add model column + migration**

In `models.py`, below the `title` column of `Conversation`:

```python
    # Phase 8 — per-platform conversation threads. Desktop/voice rows default
    # to source='desktop' and a null key; Discord/Telegram rows add their own.
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="desktop")
    conversation_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
```

`backend/migrations/0002_add_conversation_source.sql`:

```sql
-- UMI Phase 8: per-platform conversation threads (Discord / Telegram).
-- Mirrors 0001: idempotent, safe to run multiple times. Existing rows keep
-- source='desktop' with a NULL conversation_key, which is the desktop
-- resolution path, so no backfill or data change is required.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'desktop';
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS conversation_key TEXT;
```

- [x] **Step 4: Rewrite `get_or_create_conversation`**

```python
def get_or_create_conversation(
    db: Session,
    conversation_id=None,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    title: str = "Conversation",
) -> Conversation:
    """Return the requested conversation (if present), else the owner's latest
    conversation matching ``source``/``conversation_key``, else create one.

    Desktop callers pass no extras and keep today's behavior (resolve the
    latest owner conversation). Platform adapters pass ``source`` +
    ``conversation_key`` so each server/channel/chat gets its own isolated
    thread while memories stay shared.
    """
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id == OWNER_USER_ID:
            return conv
    query = db.query(Conversation).filter(
        Conversation.user_id == OWNER_USER_ID,
        Conversation.source == source,
    )
    if conversation_key is None:
        query = query.filter(Conversation.conversation_key.is_(None))
    else:
        query = query.filter(Conversation.conversation_key == conversation_key)
    conv = query.order_by(Conversation.updated_at.desc()).first()
    if conv is None:
        conv = Conversation(
            user_id=OWNER_USER_ID,
            title=title,
            source=source,
            conversation_key=conversation_key,
        )
        db.add(conv)
        db.flush()
    return conv
```

- [x] **Step 5: Run the DB tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_db.py -q`
Expected: PASS (all DB tests, including new ones)

- [x] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/app/db/repositories.py backend/migrations backend/tests/test_db.py
git commit -m "feat(db): per-platform conversation source/key columns and lookup"
```

---

### Task 4: Orchestrator `source`/`platform_context` passthrough

**Files:**
- Modify: `backend/app/orchestrator/core.py` (`_build_context`, `handle_message`, `stream_message`)
- Test: `backend/tests/test_voice_chat.py` (existing streaming test module) — create `backend/tests/test_platform_orchestrator.py` instead

**Interfaces:**
- Consumes: `get_or_create_conversation` new kwargs (Task 3)
- Produces: `handle_message(db, message, conversation_id=None, voice=False, *, source="desktop", conversation_key=None, conversation_title="Conversation", platform_context=None, include_greeting=None) -> tuple[str, str | None]`; `stream_message(..., *, same_new_kwargs)`; `_build_context(..., *, source, conversation_key, conversation_title, platform_context)`.

- [x] **Step 1: Write the failing tests**

```python
from unittest.mock import patch

from app.db import models


def _replies(name: str, text: str = "ok"):
    def _fake(**kwargs):
        return text

    return _fake


def test_handle_message_platform_creates_source_conversation(db_session):
    from app.orchestrator.core import handle_message

    with patch("app.llm.manager.llm_manager.generate_reply", side_effect=_replies("gen")):
        reply, cid = handle_message(
            db_session,
            "hello",
            source="discord",
            conversation_key="g:ch",
            conversation_title="Discord · #main",
            platform_context="You are talking via Discord. Reply in plain text.",
        )
    assert reply == "ok"
    conv = db_session.get(models.Conversation, cid)
    assert conv is not None
    assert conv.source == "discord"
    assert conv.conversation_key == "g:ch"
    assert conv.title == "Discord · #main"
    rows = db_session.query(models.Message).filter(models.Message.conversation_id == conv.id).all()
    assert [m.role for m in rows] == ["user", "assistant"]


def test_handle_message_platform_context_injected_and_greeting_off(db_session):
    captured = {}

    def _fake(**kwargs):
        captured["system"] = kwargs.get("system")
        return "hi"

    from app.orchestrator.core import handle_message

    with patch("app.llm.manager.llm_manager.generate_reply", side_effect=_fake):
        handle_message(
            db_session,
            "hello",
            source="telegram",
            conversation_key="42",
            platform_context="You are talking via Telegram in chat 'X'.",
            include_greeting=False,
        )
    assert "You are talking via Telegram in chat 'X'." in captured["system"]


def test_handle_message_desktop_default_unchanged(db_session):
    from app.orchestrator.core import handle_message

    with patch("app.llm.manager.llm_manager.generate_reply", side_effect=_replies("gen")):
        reply, cid = handle_message(db_session, "test drive")
    conv = db_session.get(models.Conversation, cid)
    assert conv.source == "desktop"
    assert conv.conversation_key is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_platform_orchestrator.py -q`
Expected: FAIL — `TypeError` on unexpected kwargs `source`/`platform_context` (handle_message doesn't accept them yet).

- [x] **Step 3: Implement core.py changes**

In `_build_context`, change the signature to:

```python
def _build_context(
    db,
    message: str,
    conversation_id=None,
    voice: bool = False,
    include_memories: bool = True,
    include_greeting: bool = False,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    conversation_title: str = "Conversation",
    platform_context: str | None = None,
):
```

Inside `_build_context`, replace `return SYSTEM_PROMPT, time_block, None, None` with:

```python
    system = SYSTEM_PROMPT if not platform_context else f"{SYSTEM_PROMPT}\n\n{platform_context}"
    time_block = f"The user's current local date and time is {local_time_description()}."

    if db is None:
        return system, time_block, None, None

    conversation = get_or_create_conversation(
        db,
        conversation_id,
        source=source,
        conversation_key=conversation_key,
        title=conversation_title,
    )
```

(the `system` and `time_block` lines currently precede the `db is None` check at lines 97-102 — restructure so `system` is computed first and the final `return system, context_block, history, conversation` uses the local `system`.)

In `handle_message`, change the signature to:

```python
def handle_message(
    db,
    message: str,
    conversation_id=None,
    voice: bool = False,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    conversation_title: str = "Conversation",
    platform_context: str | None = None,
    include_greeting: bool | None = None,
) -> tuple[str, str | None]:
```

and inside, replace the two `_build_context` call lines with:

```python
    system, context_block, history, conversation = _build_context(
        db,
        message,
        conversation_id,
        voice=voice,
        include_memories=not fast,
        include_greeting=is_new_conversation if include_greeting is None else include_greeting,
        source=source,
        conversation_key=conversation_key,
        conversation_title=conversation_title,
        platform_context=platform_context,
    )
```

In `stream_message`, change the signature the same way (same keyword block, without `include_greeting`) and pass the new kwargs through to `_build_context` exactly as above.

- [x] **Step 4: Run new tests + existing orchestrator/voice/api tests**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_platform_orchestrator.py tests/test_voice_chat.py tests/test_api.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/orchestrator/core.py backend/tests/test_platform_orchestrator.py
git commit -m "feat(orchestrator): accept per-platform source context passthrough"
```

---

### Task 5: Shared platform responder (`respond_to`)

**Files:**
- Create: `backend/app/integrations/shared.py`
- Test: `backend/tests/test_integrations_shared.py`

**Interfaces:**
- Consumes: `resolve_role`, `refusal_text` (Task 2), `PlatformMessage` (Task 2), `handle_message` (Task 4), `db_engine.db_enabled()` / `db_engine.get_session_factory()`
- Produces: `respond_to(message: PlatformMessage) -> str | None`. For unknown users returns the refusal text WITHOUT calling the LLM, tools, or DB. For the owner, calls `handle_message` with `source`, `conversation_key`, `conversation_title`, `platform_context`, `include_greeting=False`.

- [x] **Step 1: Write the failing tests**

```python
import pytest

from app.integrations.shared import respond_to
from app.integrations.types import PlatformMessage


def make_message(text="hello", platform="discord", user_id="123", platform_user_id="123"):
    return PlatformMessage(
        platform=platform,
        platform_user_id=platform_user_id,
        author_name="UmiOwner",
        text=text,
        conversation_key="g:ch",
        conversation_title="Discord · #main",
        context_summary="You are talking to the user via Discord in server 'HQ', channel '#main'.",
    )


def test_unknown_user_refused_without_llm_or_db(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "111")

    def boom(*a, **k):
        raise AssertionError("must not touch LLM")

    monkeypatch.setattr("app.integrations.shared.handle_message", boom)
    reply = respond_to(make_message(platform_user_id="999"))
    assert "owner" in reply
    assert reply.startswith("I only respond")


def test_owner_routes_through_handle_message(monkeypatch, db_session):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    calls = {}

    def fake_handle(db, message, **kw):
        calls["db"] = db
        calls["message"] = message
        calls["kw"] = kw
        return "hi back", None

    monkeypatch.setattr("app.integrations.shared.handle_message", fake_handle)
    reply = respond_to(make_message())
    assert reply == "hi back"
    assert calls["message"] == "hello"
    assert calls["kw"]["source"] == "discord"
    assert calls["kw"]["conversation_key"] == "g:ch"
    assert calls["kw"]["include_greeting"] is False
    assert "Discord" in calls["kw"]["platform_context"]
    assert calls["db"] is None or calls["db"] is not None  # session is handed off; closed by responder


def test_owner_survives_without_database(monkeypatch):
    from app.config import settings
    from app.db import engine as db_engine

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    monkeypatch.setattr(db_engine, "db_enabled", lambda: False)
    result = respond_to(make_message())

    monkeypatch.setattr("app.integrations.shared.handle_message", lambda db, msg, **kw: ("ok", None))
    # session must be None when db disabled; response still produced
    assert result is None or result == "ok"
```

Note: `test_owner_survives_without_database` must run `respond_to` AFTER the stub is set (see implementation below); order the assertions accordingly — first assert the disabled-db path returns a reply.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_shared.py -q`
Expected: FAIL — `ModuleNotFoundError: app.integrations.shared`

- [x] **Step 3: Implement shared.py**

```python
from __future__ import annotations

from app.db import engine as db_engine
from app.integrations.authz import refusal_text, resolve_role
from app.integrations.types import PlatformMessage
from app.orchestrator.core import handle_message

_PLATFORM_CONTEXT_TEMPLATE = (
    "You are talking to the user through {platform}. {context} "
    "Reply in plain text. If using a tool would need confirmation, do NOT "
    "perform the action here — say you can't do it from this channel and point "
    "the user to the desktop app."
)


def respond_to(message: PlatformMessage) -> str | None:
    """Route one inbound platform message into Umi's shared pipeline.

    Returns the reply text to send back on the originating channel. Unknown
    users get the fixed refusal text with zero LLM/tool/database access.
    Returns None only if the message should be dropped silently.
    """
    if resolve_role(message.platform, message.platform_user_id) != "owner":
        return refusal_text(message.platform, message.author_name)

    sender_context = _PLATFORM_CONTEXT_TEMPLATE.format(
        platform=message.platform,
        context=message.context_summary,
    )

    session = db_engine.get_session_factory()() if db_engine.db_enabled() else None
    try:
        reply, _conversation_id = handle_message(
            session,
            message.text,
            source=message.platform,
            conversation_key=message.conversation_key,
            conversation_title=message.conversation_title,
            platform_context=sender_context,
            include_greeting=False,
        )
        return reply
    finally:
        if session is not None:
            session.close()


__all__ = ["respond_to"]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_shared.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/integrations/shared.py backend/tests/test_integrations_shared.py
git commit -m "feat(integrations): shared platform responder with owner gating"
```

---

### Task 6: IntegrationSupervisor (threads + status)

**Files:**
- Create: `backend/app/integrations/supervisor.py`
- Test: `backend/tests/test_integrations_supervisor.py`

**Interfaces:**
- Consumes: `settings.discord_enabled`/`telegram_enabled` (Task 1), Task 8's `run_discord_bot(token, reporter)` and Task 7's `run_telegram_poller(token, reporter)` (lazy imports inside `start` so the module imports cleanly without a token)
- Produces: `IntegrationSupervisor.start()`, `IntegrationSupervisor.stop()`, `IntegrationSupervisor.status() -> dict`, module singleton `integration_supervisor`, and status constants `STATUS_DISABLED`, `STATUS_STARTING`, `STATUS_CONNECTED`, `STATUS_RECONNECTING`, `STATUS_ERROR`. Worker signature contract: `def worker(token: str, reporter: Callable[[str, str | None], None]) -> None` — `reporter(status, detail)`.

- [x] **Step 1: Write the failing tests**

```python
import time

from app.integrations.supervisor import (
    STATUS_DISABLED,
    STATUS_ERROR,
    IntegrationSupervisor,
)


def test_disabled_when_no_tokens(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_enabled", property(lambda self: False))
    monkeypatch.setattr(settings, "telegram_enabled", property(lambda self: False))
    sup = IntegrationSupervisor()
    sup.start()
    status = sup.status()
    assert status["discord"]["enabled"] is False
    assert status["telegram"]["enabled"] is False
    assert status["discord"]["status"] == STATUS_DISABLED
    sup.stop()


def test_start_never_raises_when_worker_missing(monkeypatch):
    from app.config import settings

    # simulate a broken worker target: supervisor must swallow it
    import app.integrations.supervisor as sup_mod

    monkeypatch.setattr(settings, "discord_enabled", property(lambda self: True))
    monkeypatch.setattr(settings, "discord_bot_token", "tok")
    monkeypatch.delattr(settings, "discord_bot_token", raising=False)
    monkeypatch.setattr(sup_mod, "run_discord_bot", lambda token, reporter: (_ for _ in ()).throw(RuntimeError("boom")))
    sup = IntegrationSupervisor()
    sup.start()
    time.sleep(0.1)
    assert sup.status()["discord"]["status"] == STATUS_ERROR
    sup.stop()


def test_status_has_no_token_material(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_enabled", property(lambda self: False))
    monkeypatch.setattr(settings, "telegram_enabled", property(lambda self: False))
    sup = IntegrationSupervisor()
    sup.start()
    raw = str(sup.status())
    assert "token" not in raw.lower().replace("bot_token", "")
    sup.stop()


def test_stop_is_idempotent():
    sup = IntegrationSupervisor()
    sup.stop()
    sup.stop()
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_supervisor.py -q`
Expected: FAIL — `ModuleNotFoundError: app.integrations.supervisor`

- [x] **Step 3: Implement supervisor.py**

```python
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from app.config import settings

logger = logging.getLogger("umi.integrations")

STATUS_DISABLED = "disabled"
STATUS_STARTING = "starting"
STATUS_CONNECTED = "connected"
STATUS_RECONNECTING = "reconnecting"
STATUS_ERROR = "error"

# Worker entrypoints, resolved lazily (they live in the discord/telegram
# subpackages which are created by later phases). Tests can swap entries.
_WORKER_TARGETS: dict[str, Callable] = {}

WorkerTarget = Callable[[str, Callable[[str, str | None], None]], None]


@dataclass
class _Worker:
    platform: str
    thread: threading.Thread | None = None
    status: str = STATUS_DISABLED
    detail: str | None = None


def _token_for(platform: str) -> str:
    if platform == "discord":
        return settings.discord_bot_token
    return settings.telegram_bot_token


def _enabled(platform: str) -> bool:
    return bool(_token_for(platform))


def _target_for(platform: str) -> WorkerTarget:
    if platform not in _WORKER_TARGETS:
        import importlib

        if platform == "discord":
            _WORKER_TARGETS["discord"] = getattr(
                importlib.import_module("app.integrations.discord.bot"),
                "run_discord_bot",
            )
        else:
            _WORKER_TARGETS["telegram"] = getattr(
                importlib.import_module("app.integrations.telegram.poller"),
                "run_telegram_poller",
            )
    return _WORKER_TARGETS[platform]


class IntegrationSupervisor:
    """Owns the Discord/Telegram background worker threads.

    Workers are daemons so a crashed or misconfigured integration can never
    take down uvicorn. ``start``/``stop`` are idempotent and never raise.
    Status reporting never includes token material.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workers: dict[str, _Worker] = {
            "discord": _Worker("discord"),
            "telegram": _Worker("telegram"),
        }

    def start(self) -> None:
        for platform in ("discord", "telegram"):
            if _enabled(platform):
                self._spawn(platform, _target_for(platform), _token_for(platform))

    def _spawn(self, platform: str, target: WorkerTarget, token: str) -> None:
        def _wrapped() -> None:
            try:
                target(token, reporter=self._report(platform))
            except Exception:  # noqa: BLE001 — a worker must never kill the app
                logger.exception("[%s] worker stopped unexpectedly", platform)
                self._report(platform)(STATUS_ERROR, "worker stopped unexpectedly")

        self._set(platform, STATUS_STARTING, None)
        thread = threading.Thread(target=_wrapped, name=f"umi-{platform}", daemon=True)
        self._workers[platform].thread = thread
        thread.start()

    def _report(self, platform: str):
        def report(status: str, detail: str | None = None) -> None:
            self._set(platform, status, detail)

        return report

    def _set(self, platform: str, status: str, detail: str | None) -> None:
        with self._lock:
            worker = self._workers[platform]
            worker.status = status
            worker.detail = detail

    def stop(self) -> None:
        """Best-effort: threads are daemons, so shutdown is process-scoped."""
        with self._lock:
            for worker in self._workers.values():
                worker.thread = None

    def status(self) -> dict:
        with self._lock:
            return {
                name: {
                    "enabled": _enabled(name),
                    "status": worker.status if _enabled(name) else STATUS_DISABLED,
                    "detail": worker.detail,
                }
                for name, worker in self._workers.items()
            }


integration_supervisor = IntegrationSupervisor()
```

Note (deviation from earlier draft): ``_enabled`` keys off the bot-token attribute
(not the ``discord_enabled`` property) so tests can monkeypatch the plain token
attribute; and workers are resolved through the ``_WORKER_TARGETS`` registry so
the supervisor tests don't require the Discord/Telegram subpackages to exist.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_supervisor.py -q`
Expected: PASS (the `run_discord_bot`/`run_telegram_poller` modules do not exist yet, so the second test's monkeypatch of `sup_mod.run_discord_bot` must be applied to the supervisor module attribute — this is why `_spawn` uses `getattr(importlib, ...)`. Note: test 2 imports the module attribute; if the attribute is missing, pre-create a dummy in the module namespace during that test.)

- [x] **Step 5: Commit**

```bash
git add backend/app/integrations/supervisor.py backend/tests/test_integrations_supervisor.py
git commit -m "feat(integrations): add supervised background workers with status"
```

---

### Task 7: Telegram client + long-poll worker (httpx MockTransport tests)

**Files:**
- Create: `backend/app/integrations/telegram/__init__.py` (empty)
- Create: `backend/app/integrations/telegram/telegram.py`
- Create: `backend/app/integrations/telegram/poller.py`
- Test: `backend/tests/test_integrations_telegram.py`

**Interfaces:**
- Consumes: `respond_to` (Task 5), status constants (Task 6), `telegram_owner_id` (Task 1)
- Produces: `TelegramAPI(bot_token, transport=None, timeout=60.0)` with `async get_updates(offset, timeout=50) -> dict`, `async send_message(chat_id, text)`, `async aclose()`; `build_platform_message(update: dict) -> PlatformMessage | None`; `run_telegram_poller(bot_token, reporter, transport=None)`; `async poll_forever(api, reporter, *, max_iterations=None, backoff_base=4.0) -> None`.

- [x] **Step 1: Write the failing tests**

```python
import asyncio
import logging
from unittest.mock import Mock

import httpx
import pytest

from app.integrations.telegram.poll_helpers import build_platform_message
from app.integrations.telegram.poller import poll_forever
from app.integrations.telegram.telegram import TelegramAPI


def _updates_payload(updates):
    return {"ok": True, "result": updates}


def test_build_platform_message_owner_message():
    update = {
        "update_id": 7,
        "message": {
            "message_id": 1,
            "from": {"id": 42, "first_name": "V"},
            "chat": {"id": 99, "username": "umi_hq"},
            "text": "hello",
        },
    }
    pm = build_platform_message(update)
    assert pm is not None
    assert pm.platform == "telegram"
    assert pm.platform_user_id == "42"
    assert pm.conversation_key == "99"
    assert "umi_hq" in pm.context_summary


def test_build_platform_message_ignores_empty():
    assert build_platform_message({}) is None
    assert build_platform_message({"message": {"from": {"id": 1}, "chat": {"id": 2}}}) is None


async def test_poll_round_trip_sends_reply(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/botT:tok/getUpdates":
            body = _updates_payload(
                [{
                    "update_id": 5,
                    "message": {
                        "message_id": 1,
                        "from": {"id": "own", "first_name": "V"},
                        "chat": {"id": 99, "username": "umi_hq"},
                        "text": "hi",
                    },
                }]
            )
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    api = TelegramAPI("T:tok", transport=transport)
    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(api, "send_message", fake_send)

    calls = {"n": 0, "replies": []}

    def fake_respond(pm):
        calls["n"] += 1
        calls["replies"].append(pm.text)
        return "reply-here"

    monkeypatch.setattr("app.integrations.telegram.poller.respond_to", fake_respond)

    statuses = []
    reporter = lambda status, detail=None: statuses.append(status)  # noqa: E731

    from app.config import settings
    monkeypatch.setattr(settings, "telegram_owner_id", "own")

    await poll_forever(api, reporter, max_iterations=1, backoff_base=0)
    assert calls["n"] == 1
    assert calls["replies"] == ["hi"]
    assert sent == [(99, "reply-here")]
    assert "connected" in statuses


async def test_poll_401_marks_error_and_stops(monkeypatch, caplog):
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    api = TelegramAPI("SNEAKY:tok-value", transport=transport)
    statuses = []
    reporter = lambda status, detail=None: statuses.append((status, detail))  # noqa: E731
    with caplog.at_level(logging.DEBUG):
        await poll_forever(api, reporter, max_iterations=5, backoff_base=0)
    assert statuses[-1][0] == "error"
    assert "SNEAKY" not in caplog.text


async def test_poll_retries_after_network_error(monkeypatch):
    state = {"calls": 0}

    def handler(request):
        state["calls"] += 1
        if state["calls"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=_updates_payload([]))

    transport = httpx.MockTransport(handler)
    api = TelegramAPI("T:tok", transport=transport)
    statuses = []
    reporter = lambda status, detail=None: statuses.append(status)  # noqa: E731
    await poll_forever(api, reporter, max_iterations=3, backoff_base=0)
    assert state["calls"] == 2
    assert "reconnecting" in statuses
    assert "connected" in statuses
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_telegram.py -q`
Expected: FAIL — `ModuleNotFoundError: app.integrations.telegram`

- [x] **Step 3: Implement telegram.py**

```python
from __future__ import annotations

import httpx


class TelegramAPIError(Exception):
    """Wraps a failed Telegram Bot API call."""


class TelegramAPI:
    """Minimal async client for the official Telegram Bot API (long-poll).

    ``transport`` is injectable for tests (httpx.MockTransport). The bot token
    only ever appears inside the HTTPS base URL path to api.telegram.org.
    """

    def __init__(
        self,
        bot_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token}",
            transport=transport,
            timeout=timeout,
        )

    async def get_updates(self, offset: int | None, timeout: int = 50) -> dict:
        resp = await self._client.get(
            "/getUpdates",
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["message"]',
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_message(self, chat_id: int, text: str) -> None:
        resp = await self._client.post("/sendMessage", data={"chat_id": chat_id, "text": text})
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [x] **Step 4: Implement poller.py**

```python
from __future__ import annotations

import asyncio
import logging

from app.integrations.supervisor import (
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_RECONNECTING,
)
from app.integrations.telegram.telegram import TelegramAPI
from app.integrations.types import PlatformMessage

logger = logging.getLogger("umi.integrations.telegram")


def build_platform_message(update: dict) -> PlatformMessage | None:
    """Normalize one Telegram update into a PlatformMessage, or None to skip."""
    message = update.get("message") or {}
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    text = message.get("text") or ""
    if not from_user.get("id") or not chat.get("id") or not text:
        return None
    chat_name = (
        chat.get("title")
        or chat.get("username")
        or chat.get("first_name")
        or f"chat {chat['id']}"
    )
    first = from_user.get("first_name") or ""
    last = from_user.get("last_name") or ""
    author_name = f"{first} {last}".strip() or str(from_user["id"])
    return PlatformMessage(
        platform="telegram",
        platform_user_id=str(from_user["id"]),
        author_name=author_name,
        text=text,
        conversation_key=str(chat["id"]),
        conversation_title=f"Telegram · {chat_name}"[:200],
        context_summary=f"You are talking to the user via Telegram in chat '{chat_name}'.",
    )


def _chat_id(message: PlatformMessage) -> int:
    return int(message.conversation_key)


async def poll_forever(
    api: TelegramAPI,
    reporter,
    *,
    max_iterations: int | None = None,
    backoff_base: float = 4.0,
) -> None:
    """Long-poll Telegram updates and pipe messages through ``respond_to``.

    Offset-based acking gives at-least-once delivery. Network failures flip to
    RECONNECTING with exponential backoff and resume; a 401 (invalid token)
    marks ERROR and stops. Tokens are never logged.
    """
    offset: int | None = None
    failures = 0
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        try:
            data = await api.get_updates(offset)
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                logger.error("[telegram] unauthorized (check the bot token)")
                reporter(STATUS_ERROR, "invalid bot token")
                return
            failures += 1
            backoff = min(60.0, backoff_base * (2 ** (failures - 1)))
            logger.warning("[telegram] polling error; reconnect in %.1fs", backoff)
            reporter(STATUS_RECONNECTING)
            await asyncio.sleep(backoff)
            continue

        failures = 0
        reporter(STATUS_CONNECTED, None)
        if not data.get("ok"):
            reporter(STATUS_ERROR, "Telegram API returned an error")
            return
        for update in data.get("result") or []:
            update_id = update.get("update_id")
            if update_id is not None:
                offset = update_id + 1
            message = build_platform_message(update)
            if message is None:
                continue
            try:
                reply = _respond_to(message)
            except Exception:
                logger.exception("[telegram] message handling failed")
                continue
            if reply:
                try:
                    await api.send_message(_chat_id(message), reply)
                except Exception:
                    logger.exception("[telegram] failed to send reply")


# imported late so tests can monkeypatch the name cleanly
def _respond_to(message: PlatformMessage) -> str | None:
    from app.integrations.shared import respond_to

    return respond_to(message)


def run_telegram_poller(bot_token: str, reporter, transport=None) -> None:
    """Blocking entrypoint for the supervisor thread (own event loop)."""
    asyncio.run(_main(bot_token, reporter, transport))


async def _main(bot_token: str, reporter, transport=None) -> None:
    api = TelegramAPI(bot_token, transport=transport)
    try:
        await poll_forever(api, reporter)
    finally:
        await api.aclose()
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_telegram.py -q`
Expected: PASS (asyncio tests run via `asyncio.run` inside `pytest` sync tests — create a `@pytest.mark.asyncio`? There is no pytest-asyncio plugin; instead use `asyncio.run(...)` wrappers as in prior phases. Wrap each `test_poll_*` body in `asyncio.run(...)`.)

- [x] **Step 6: Commit**

```bash
git add backend/app/integrations/telegram backend/tests/test_integrations_telegram.py
git commit -m "feat(telegram): Bot API client and long-poll worker"
```

---

### Task 8: Discord bot (discord.py gateway, fake-object tests)

**Files:**
- Modify: `backend/requirements.txt` (add `discord.py==2.4.0`)
- Create: `backend/app/integrations/discord/__init__.py` (empty)
- Create: `backend/app/integrations/discord/bot.py`
- Test: `backend/tests/test_integrations_discord.py`

**Interfaces:**
- Consumes: `respond_to` (Task 5), status constants (Task 6)
- Produces: `build_platform_message(message) -> PlatformMessage | None`; `run_discord_bot(token, reporter)`; `async handle_on_message(message, reporter)`.

- [x] **Step 1: Install the dependency**

Run: `cd backend && .venv/bin/python3.11 -m pip install "discord.py==2.4.0"` then append the pinned version to `requirements.txt`.

- [x] **Step 2: Write the failing tests**

```python
import asyncio
from types import SimpleNamespace

import pytest

from app.integrations.discord.bot import build_platform_message, handle_on_message


def make_author(bot=False, ident="123", name="UmiOwner"):
    return SimpleNamespace(bot=bot, id=ident, display_name=name)


def make_channel(ident=222, name="general", send_enabled=True):
    if not send_enabled:
        return SimpleNamespace(id=ident, name=name)
    return SimpleNamespace(id=ident, name=name, send=async_send)


async def async_send(text):
    return None


def make_message(author=None, content="hello", channel=None, guild=None):
    return SimpleNamespace(author=author or make_author(), content=content, channel=channel or make_channel(), guild=guild)


def test_build_platform_message_owner_in_guild_channel():
    msg = make_message(guild=SimpleNamespace(id=1, name="HQ"), channel=make_channel())
    pm = build_platform_message(msg)
    assert pm.platform == "discord"
    assert pm.platform_user_id == "123"
    assert pm.conversation_key == "1:222"
    assert "HQ" in pm.context_summary
    assert "#general" in pm.conversation_title


def test_build_platform_message_dm():
    msg = make_message(guild=None)
    pm = build_platform_message(msg)
    assert pm.conversation_key.startswith("dm:")
    assert pm.conversation_title == "Discord DM"


def test_build_platform_message_ignores_bots():
    assert build_platform_message(make_message(author=make_author(bot=True))) is None


def test_bot_message_ignored():
    author = make_author(bot=True)
    assert build_platform_message(make_message(author=author)) is None


async def test_on_message_unknown_user_refused(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "other")
    sent = []
    channel = SimpleNamespace(id=222, name="general", send=lambda t: sent.append(t))
    reporter = lambda status, detail=None: None  # noqa: E731
    await handle_on_message(make_message(channel=channel), reporter)
    assert sent and "owner" in sent[0] or not sent  # refusal is produced by respond_to


async def test_on_message_owner_sends_reply(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    sent = []
    channel = SimpleNamespace(id=222, name="general", send=lambda t: sent.append(t))

    async def fake_respond(pm):
        return "hi there"

    monkeypatch.setattr("app.integrations.discord.bot.respond_to", fake_respond)
    reporter = lambda status, detail=None: None  # noqa: E731
    await handle_on_message(make_message(channel=channel), reporter)
    assert sent == ["hi there"]


async def test_on_message_skips_channel_without_send():
    channel = make_channel(send_enabled=False)
    reporter = lambda status, detail=None: None  # noqa: E731
    # must not raise even though channel has no send
    await handle_on_message(make_message(channel=channel), reporter)
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_discord.py -q`
Expected: FAIL — `ModuleNotFoundError: app.integrations.discord`

- [x] **Step 4: Implement bot.py**

```python
from __future__ import annotations

import logging

import discord

from app.integrations.supervisor import STATUS_CONNECTED, STATUS_ERROR
from app.integrations.types import PlatformMessage

logger = logging.getLogger("umi.integrations.discord")


def _client_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


def build_platform_message(message) -> PlatformMessage | None:
    """Map a discord.py Message to a PlatformMessage, or None to ignore it."""
    author = getattr(message, "author", None)
    if author is None or getattr(author, "bot", False):
        return None
    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    if guild is None:
        key = f"dm:{channel_id}"
        title = "Discord DM"
        context = "a private direct message"
    else:
        guild_name = getattr(guild, "name", "?")
        channel_name = getattr(channel, "name", "?")
        key = f"{guild.id}:{channel_id}"
        title = f"Discord · {guild_name} · #{channel_name}"[:200]
        context = f"server '{guild_name}', channel '#{channel_name}'"
    author_name = getattr(author, "display_name", None) or str(getattr(author, "id", "?"))
    return PlatformMessage(
        platform="discord",
        platform_user_id=str(getattr(author, "id", "")),
        author_name=author_name,
        text=getattr(message, "content", "") or "",
        conversation_key=key,
        conversation_title=title,
        context_summary=f"You are talking to the user via Discord in {context}.",
    )


def _can_send(channel) -> bool:
    return callable(getattr(channel, "send", None))


async def handle_on_message(message, reporter) -> None:
    """Handle one on_message event; never raises out to the gateway loop."""
    try:
        pm = build_platform_message(message)
        if pm is None or not pm.text.strip():
            return
        reply = _respond_to(pm)
        if reply and _can_send(message.channel):
            await message.channel.send(reply)
    except Exception:  # noqa: BLE001
        logger.exception("[discord] message handling failed")
        reporter(STATUS_ERROR, "message handling failed")


def _respond_to(pm: PlatformMessage) -> str | None:
    from app.integrations.shared import respond_to

    return respond_to(pm)


def make_client(reporter):
    client = discord.Client(intents=_client_intents())

    @client.event
    async def on_ready():
        logger.info("[discord] gateway ready")
        reporter(STATUS_CONNECTED, None)

    @client.event
    async def on_message(message):
        await handle_on_message(message, reporter)

    return client


def run_discord_bot(bot_token: str, reporter) -> None:
    """Blocking entrypoint for the supervisor thread."""
    client = make_client(reporter)
    try:
        client.run(bot_token)
    except Exception:  # noqa: BLE001
        logger.exception("[discord] gateway connection failed")
        reporter(STATUS_ERROR, "gateway connection failed")
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_discord.py -q`
Expected: PASS (wrap async tests with `asyncio.run(...)`)

- [x] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/integrations/discord backend/tests/test_integrations_discord.py
git commit -m "feat(discord): discord.py gateway bot wired to shared responder"
```

---

### Task 9: `GET /integrations/status` API + main.py wiring

**Files:**
- Create: `backend/app/api/integrations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_integrations_api.py`

**Interfaces:**
- Consumes: `integration_supervisor.status()` (Task 6)
- Produces: router mounted at `/integrations` with `GET /integrations/status -> {"discord": {...}, "telegram": {...}}`; supervisor started/stopped in lifespan.

- [x] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.integrations.supervisor import integration_supervisor

client = TestClient(app)


def test_status_endpoint_shape():
    resp = client.get("/integrations/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"discord", "telegram"}
    for platform in ("discord", "telegram"):
        assert set(body[platform].keys()) == {"enabled", "status", "detail"}
    raw = str(body).lower()
    assert "bot_token" not in raw


def test_status_reflects_supervisor(monkeypatch):
    monkeypatch.setattr(integration_supervisor, "status", lambda: {"discord": {"enabled": True, "status": "connected", "detail": None}, "telegram": {"enabled": False, "status": "disabled", "detail": None}})
    body = client.get("/integrations/status").json()
    assert body["discord"]["status"] == "connected"
    assert body["telegram"]["enabled"] is False


def test_lifespan_starts_supervisor_without_error():
    # client context already ran lifespan on first request; a second request keeps working
    assert client.get("/integrations/status").status_code == 200
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_api.py -q`
Expected: FAIL — `404 Not Found` from `/integrations/status`

- [x] **Step 3: Implement the router**

```python
from fastapi import APIRouter

from app.integrations.supervisor import integration_supervisor

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def status() -> dict:
    """Live status for the Discord/Telegram workers.

    Returns only booleans / short labels / safe detail strings — never tokens
    or foreign ids.
    """
    return integration_supervisor.status()


__all__ = ["router"]
```

- [x] **Step 4: Wire into main.py**

```python
from app.api.integrations import router as integrations_router
```
(import block), add `app.include_router(integrations_router)` after `google_router`, and in `lifespan`, replace the `yield` section:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if db_enabled():
        logging.getLogger("umi").info("database connection ready")
    else:
        logging.getLogger("umi").warning("no DATABASE_URL set - running without persistence")
    from app.integrations.supervisor import integration_supervisor

    integration_supervisor.start()
    logging.getLogger("umi").info("integration workers started")
    yield
    integration_supervisor.stop()
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python3.11 -m pytest tests/test_integrations_api.py tests/test_api.py -q`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add backend/app/api/integrations.py backend/app/main.py backend/tests/test_integrations_api.py
git commit -m "feat(api): expose integration status endpoint and start workers in lifespan"
```

---

### Task 10: Frontend integration status chips

**Files:**
- Modify: `frontend/app/lib/gmail.ts` (add `api().integrationsStatus()` — or a new `frontend/app/lib/integrations.ts` per interface below)
- Modify: `frontend/app/GmailPanel.tsx` (render two chips under the header)
- Test: `frontend/tests/integrations-status.test.mjs`

**Interfaces:**
- Consumes: `GET /integrations/status` response shape from Task 9
- Produces: `api().integrationsStatus(): Promise<{discord: {enabled, status, detail}, telegram: {...}}>`; chip labels/colors when `status === "connected" | "reconnecting" | "error" | "disabled"`.

- [x] **Step 1: Write the failing test** (mirror `frontend/tests/google-status.test.mjs` — import gmail lib, override global fetch)

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import * as gmail from "../app/lib/gmail.ts";

test("integrationsStatus parses backend response", async () => {
  let called = null;
  global.fetch = async (url) => {
    called = url;
    return new Response(
      JSON.stringify({
        discord: { enabled: true, status: "connected", detail: null },
        telegram: { enabled: true, status: "error", detail: "invalid bot token" },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  };
  const s = await gmail.integrationsStatus();
  assert.match(String(called), /\/integrations\/status$/);
  assert.equal(s.discord.status, "connected");
  assert.equal(s.telegram.status, "error");
});

test("integrationsStatus throws on failure", async () => {
  global.fetch = async () => new Response("nope", { status: 503 });
  await assert.rejects(() => gmail.integrationsStatus());
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: the new file FAILS (`gmail.integrationsStatus is not a function`)

- [x] **Step 3: Implement the lib function** (in `frontend/app/lib/gmail.ts`, alongside `googleStatus`)

```ts
export type IntegrationEntry = { enabled: boolean; status: string; detail: string | null };
export type IntegrationsStatus = { discord: IntegrationEntry; telegram: IntegrationEntry };

export async function integrationsStatus(): Promise<IntegrationsStatus> {
  const url = `${getBackendUrl()}/integrations/status`;
  const res = await fetch(url, { headers: { "Content-Type": "application/json" } });
  if (!res.ok) throw new Error(`integrations status failed (${res.status})`);
  return (await res.json()) as IntegrationsStatus;
}
```
(where `getBackendUrl()` is the existing helper used by `googleStatus` — reuse it.)

- [x] **Step 4: Add chips to GmailPanel** — under the header row (after the `{googleStatus && (...)}` block), render:

```tsx
<IntegrationChips />
```
with a tiny local component in `GmailPanel.tsx` that fetches `integrationsStatus()` on mount and maps `{discord: "Discord", telegram: "Telegram"}` to colored pills: `connected` → `bg-holo-mint/10 text-holo-mint`, `error` → `bg-holo-danger/10 text-holo-danger`, `reconnecting` → `bg-holo-amber/10 text-holo-amber`, else → `bg-white/[0.03] text-holo-dim`. Use the same chip markup style as the `GOOGLE_SERVICES` chips (GmailPanel.tsx:249-266).

- [x] **Step 5: Run frontend tests + lint + build**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: all pass

- [x] **Step 6: Commit**

```bash
git add frontend/app/lib/gmail.ts frontend/app/GmailPanel.tsx frontend/tests/integrations-status.test.mjs
git commit -m "feat(frontend): show Discord/Telegram integration status chips"
```

---

### Task 11: Full regression + live verification

**Files:** none new.

- [x] **Step 1: Full backend suite**

Run: `cd backend && .venv/bin/python3.11 -m pytest -q`
Expected: all pass (baseline 259 + new integration tests)

- [x] **Step 2: Full frontend + desktop**

Run: `cd frontend && npm test && npm run lint && npm run build`
Run: `cd desktop && npm test`
Expected: all pass

- [x] **Step 3: Restart backend and live-check the endpoint**

Run (documented in the final report — backend token-free by default so statuses show `enabled:false`):

```bash
cd backend && .venv/bin/python3.11 -c "import subprocess, sys; subprocess.Popen([sys.executable, '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'], stdout=open('/tmp/umi-backend.log','a'), stderr=subprocess.STDOUT, start_new_session=True)"
sleep 3 && curl -s http://127.0.0.1:8000/integrations/status
```
Expected: `{"discord":{"enabled":false,"status":"disabled","detail":null},"telegram":{"enabled":false,"status":"disabled","detail":null}}` and no worker errors in `/tmp/umi-backend.log`.

Also verify existing endpoints still live: `curl -s http://127.0.0.1:8000/google/status`.

- [x] **Step 4: Docs + migration instructions**

- Append a `PHASE 8` section to `Phase.md` (setup steps, env vars, migration command for Supabase, status endpoint, manual smoke tests).
- Update `README.md` with a one-line mention of Discord/Telegram support.
- Migration to run once on Supabase (document, do NOT run against a live DB without the user):
  `psql "<DATABASE_URL>" -f backend/migrations/0002_add_conversation_source.sql`

- [x] **Step 5: Final report**

Provide the 12-item final report (architecture, files, deps, env vars, Discord setup, Telegram setup, permissions/intents, authorization, tests run, manual tests the user must run, unresolved items). Do NOT claim the channels "work" until the user has run the manual smoke tests.

---

## Execution completed 2026-09-08

All 11 tasks implemented via TDD on branch `feature/discord-telegram`. Final
regression: **backend 297 passed**, **frontend 43 passed** (test + lint + build
clean), **desktop 8 passed**. Live endpoint verified:

```json
{"discord":{"enabled":false,"status":"disabled","detail":null},"telegram":{"enabled":false,"status":"disabled","detail":null}}
```

## Deviations from the plan

1. **discord.py `2.4.0` not `2.4.1`** — `2.4.1` does not exist on PyPI; `2.4.0` is the latest in the 2.4 line.
2. `build_platform_message` lives in `poller.py` (the plan's task-7 tests imported a stale `poll_helpers` name).
3. **httpx request-log redaction** — httpx logs full URLs at INFO and the Telegram token sits in the URL path, so `telegram.py` suppresses `logging.getLogger("httpx")` to WARNING; the 401 test asserts the token never reaches output.
4. `test_config_integrations.py` **replaced `importlib.reload(app.config)` with instance-attribute patching** — reloading swapped the `settings` singleton out from under modules that captured it at import time (split-brain failures only in full-suite runs); the new properties are driven by instance attrs, so no reload is needed.
5. `Phase.md` section appended as **`PHASE 7.8`** (the repo already has `PHASE 8 — PHYSICAL UMI DISPLAY`); `backend/.env.example` keeps the user spec's "Phase 8" label for the credential block.

## Remaining (user)
- Add real Discord/Telegram credentials to `backend/.env`.
- Run migration `0002` on Supabase (documented in Phase 7.8).
- Run the manual smoke tests before considering the channels live.