from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_voice_flag_passed_to_handler():
    with patch("app.api.routes.handle_message", return_value=("ok", None)) as handle:
        response = client.post("/chat", json={"message": "hi", "voice": True})
    assert response.status_code == 200
    # db, message, conversation_id, voice
    assert handle.call_args.kwargs["voice"] is True


def test_chat_voice_flag_defaults_to_false():
    with patch("app.api.routes.handle_message", return_value=("ok", None)) as handle:
        response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert handle.call_args.kwargs["voice"] is False


def test_handle_message_injects_local_time_without_db():
    from app.orchestrator.core import handle_message

    fake_reply = '"It is 4:16 AM for you."'
    llm = MagicMock()
    llm.generate_reply.return_value = fake_reply
    with patch("app.orchestrator.core.llm_manager", llm):
        reply, conversation_id = handle_message(None, "What time is it?")
    assert reply == fake_reply
    assert conversation_id is None
    _, kwargs = llm.generate_reply.call_args
    assert "time" in (kwargs.get("memories") or "").lower()
    assert kwargs.get("voice") is False


def test_handle_message_voice_guidance_uses_voice_flag():
    from app.orchestrator.core import handle_message

    fake_reply = "It is 4:16 AM."
    llm = MagicMock()
    llm.generate_reply.return_value = fake_reply
    with patch("app.orchestrator.core.llm_manager", llm):
        reply, _ = handle_message(None, "What time is it?", voice=True)
    assert reply == fake_reply
    _, kwargs = llm.generate_reply.call_args
    assert kwargs.get("voice") is True
    assert "time" in (kwargs.get("memories") or "").lower()


def test_history_cache_round_trip_and_append():
    from app.orchestrator import core

    conv_id = "c0ffee00-0000-0000-0000-000000000001"
    core._cache_history(conv_id, [{"role": "assistant", "content": "hi"}])
    assert core._cached_history(conv_id, 10) == [{"role": "assistant", "content": "hi"}]
    core._append_cached_message(conv_id, "user", "hello")
    core._append_cached_message(conv_id, "assistant", "hey")
    assert core._cached_history(conv_id, 10)[-2:] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hey"},
    ]
    assert core._cached_history(conv_id, 1) == [{"role": "assistant", "content": "hey"}]
    assert core._cached_history("00000000-0000-0000-0000-000000000002", 10) is None


def test_stream_message_without_db_yields_chunks_and_done():
    from app.orchestrator.core import stream_message

    llm = MagicMock()
    llm.stream_reply.return_value = iter(["Hello", " there."])
    with patch("app.orchestrator.core.llm_manager", llm):
        events = list(stream_message(None, "hi", voice=True))
    assert events[0] == ("chunk", {"text": "Hello"})
    assert events[1] == ("chunk", {"text": " there."})
    assert events[2][0] == "done"
    assert events[2][1]["reply"] == "Hello there."
    assert events[2][1]["conversation_id"] is None
    _, kwargs = llm.stream_reply.call_args
    assert kwargs.get("voice") is True
    assert kwargs.get("fast") is True


def test_stream_message_persists_full_reply_with_db(db_session):
    import uuid

    from app.orchestrator.core import stream_message

    llm = MagicMock()
    llm.stream_reply.return_value = iter(["Hi!", " How are you?"])
    with patch("app.orchestrator.core.llm_manager", llm):
        events = list(stream_message(db_session, "hello", voice=False))

    done = events[-1][1]
    assert done["reply"] == "Hi! How are you?"
    assert done["conversation_id"] is not None

    from app.db.repositories import get_messages

    stored = get_messages(db_session, uuid.UUID(done["conversation_id"]))
    assert [m.content for m in stored] == ["hello", "Hi! How are you?"]


def test_stream_message_error_emits_safe_event():
    from app.orchestrator.core import stream_message
    from app.llm.manager import LLMError

    llm = MagicMock()
    llm.stream_reply.side_effect = LLMError("boom")
    with patch("app.orchestrator.core.llm_manager", llm):
        events = list(stream_message(None, "hi"))
    assert events[0][0] == "error"
    assert "reasoning engine" in events[0][1]["detail"]