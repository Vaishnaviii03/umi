from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.local_tts import TTSError

client = TestClient(app)

AUDIO_BYTES = b"\xff\xfb\x90\x00UMI-audio"


def test_tts_missing_key_returns_503():
    with patch("app.api.routes.tts_service.is_configured", return_value=False):
        response = client.post("/tts", json={"text": "hello"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "voice" in detail.lower()
    assert "still works" in detail


def test_tts_success_returns_audio():
    with patch("app.api.routes.tts_service.synthesize", return_value=AUDIO_BYTES):
        response = client.post("/tts", json={"text": "hello"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == AUDIO_BYTES


def test_tts_empty_text_rejected():
    response = client.post("/tts", json={"text": ""})
    assert response.status_code == 422


def test_tts_text_too_long_rejected():
    response = client.post("/tts", json={"text": "a" * 4001})
    assert response.status_code == 422


def test_tts_provider_failure_returns_safe_error():
    with patch("app.api.routes.tts_service.is_configured", return_value=True), patch(
        "app.api.routes.tts_service.synthesize",
        side_effect=TTSError("TTS provider returned HTTP 401"),
    ):
        response = client.post("/tts", json={"text": "hello"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "voice" in detail.lower()
    assert "still works" in detail
    # Never leak provider internals / status codes / keys to the client.
    assert "401" not in detail
    assert "sk-" not in detail
    assert "xi-api-key" not in detail


def test_preflight_allowed_for_desktop_shell_origin():
    response = client.options(
        "/tts",
        headers={
            "Origin": "http://127.0.0.1:3456",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3456"


def test_tts_voices_returns_safe_listing():
    listing = [
        {"id": "com.apple.voice.compact.en-US.Samantha", "name": "Samantha", "language": "en_US", "gender": "VoiceGenderFemale"}
    ]
    with patch("app.api.routes.tts_service.is_configured", return_value=True), patch(
        "app.api.routes.tts_service.current_voice", return_value="com.apple.voice.compact.en-US.Samantha"
    ), patch("app.api.routes.tts_service.list_voices", return_value=listing):
        response = client.get("/tts/voices")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["default_voice"] == "com.apple.voice.compact.en-US.Samantha"
    assert body["voices"][0]["id"] == "com.apple.voice.compact.en-US.Samantha"


def test_chat_remains_intact_with_tts_live():
    with patch("app.api.routes.handle_message", return_value=("hello back", None)):
        response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json() == {"reply": "hello back", "conversation_id": None}