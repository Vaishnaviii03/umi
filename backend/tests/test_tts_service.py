import httpx
import pytest

from app.services.elevenlabs_tts import ElevenLabsTTS, TTSError


def make_service(handler) -> ElevenLabsTTS:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return ElevenLabsTTS(api_key="test-key", voice_id="test-voice", model_id="test-model", client=client)


def test_synthesize_returns_audio_bytes():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("xi-api-key")
        captured["accept"] = request.headers.get("accept")
        captured["auth"] = "key-string" in str(request.headers.get("xi-api-key"))
        return httpx.Response(200, content=b"\xff\xfb\x00\x00MP3", headers={"content-type": "audio/mpeg"})

    service = make_service(handler)
    try:
        audio = service.synthesize("hello there")
    finally:
        service.close()
    assert audio == b"\xff\xfb\x00\x00MP3"
    assert captured["key"] == "test-key"
    assert captured["accept"] == "audio/mpeg"


def test_synthesize_sends_text_and_model():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, content=b"\xff\xfb")

    service = make_service(handler)
    try:
        service.synthesize("  hello  ")
    finally:
        service.close()

    import json

    body = json.loads(captured["body"])
    assert body["text"] == "hello"
    assert body["model_id"] == "test-model"


def test_missing_api_key_raises():
    service = ElevenLabsTTS(api_key="", voice_id="v", model_id="m")
    with pytest.raises(TTSError):
        service.synthesize("hi")


def test_empty_text_raises():
    service = make_service(lambda request: httpx.Response(200, content=b"\xff\xfb"))
    try:
        with pytest.raises(TTSError):
            service.synthesize("   ")
    finally:
        service.close()


def test_provider_failure_raises():
    service = make_service(lambda request: httpx.Response(401, text="unauthorized"))
    try:
        with pytest.raises(TTSError) as exc_info:
            service.synthesize("hi")
    finally:
        service.close()
    # Internal diagnostic-based error message must not leak tokens/status as detail.
    assert "unauthorized" not in str(exc_info.value)
    assert "401" in str(exc_info.value)


def test_provider_empty_audio_raises():
    service = make_service(lambda request: httpx.Response(200, content=b""))
    try:
        with pytest.raises(TTSError):
            service.synthesize("hi")
    finally:
        service.close()


def test_not_configured_short_circuits():
    service = ElevenLabsTTS(api_key="", voice_id="v", model_id="m")
    assert service.is_configured() is False