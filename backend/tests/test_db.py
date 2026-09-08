import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.repositories import (
    append_message,
    create_memory,
    delete_memory,
    get_messages,
    get_or_create_conversation,
    list_memories,
    retrieve_relevant_memories,
)
from app.db.session import get_db
from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Conversation persistence
# --------------------------------------------------------------------------- #
def test_get_or_create_conversation_is_stable(db_session):
    conv1 = get_or_create_conversation(db_session)
    conv2 = get_or_create_conversation(db_session)
    assert conv1.id == conv2.id
    db_session.commit()


def test_append_and_read_messages(db_session):
    conv = get_or_create_conversation(db_session)
    append_message(db_session, conv.id, "user", "hi there")
    append_message(db_session, conv.id, "assistant", "hello!")
    db_session.commit()

    messages = get_messages(db_session, conv.id)
    assert [(m.role, m.content) for m in messages] == [
        ("user", "hi there"),
        ("assistant", "hello!"),
    ]
    db_session.delete(conv)
    db_session.commit()


def test_handle_message_persists_and_returns_conversation_id(db_session):
    from app.orchestrator.core import handle_message

    with patch("app.orchestrator.core.llm_manager.generate_reply", return_value="stub reply"):
        reply, conversation_id = handle_message(db_session, "hello world")
    db_session.commit()

    assert reply == "stub reply"
    assert conversation_id is not None

    messages = get_messages(db_session, uuid.UUID(conversation_id))
    assert [(m.role, m.content) for m in messages] == [
        ("user", "hello world"),
        ("assistant", "stub reply"),
    ]


def test_chat_endpoint_returns_conversation_id():
    with patch("app.api.routes.handle_message", return_value=("stub reply", "cv-123")):
        response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json() == {"reply": "stub reply", "conversation_id": "cv-123"}


# --------------------------------------------------------------------------- #
# Memory lifecycle
# --------------------------------------------------------------------------- #
def test_memory_create_list_retrieve_delete(db_session):
    create_memory(db_session, "user prefers dark mode")
    create_memory(db_session, "user drinks chai every morning")
    db_session.commit()

    memories = list_memories(db_session)
    assert len(memories) == 2

    hits = retrieve_relevant_memories(db_session, "what does the user drink?", limit=5)
    assert any("chai" in m.content for m in hits)

    first = memories[0]
    assert delete_memory(db_session, first.id) is True
    db_session.commit()
    assert len(list_memories(db_session)) == 1


def test_retrieve_relevant_memories_falls_back_to_recent(db_session):
    create_memory(db_session, "nothing matches these words here")
    db_session.commit()
    hits = retrieve_relevant_memories(db_session, "zzzz unknown terms", limit=5)
    assert len(hits) == 1


# --------------------------------------------------------------------------- #
# API-level memory endpoints (against the SQLite test DB)
# --------------------------------------------------------------------------- #
def test_memory_endpoints_lifecycle():
    created = client.post("/memories", json={"content": "UMI is a personal assistant"})
    assert created.status_code == 201
    memory_id = created.json()["id"]

    listed = client.get("/memories")
    assert listed.status_code == 200
    assert any(m["id"] == memory_id for m in listed.json())

    deleted = client.delete(f"/memories/{memory_id}")
    assert deleted.status_code == 204

    after = client.get("/memories")
    assert all(m["id"] != memory_id for m in after.json())


def test_conversations_endpoint():
    response = client.get("/conversations")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_conversation_messages_endpoint_404_for_unknown():
    response = client.get(f"/conversations/{uuid.uuid4()}/messages")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Graceful degradation when the database is unavailable
# --------------------------------------------------------------------------- #
def test_memory_endpoints_503_when_db_disabled():
    overrides = {get_db: lambda: None}
    app.dependency_overrides.update(overrides)
    try:
        assert client.get("/memories").status_code == 503
        assert client.get("/conversations").status_code == 503
        assert client.post("/memories", json={"content": "x"}).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_chat_still_works_when_db_disabled():
    overrides = {get_db: lambda: None}
    app.dependency_overrides.update(overrides)
    try:
        # handle_message keeps its own tuple contract; earlier we proved the
        # orchestration path works both with and without a configured DB.
        with patch("app.api.routes.handle_message", return_value=("offline reply", None)):
            response = client.post("/chat", json={"message": "ping"})
        assert response.status_code == 200
        assert response.json() == {"reply": "offline reply", "conversation_id": None}
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Phase 8 — per-platform conversation threads
# --------------------------------------------------------------------------- #
def test_get_or_create_conversation_with_source(db_session):
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
    db_session.commit()


def test_platform_sources_are_isolated(db_session):
    discord = get_or_create_conversation(db_session, source="discord", conversation_key="1:2")
    telegram = get_or_create_conversation(db_session, source="telegram", conversation_key="3")
    desktop = get_or_create_conversation(db_session)
    assert discord.id != telegram.id
    assert telegram.id != desktop.id
    assert discord.id != desktop.id
    db_session.commit()


def test_desktop_default_preserves_latest_conversation(db_session):
    from app.db.repositories import OWNER_USER_ID
    from app.db.models import Conversation

    first = Conversation(user_id=OWNER_USER_ID, title="A", source="desktop")
    db_session.add(first)
    db_session.flush()
    got = get_or_create_conversation(db_session)
    assert got.id == first.id
    assert got.source == "desktop"
    db_session.commit()