import uuid
from unittest.mock import patch

from app.db import models


def test_handle_message_platform_creates_source_conversation(db_session):
    from app.orchestrator.core import handle_message

    with patch("app.llm.manager.llm_manager.generate_reply", return_value="ok"):
        reply, cid = handle_message(
            db_session,
            "hello",
            source="discord",
            conversation_key="g:ch",
            conversation_title="Discord · #main",
            platform_context="You are talking via Discord. Reply in plain text.",
        )
    assert reply == "ok"
    conv = db_session.get(models.Conversation, uuid.UUID(cid))
    assert conv is not None
    assert conv.source == "discord"
    assert conv.conversation_key == "g:ch"
    assert conv.title == "Discord · #main"
    rows = (
        db_session.query(models.Message)
        .filter(models.Message.conversation_id == conv.id)
        .all()
    )
    assert [m.role for m in rows] == ["user", "assistant"]


def test_handle_message_platform_context_injected_and_greeting_off(db_session):
    captured = {}

    def _fake(message, **kwargs):
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

    with patch("app.llm.manager.llm_manager.generate_reply", return_value="ok"):
        reply, cid = handle_message(db_session, "test drive")
    assert reply == "ok"
    conv = db_session.get(models.Conversation, uuid.UUID(cid))
    assert conv.source == "desktop"
    assert conv.conversation_key is None