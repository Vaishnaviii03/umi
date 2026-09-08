"""Phase 5 — Gmail REST API route tests (no real Google calls)."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.api.gmail import router
from app.main import app
from app.services.gmail import GmailNotConfigured, GmailNotConnected, gmail_service
from app.services.gmail.service import GmailService
from app.services.gmail.token_store import TokenStore

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_token_store(tmp_path, monkeypatch):
    """Every route test runs against an empty, throwaway token store — never
    the developer's real ~/.umi/gmail_token.json."""
    store = TokenStore(str(tmp_path / "gmail_test.json"))
    monkeypatch.setattr(gmail_service, "store", store)
    return store


def test_status_disconnected_without_creds():
    """Without a stored token, /gmail/status returns connected=False (safe no-op)."""
    resp = client.get("/gmail/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


def test_auth_endpoint_503_when_not_configured(monkeypatch):
    """/gmail/auth maps GmailNotConfigured to a 503 — env-independent test."""

    class _Unconfigured:
        def authorize_url(self):
            raise GmailNotConfigured("Gmail is not configured yet")

    monkeypatch.setattr("app.api.gmail.gmail_service", _Unconfigured())
    resp = client.get("/gmail/auth")
    assert resp.status_code == 503
    assert "configured" in resp.json()["detail"].lower()


def test_emails_401_when_not_connected():
    resp = client.get("/gmail/emails")
    assert resp.status_code == 401


def test_search_401_when_not_connected():
    resp = client.get("/gmail/search", params={"q": "test"})
    assert resp.status_code == 401


def test_send_401_when_not_connected():
    resp = client.post("/gmail/send", json={"draft_id": "x"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Monkeypatched success paths
# --------------------------------------------------------------------------- #
def test_list_emails_success(monkeypatch):
    fake_email = {
        "id": "m1",
        "subject": "Hello",
        "from_header": "A <a@b.com>",
        "from_email": "a@b.com",
        "from_name": "A",
        "date": "2026-09-08T10:00:00+00:00",
        "unread": True,
        "snippet": "hi",
        "importance_level": "medium",
        "importance_score": 0.4,
        "thread_length": 1,
        "labels": [],
    }
    monkeypatch.setattr(gmail_service, "list_emails", lambda **kw: [fake_email])
    resp = client.get("/gmail/emails")
    assert resp.status_code == 200
    assert resp.json()[0]["subject"] == "Hello"


def test_search_success(monkeypatch):
    monkeypatch.setattr(gmail_service, "search", lambda q, max_results=25: [{"id": "m1", "subject": "Hi"}])
    resp = client.get("/gmail/search", params={"q": "invoice"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_drafts_success(monkeypatch):
    monkeypatch.setattr(gmail_service, "draft", lambda: [{"id": "d1", "to": "a@b.com", "subject": "Hi", "snippet": "draft"}])
    resp = client.get("/gmail/drafts")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "d1"


def test_draft_create_success(monkeypatch):
    monkeypatch.setattr(gmail_service, "create_draft", lambda to, subject, body: {"id": "d2", "to": to, "subject": subject})
    resp = client.post("/gmail/drafts", json={"to": "x@y.com", "subject": "Yo", "body": "hi"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "d2"


def test_send_success(monkeypatch):
    monkeypatch.setattr(gmail_service, "send_draft", lambda did: {"message_id": "sent-99"})
    resp = client.post("/gmail/send", json={"draft_id": "d1"})
    assert resp.status_code == 200
    assert resp.json()["message_id"] == "sent-99"


def test_summarize_success(monkeypatch):
    monkeypatch.setattr(gmail_service, "list_emails", lambda **kw: [{"id": "m1", "importance_score": 0.8, "importance_level": "high"}])
    monkeypatch.setattr(gmail_service, "summarize", lambda emails, statement=None: "You have 1 urgent email.")
    resp = client.post("/gmail/summarize", json={"unread_only": True})
    assert resp.status_code == 200
    assert "urgent" in resp.json()["brief"]


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_draft_create_rejects_empty_fields():
    resp = client.post("/gmail/drafts", json={"to": "", "subject": "X"})
    assert resp.status_code == 422


def test_send_requires_draft_id():
    resp = client.post("/gmail/send", json={"draft_id": ""})
    assert resp.status_code == 422

def test_oauth_scopes_cover_gmail_and_calendar():
    """The single OAuth consent must grant access Umi needs for both Gmail and
    Calendar (PRD 9.5/9.6): gmail read+send, calendar read+event write."""
    from app.services.gmail.api import GOOGLE_SCOPES

    joined = " ".join(GOOGLE_SCOPES)
    assert "/auth/gmail.modify" in joined
    assert "/auth/calendar.readonly" in joined
    assert "/auth/calendar.events" in joined


def test_callback_never_returns_500(monkeypatch):
    """The OAuth callback must degrade to a user-facing redirect even on
    unexpected errors — never a raw 'Internal Server Error'."""

    def _boom(code):
        raise ValueError("simulated unexpected failure")

    monkeypatch.setattr("app.api.gmail.gmail_service.connect", _boom)
    resp = client.get(
        "/gmail/oauth/callback",
        params={"code": "some-auth-code"},
        headers={"Origin": "http://localhost:3000"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303, 307)
    assert resp.is_redirect
    location = resp.headers["location"]
    assert location.startswith("http://localhost:3000/")
    assert "gmail=error" in location
    assert "error=auth-failed" in location


# --------------------------------------------------------------------------- #
# Credential refresh must honor the stored grant (regression: invalid_scope)
# --------------------------------------------------------------------------- #
def test_credentials_from_store_keeps_stored_grant_scope(monkeypatch):
    """Root cause: forcing GOOGLE_SCOPES onto a token consented for fewer scopes
    made every refresh fail with invalid_scope, stranding all Google services.
    The stored grant must stay authoritative."""
    from app.services.gmail.api import credentials_from_store

    blob = {
        "token": "at",
        "refresh_token": "rt",
        "client_id": "cid",
        "client_secret": "cs",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        "expiry": "2099-01-01T00:00:00",
    }
    creds = credentials_from_store(blob)
    assert creds.scopes == [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.readonly",
    ], "refresh scope must come from the stored token, not GOOGLE_SCOPES"


def test_credentials_from_store_raises_reauth_on_refresh_failure(monkeypatch):
    """A failed refresh must raise the reconnect-facing error, never a raw
    google RefreshError leaking past the tool layer."""
    from google.auth.exceptions import RefreshError

    import app.services.gmail.api as api_mod
    from app.services.gmail import GmailReauthRequired

    blob = {
        "token": "at",
        "refresh_token": "rt",
        "client_id": "cid",
        "client_secret": "cs",
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        "expiry": "2020-01-01T00:00:00",
    }

    def _boom(*args, **kwargs):
        raise RefreshError("invalid_scope: Bad Request")

    monkeypatch.setattr(api_mod.Credentials, "refresh", _boom)
    with pytest.raises(GmailReauthRequired):
        api_mod.credentials_from_store(blob)


class _StubResp:
    def __init__(self, status, reason=""):
        self.status = status
        self.reason = reason


def _svc_raising(status, err_body):
    from googleapiclient.errors import HttpError

    class _Chain:
        def users(self):
            return self

        def getProfile(self, userId):
            return self

        def execute(self):
            raise HttpError(_StubResp(status), json.dumps(err_body).encode())

    return _Chain()


def test_gmail_http_401_maps_to_reauth():
    from app.services.gmail import GmailReauthRequired
    from app.services.gmail.api import GmailAPI

    api = GmailAPI(service=_svc_raising(401, {"error": {"reason": "invalid_grant", "message": "Token expired"}}))
    with pytest.raises(GmailReauthRequired):
        api.profile()


def test_gmail_http_403_insufficient_scope_maps_to_permission():
    from app.services.gmail import GmailPermissionMissing
    from app.services.gmail.api import GmailAPI

    api = GmailAPI(
        service=_svc_raising(403, {"error": {"reason": "insufficientPermissions", "message": "Insufficient Permission"}})
    )
    with pytest.raises(GmailPermissionMissing):
        api.profile()
