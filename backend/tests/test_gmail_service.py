"""Phase 5 — Gmail service + importance tests (FakeAPI, no network)."""

from app.services.gmail.api import GmailNotConnected, credentials_from_store
from app.services.gmail.importance import scale_email
from app.services.gmail.service import GmailService
from app.services.gmail.token_store import TokenStore

import pytest


def _raw_message(message_id="m1", subject="URGENT: invoice due today", labels=("UNREAD",), thread_id="t1"):
    return {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": list(labels),
        "snippet": "please pay by end of day",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Billing <billing@example.com>"},
                {"name": "To", "value": "boss@example.com"},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Tue, 08 Sep 2026 10:00:00 +0000"},
            ],
            "body": {"data": "cGxlYXNlIHBheSBieSBlbmQgb2YgZGF5"},  # base64 of plain text
        },
    }


class FakeAPI:
    def __init__(self):
        self.profile_email = "boss@example.com"
        self.sent_drafts = []

    def profile(self):
        return {"emailAddress": self.profile_email}

    def list_message_metadata(self, query="", max_results=25):
        items = [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]
        return items[:max_results]

    def get_json(self, message_id, fmt="metadata"):
        return _raw_message(message_id)

    def search(self, query, max_results=25):
        return self.list_message_metadata(query, max_results)

    def list_drafts(self, max_results=50):
        return [{"id": "d1"}]

    def get_draft(self, draft_id, fmt="metadata"):
        return {
            "message": {
                "payload": {
                    "headers": [
                        {"name": "To", "value": "alice@example.com"},
                        {"name": "Subject", "value": "Re: hello"},
                    ]
                }
            }
        }

    def create_draft(self, to, subject, body):
        return {"id": "new-draft", "to": to, "subject": subject}

    def send_draft(self, draft_id):
        self.sent_drafts.append(draft_id)
        return {"id": "sent-123"}


@pytest.fixture()
def service(tmp_path):
    store = TokenStore(str(tmp_path / "token.json"))
    return GmailService(store=store, api=FakeAPI())


# --------------------------------------------------------------------------- #
# Importance heuristic
# --------------------------------------------------------------------------- #
def test_importance_high_for_unread_urgent():
    result = scale_email({"unread": True, "subject": "URGENT: invoice due today", "thread_length": 1, "has_attachment": False})
    assert result["level"] == "high"
    assert result["score"] >= 0.7


def test_importance_low_for_quiet_read():
    result = scale_email({"unread": False, "subject": "newsletter", "thread_length": 1, "has_attachment": False})
    assert result["level"] == "low"


def test_importance_reasons_present():
    result = scale_email({"unread": True, "subject": "meeting", "thread_length": 6, "has_attachment": False})
    assert "unread" in result["reasons"]
    assert "long thread" in result["reasons"]


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def test_normalize_message_parses_headers(service):
    email = service.normalize_message(_raw_message())
    assert email["subject"] == "URGENT: invoice due today"
    assert email["from_name"] == "Billing"
    assert email["from_email"] == "billing@example.com"
    assert email["unread"] is True
    assert email["importance_level"] == "high"


def test_get_email_includes_decoded_body(service):
    email = service.get_email("m1")
    assert "pay by end of day" in email["body"]


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def test_list_emails_normalizes_and_returns(service):
    emails = service.list_emails(max_results=25)
    assert [e["id"] for e in emails] == ["m1", "m2"]


def test_search_returns_emails(service):
    emails = service.search("invoice", max_results=10)
    assert len(emails) == 2


def test_drafts_normalize(service):
    drafts = service.draft()
    assert drafts[0]["id"] == "d1"
    assert drafts[0]["to"] == "alice@example.com"


def test_create_draft(service):
    draft = service.create_draft("a@example.com", "Hi", "body")
    assert draft["id"] == "new-draft"


def test_send_draft_audits_and_returns(service):
    result = service.send_draft("d1")
    assert result["message_id"] == "sent-123"
    assert service._api.sent_drafts == ["d1"]


def test_status_disconnected_when_no_token(tmp_path):
    service = GmailService(store=TokenStore(str(tmp_path / "absent.json")))
    assert service.status() == {"connected": False, "email": None}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
def test_list_emails_requires_connection(tmp_path):
    service = GmailService(store=TokenStore(str(tmp_path / "no.json")))
    with pytest.raises(GmailNotConnected):
        service.list_emails()

# --------------------------------------------------------------------------- #
# OAuth PKCE flow reuse
# --------------------------------------------------------------------------- #
class _FakeFlow:
    def __init__(self):
        self.redirect_uri = None
        self.token_exchanges = []
        self.credentials = "fake-creds"

    def authorization_url(self, **kwargs):
        return f"https://accounts.google.com/oauth2/auth?test=1", "state-1"

    def fetch_token(self, code=None, **kwargs):
        self.token_exchanges.append(code)
        return {}


def test_authorization_url_then_exchange_reuses_same_flow(monkeypatch):
    """The PKCE code_verifier lives on the Flow, so the callback must reuse it.
    Regression for 'Missing code verifier' InvalidGrantError."""
    from app.services.gmail import api as gmail_api

    created = []
    monkeypatch.setattr(
        gmail_api.Flow,
        "from_client_config",
        classmethod(lambda cls, *a, **k: created.append(1) or _FakeFlow()),
    )
    g = gmail_api.GmailAPI()
    url = g.authorization_url()
    assert "accounts.google.com" in url
    creds = g.exchange_code("auth-code")
    assert creds == "fake-creds"
    assert created == [1], "exactly one Flow created — the verifier must be reused"
    assert g._flow is None, "flow should be consumed after exchange"


def test_oauth_verifier_carried_across_instances(monkeypatch, tmp_path):
    """authorize_url() and connect() run on separate GmailAPI instances; the
    code_verifier must still reach the token exchange (stateless PKCE)."""
    from app.services.gmail import api as gmail_api

    seen = []

    class _RecordingFlow(_FakeFlow):
        def __init__(self):
            super().__init__()
            self._verifier = None
            self.credentials = type(
                "Creds",
                (),
                {
                    "token": "x",
                    "refresh_token": "y",
                    "client_id": "cid",
                    "client_secret": "cs",
                    "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
                    "expiry": None,
                },
            )()

        @property
        def code_verifier(self):
            return self._verifier

        @code_verifier.setter
        def code_verifier(self, value):
            self._verifier = value
            seen.append(value)

    monkeypatch.setattr(
        gmail_api.Flow,
        "from_client_config",
        classmethod(lambda cls, *a, **k: _RecordingFlow()),
    )
    service = GmailService(store=TokenStore(str(tmp_path / "tok.json")))
    monkeypatch.setattr(GmailService, "status", lambda self: {"connected": True, "email": "a@b.com"})
    service.authorize_url()
    assert len(seen) == 1, "authorize generated one code_verifier"
    service.connect("auth-code")
    assert seen[0] == seen[-1], "token exchange replayed the same code_verifier"
    assert service._code_verifier is None, "verifier cleared after exchange"


def test_save_creds_serializes_datetime_expiry(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    service = GmailService(store=TokenStore(str(tmp_path / "tok.json")))

    class _Creds:
        def __init__(self):
            self.token = "at"
            self.refresh_token = "rt"
            self.client_id = "cid"
            self.client_secret = "cs"
            self.scopes = ["gmail.modify"]
            self.expiry = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

    service._save_creds(_Creds())
    blob = service.store.load()
    assert blob["expiry"] == "2026-09-08T12:00:00+00:00"
    assert blob["token"] == "at"


# --------------------------------------------------------------------------- #
# Regressions: round-trip persistence of real google Credentials
# --------------------------------------------------------------------------- #
def test_roundtrip_saved_credentials_rebuild(tmp_path):
    """Root cause: _save_creds used to drop refresh_token/client_id/client_secret
    (google-auth stores them underscore-prefixed), so the token file could not
    be rebuilt — the next status() call raised ValueError -> HTTP 500."""
    from datetime import datetime, timedelta, timezone

    from google.oauth2.credentials import Credentials

    store = TokenStore(str(tmp_path / "tok.json"))
    service = GmailService(store=store)
    creds = Credentials(
        token="access-token",
        refresh_token="refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="cid",
        client_secret="cs",
        scopes=["https://www.googleapis.com/auth/gmail.modify"],
        expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service._save_creds(creds)

    blob = store.load()
    assert blob["refresh_token"] == "refresh-token"
    assert blob["client_id"] == "cid"
    assert blob["client_secret"] == "cs"
    assert blob["expiry"]

    rebuilt = credentials_from_store(blob)
    assert rebuilt.refresh_token == "refresh-token"
    assert rebuilt.client_id == "cid"
    assert rebuilt.client_secret == "cs"


def test_status_degrades_on_corrupt_token(tmp_path):
    """A token file missing required fields must report disconnected, not 500."""
    store = TokenStore(str(tmp_path / "tok.json"))
    store.save({"token": "x"})  # no client_id/client_secret/refresh_token
    service = GmailService(store=store)
    assert service.status() == {"connected": False, "email": None}
