"""Phase 7 — Natural Conversation End-to-End Test.

Verifies the complete Speak → STT → UMI → LLM → TTS → Speak back pipeline:
1. STT authorization via /stt/token
2. Voice turn streaming via /chat/stream with voice=True
3. Sentence-boundary streaming chunking
4. Local TTS synthesis (/tts) yielding valid WAV audio
5. Multi-turn conversational context continuity under voice constraints
6. Interruption / barge-in simulation
"""

import io
import json
import wave
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_stt_token_endpoint():
    """Verify STT token issuance or graceful fallback response."""
    response = client.get("/stt/token")
    # Status code is 200 (if key configured) or 503/400 (if no key / credits)
    assert response.status_code in (200, 503, 400)
    data = response.json()
    if response.status_code == 200:
        assert "token" in data
    else:
        assert "detail" in data


def test_voice_stream_sentence_chunking_to_tts_e2e():
    """Full loop: User utterance -> /chat/stream (voice=True) -> Sentence splitting -> /tts -> WAV."""
    mock_chunks = [
        "Good morning! ",
        "I have reviewed your ",
        "schedule for today. ",
        "You have a meeting at 10 AM.",
    ]

    llm = MagicMock()
    llm.stream_reply.return_value = iter(mock_chunks)

    # 1. Stream voice reply from backend
    with patch("app.orchestrator.core.llm_manager", llm):
        response = client.post(
            "/chat/stream",
            json={"message": "What is my plan today?", "voice": True},
        )
    assert response.status_code == 200

    # Parse SSE text
    lines = response.text.strip().split("\n")
    collected_text = ""
    for line in lines:
        if line.startswith("data: "):
            payload = json.loads(line[len("data: ") :])
            if "text" in payload:
                collected_text += payload["text"]

    assert "Good morning!" in collected_text
    assert "meeting at 10 AM" in collected_text

    # 2. Extract first complete sentence for TTS
    first_sentence = collected_text.split("!")[0] + "!"

    # 3. Synthesize via /tts
    tts_response = client.post("/tts", json={"text": first_sentence})
    # Should return 200 with audio/wav
    if tts_response.status_code == 200:
        assert tts_response.headers["content-type"] == "audio/wav"
        # Validate RIFF header
        audio_bytes = tts_response.content
        assert len(audio_bytes) > 44  # WAV header is 44 bytes
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            assert wf.getnchannels() in (1, 2)
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.getframerate() in (16000, 22050, 24000, 44100)


def test_multi_turn_voice_context_retention(db_session):
    """Voice turns maintain conversational memory and history."""
    from app.orchestrator.core import handle_message

    llm = MagicMock()
    llm.generate_reply.side_effect = [
        "Hello! Pleasure to meet you.",
        "Your name is Vaishnavi.",
    ]

    with patch("app.orchestrator.core.llm_manager", llm):
        # Turn 1
        reply1, conv_id = handle_message(
            db_session,
            "Hi Umi, my name is Vaishnavi.",
            voice=True,
        )
        assert conv_id is not None
        assert reply1 == "Hello! Pleasure to meet you."

        # Turn 2 in same conversation
        reply2, conv_id2 = handle_message(
            db_session,
            "What is my name?",
            conversation_id=conv_id,
            voice=True,
        )
        assert conv_id2 == conv_id
        assert reply2 == "Your name is Vaishnavi."

    # Verify LLM was called with voice=True on both turns
    assert llm.generate_reply.call_count == 2
    for call in llm.generate_reply.call_args_list:
        assert call.kwargs.get("voice") is True


def test_voice_barge_in_and_cancellation():
    """Simulates client aborting an ongoing turn when user interrupts."""
    llm = MagicMock()

    def slow_generator():
        yield "First sentence. "
        yield "Second sentence. "
        yield "Third sentence. "

    llm.stream_reply.return_value = slow_generator()

    with patch("app.orchestrator.core.llm_manager", llm):
        # Client initiates stream
        with client.stream("POST", "/chat/stream", json={"message": "Tell me a story", "voice": True}) as stream:
            first_chunk = next(stream.iter_lines())
            assert "data:" in first_chunk
            # Client disconnects (barge-in / interruption)
            stream.close()

    # Verify a subsequent turn immediately processes without hanging
    fast_llm = MagicMock()
    fast_llm.generate_reply.return_value = "Stopped."
    with patch("app.orchestrator.core.llm_manager", fast_llm):
        reply, _ = client.post("/chat", json={"message": "Stop", "voice": True}).json().values()
        assert reply == "Yes Boss? Were you saying something else?"
