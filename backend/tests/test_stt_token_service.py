from datetime import datetime

import httpx
import pytest

from app.services.elevenlabs_token import ElevenLabsTokenError, ElevenLabsTokenMinter, SINGLE_USE_TOKEN_URL
from app.services.local_time import local_time_description


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = repr(payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def fake_client():
    resp = _FakeResponse(200, {"token": "realtime-token-abc123"})
    http = httpx.Client()
    http.post = lambda url, headers=None, **kwargs: resp  # type: ignore[method-assign]
    return http


def test_mint_returns_token(fake_client):
    minter = ElevenLabsTokenMinter(api_key="sk-test", client=fake_client)
    assert minter.mint() == "realtime-token-abc123"


def test_mint_sends_key_to_single_use_endpoint(fake_client):
    captured = {}

    def fake_post(url, headers=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResponse(200, {"token": "t"})

    fake_client.post = fake_post  # type: ignore[method-assign]
    minter = ElevenLabsTokenMinter(api_key="sk-super-secret", client=fake_client)
    minter.mint()
    assert captured["url"] == SINGLE_USE_TOKEN_URL
    assert captured["headers"]["xi-api-key"] == "sk-super-secret"


def test_mint_without_key_raises(fake_client):
    minter = ElevenLabsTokenMinter(api_key="", client=fake_client)
    assert not minter.is_configured()
    with pytest.raises(ElevenLabsTokenError):
        minter.mint()


def test_mint_http_failure_raises(fake_client):
    fake_client.post = lambda url, headers=None, **kwargs: _FakeResponse(401, {})  # type: ignore[method-assign]
    minter = ElevenLabsTokenMinter(api_key="sk-test", client=fake_client)
    with pytest.raises(ElevenLabsTokenError):
        minter.mint()


def test_local_time_description_is_nonempty_and_dated():
    value = local_time_description()
    assert isinstance(value, str)
    assert len(value) > 8
    assert str(datetime.now().year) in value
    assert "at" in value