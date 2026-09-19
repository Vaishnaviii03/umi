"""Phase 7.5 — Google integration status route tests.

/ google/status is the single source the frontend uses to render capability
chips and the reconnect prompt. It must never leak token material and must
detect that an older (3-scope) token needs reauthorization for the new
Drive/Sheets/Docs/YouTube scopes.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.gmail.api import GOOGLE_SCOPES

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _hermetic_token_store(monkeypatch):
    """Never touch the real ~/.umi/gmail_token.json."""
    import app.services.google_status as gs

    loaded = {"__none__": None}
    monkeypatch.setattr(gs.token_store, "load", lambda: loaded["__none__"])
    state = {"connected": False, "email": None}
    monkeypatch.setattr(gs.gmail_service, "status", lambda: state)
    return loaded, state


def test_status_when_no_token(_hermetic_token_store):
    loaded, state = _hermetic_token_store
    resp = client.get("/google/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["email"] is None
    assert body["granted_scopes"] == []
    assert set(body["required_scopes"]) == set(GOOGLE_SCOPES)
    assert body["needs_reauthorization"] is False


def test_status_fully_granted_no_reauth_needed(_hermetic_token_store):
    loaded, state = _hermetic_token_store
    loaded["__none__"] = {"token": "abc", "scopes": list(GOOGLE_SCOPES)}
    state.update(connected=True, email="boss@example.com")
    body = client.get("/google/status").json()
    assert body["connected"] is True
    assert body["email"] == "boss@example.com"
    assert body["needs_reauthorization"] is False


def test_status_old_token_needs_reauthorization(_hermetic_token_store):
    loaded, state = _hermetic_token_store
    loaded["__none__"] = {
        "token": "abc",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
    }
    state.update(connected=True, email="boss@example.com")
    body = client.get("/google/status").json()
    assert body["connected"] is True
    assert body["needs_reauthorization"] is True


def test_status_never_leaks_token_material(_hermetic_token_store):
    loaded, state = _hermetic_token_store
    loaded["__none__"] = {
        "token": "ya29.super-secret-access",
        "refresh_token": "super-secret-refresh",
        "client_secret": "super-secret-client",
        "scopes": list(GOOGLE_SCOPES),
    }
    state.update(connected=True, email="boss@example.com")
    raw = client.get("/google/status").content.decode()
    assert "ya29" not in raw
    assert "super-secret" not in raw
    assert "refresh_token" not in raw
    assert "client_secret" not in raw