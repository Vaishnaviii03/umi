from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.elevenlabs_token import ElevenLabsTokenError

client = TestClient(app)


def test_stt_token_unconfigured_returns_503():
    with patch("app.api.routes.token_minter.is_configured", return_value=False):
        response = client.get("/stt/token")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "voice" in detail.lower()
    assert "still works" in detail


def test_stt_token_success_returns_token():
    with patch("app.api.routes.token_minter.is_configured", return_value=True), patch(
        "app.api.routes.token_minter.mint", return_value="realtime-token-abc123"
    ):
        response = client.get("/stt/token")
    assert response.status_code == 200
    assert response.json() == {"token": "realtime-token-abc123"}


def test_stt_token_failure_returns_safe_error():
    with patch("app.api.routes.token_minter.is_configured", return_value=True), patch(
        "app.api.routes.token_minter.mint",
        side_effect=ElevenLabsTokenError("token endpoint returned HTTP 401"),
    ):
        response = client.get("/stt/token")
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "voice" in detail.lower()
    assert "still works" in detail
    # Never leak provider internals / status codes / keys to the client.
    assert "401" not in detail
    assert "sk-" not in detail
    assert "xi-api-key" not in detail