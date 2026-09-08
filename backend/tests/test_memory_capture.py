"""Task 7 — memory layering: automatic capture of durable facts and
gate-keeping so casual text turns keep memories while voice loops skip them.
"""

from unittest.mock import MagicMock, patch

from app.db.models import Conversation, Memory
from app.db.repositories import create_memory, get_or_create_conversation
from app.orchestrator.core import (
    CASUAL_MESSAGE_MAX_CHARS,
    _build_context,
    _maybe_autocapture,
)


def _conversation(db_session):
    return get_or_create_conversation(db_session, None)


def _count_memories(db_session):
    return db_session.query(Memory).count()


# ------------------------------------------------------ auto-capture heuristic

def test_autocapture_stores_durable_fact(db_session):
    conv = _conversation(db_session)
    memory = _maybe_autocapture(db_session, conv, "I'll remember my goal is to run every morning")
    assert memory is not None
    assert memory.content == "I'll remember my goal is to run every morning"
    assert memory.source_conversation_id == conv.id
    assert _count_memories(db_session) == 1


def test_autocapture_skips_questions(db_session):
    conv = _conversation(db_session)
    assert _maybe_autocapture(db_session, conv, "What should I plan for tomorrow?") is None
    assert _count_memories(db_session) == 0


def test_autocapture_skips_short_chatter(db_session):
    conv = _conversation(db_session)
    assert _maybe_autocapture(db_session, conv, "my goal is") is None
    assert _count_memories(db_session) == 0


def test_autocapture_skips_plain_statements_without_signal(db_session):
    conv = _conversation(db_session)
    assert _maybe_autocapture(db_session, conv, "the weather is nice today outside") is None
    assert _count_memories(db_session) == 0


def test_autocapture_dedupes_exact_facts(db_session):
    conv = _conversation(db_session)
    text = "I like green tea and I'll choose it over coffee"
    assert _maybe_autocapture(db_session, conv, text) is not None
    assert _maybe_autocapture(db_session, conv, text) is None
    assert _count_memories(db_session) == 1


def test_autocapture_is_best_effort_never_raises(db_session):
    conv = _conversation(db_session)
    with patch(
        "app.orchestrator.core.create_memory",
        side_effect=RuntimeError("db down"),
    ):
        assert _maybe_autocapture(db_session, conv, "remember I work at the lab") is None


# ------------------------------------------------------ memory layering on turns

def test_build_context_casual_text_includes_memories(db_session):
    conv = _conversation(db_session)
    create_memory(db_session, "the Boss likes hiking", source_conversation_id=conv.id)
    db_session.commit()
    system, context_block, history, conversation, created = _build_context(
        db_session,
        "hi",
        None,
        voice=False,
        include_memories=True,
    )
    assert "hiking" in context_block


def test_build_context_voice_skips_memory_block(db_session):
    conv = _conversation(db_session)
    create_memory(db_session, "the Boss likes hiking", source_conversation_id=conv.id)
    db_session.commit()
    system, context_block, history, conversation, created = _build_context(
        db_session,
        "hi",
        None,
        voice=True,
        include_memories=not True,  # not voice -> False
    )
    assert "hiking" not in context_block


def test_casual_turn_below_chars_keeps_memories_on_handle_message(db_session):
    # A casual text turn (<= CASUAL_MESSAGE_MAX_CHARS) must still surface
    # memories — the /session payload keeps 4 relevant ones for these turns.
    conv = _conversation(db_session)
    create_memory(db_session, "the Boss likes hiking", source_conversation_id=conv.id)
    db_session.commit()

    llm = MagicMock()
    llm.generate_reply.return_value = "Great to hear!"
    from app.orchestrator.core import handle_message

    with patch("app.orchestrator.core.llm_manager", llm):
        reply, _ = handle_message(db_session, "hi", voice=False)

    kwargs = llm.generate_reply.call_args.kwargs
    assert kwargs["voice"] is False
    assert kwargs["fast"] is True  # casual -> fast model
    assert "hiking" in (kwargs["memories"] or "")


def test_voice_turn_skips_memory_block_on_handle_message(db_session):
    conv = _conversation(db_session)
    create_memory(db_session, "the Boss likes hiking", source_conversation_id=conv.id)
    db_session.commit()

    llm = MagicMock()
    llm.generate_reply.return_value = "Thanks for the tip."
    from app.orchestrator.core import handle_message

    with patch("app.orchestrator.core.llm_manager", llm):
        reply, _ = handle_message(db_session, "go for a hike", voice=True)

    kwargs = llm.generate_reply.call_args.kwargs
    assert kwargs["voice"] is True
    assert kwargs["memories"] is None or "hiking" not in kwargs["memories"]