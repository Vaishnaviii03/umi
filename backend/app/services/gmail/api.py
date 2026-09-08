"""Phase 5 — Gmail API boundary.

A thin wrapper around the Gmail REST client. Everything above this layer
(service, tools, routes) works against the methods declared here, so tests can
inject a fake object instead of hitting Google. Secrets and refresh handling
stay in this module; callers only ever see normalized dicts or GmailError.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import re

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.errors import HttpError

from app.config import settings

logger = logging.getLogger("umi.gmail")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/youtube",
]
_DISCOVERY_CACHE_DISABLED = False


class GmailError(Exception):
    """Base class — message is always safe to show the user."""


class GmailNotConfigured(GmailError):
    pass


class GmailNotConnected(GmailError):
    pass


class GmailReauthRequired(GmailError):
    """Google auth is stale, expired, or revoked — the user must reconnect."""


class GmailPermissionMissing(GmailError):
    """The token lacks the scope an operation needs — reconnect to grant it."""


def credentials_from_store(token: dict) -> Credentials:
    """Build a refreshable Credentials object from stored token info.

    The stored grant dictates the refresh scope. Forcing the project-wide
    GOOGLE_SCOPES list here strands any token whose consent predates it: a
    refresh token can never gain scopes beyond its original grant, so Google
    rejects the refresh with ``invalid_scope`` and the token is unusable.
    Rebuilding with the token's own scopes refreshes cleanly, so every
    service the user already consented to keeps working; services beyond the
    grant surface a reconnect prompt instead of failing.
    """
    creds = Credentials.from_authorized_user_info(token)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            status = getattr(exc, "status_code", None)
            logger.warning("[gmail] token refresh failed (status=%s) — reauthorization required", status)
            raise GmailReauthRequired(
                "Google authorization needs to be renewed — reconnect your Google account."
            ) from exc
    return creds


def _map_http_error(exc: HttpError) -> GmailError:
    """Translate a Gmail REST HttpError into a safe, user-facing GmailError."""
    status = getattr(exc, "status_code", None) or 0
    reason = ""
    message = ""
    try:
        err = (json.loads(exc.content.decode("utf-8", errors="replace")) or {}).get("error") or {}
    except (ValueError, AttributeError):
        err = {}
    reason = (err.get("reason") or "").lower()
    message = err.get("message") or ""
    for item in err.get("errors") or []:
        if isinstance(item, dict):
            reason = item.get("reason") or reason
            message = item.get("message") or message
    if status == 401 or reason in ("invalid_grant", "unauthorized"):
        return GmailReauthRequired("Google authorization needs to be renewed — reconnect your Google account.")
    if status == 403 and reason in ("insufficientpermissions", "autherror", "forbidden"):
        return GmailPermissionMissing("Umi doesn't have the required Gmail permission — reconnect Google to grant it.")
    if status == 403 and (
        reason == "accessnotconfigured"
        or "has not been used" in message.lower()
        or "has not been enabled" in message.lower()
    ):
        return GmailError("Gmail API is not enabled for the Google project — enable it in Cloud Console, then reconnect.")
    if status == 429:
        return GmailError("Gmail is temporarily unavailable right now — try again shortly.")
    return GmailReauthRequired("Google denied Gmail access — reconnect your Google account if needed.")


def _gmail_http_errors(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except GmailError:
            raise
        except HttpError as exc:
            raise _map_http_error(exc) from exc

    return wrapper


def _client_config() -> dict:
    if not settings.gmail_enabled:
        raise GmailNotConfigured("Gmail isn't configured yet — set GOOGLE_CLIENT_ID/SECRET.")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


class GmailAPI:
    """Handles OAuth flow, credentials refresh, and Gmail service calls."""

    def __init__(self, *, credentials: Credentials | None = None, service=None) -> None:
        self._creds = credentials
        self._service = service  # injectable for tests
        # The OAuth Flow holds the PKCE code_verifier, which the token exchange
        # must reuse. We keep it on the instance between authorization_url()
        # and exchange_code(). Fine for this single-user localhost app.
        self._flow: Flow | None = None

    # -- OAuth --------------------------------------------------------------- #
    def authorization_url(self, code_verifier: str | None = None) -> str:
        flow = Flow.from_client_config(_client_config(), scopes=GOOGLE_SCOPES)
        flow.redirect_uri = settings.google_redirect_uri
        if code_verifier is not None:
            flow.code_verifier = code_verifier
        url, _state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        self._flow = flow
        return url

    def exchange_code(self, code: str, *, code_verifier: str | None = None) -> Credentials:
        flow = self._flow or Flow.from_client_config(_client_config(), scopes=GOOGLE_SCOPES)
        self._flow = None
        flow.redirect_uri = settings.google_redirect_uri
        if code_verifier is not None:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        return flow.credentials

    # -- Service ------------------------------------------------------------- #
    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise GmailNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("gmail", "v1", credentials=self._creds, cache_discovery=False)

    @_gmail_http_errors
    def profile(self) -> dict:
        return self._svc().users().getProfile(userId="me").execute()

    @_gmail_http_errors
    def list_message_metadata(self, query: str = "", max_results: int = 25) -> list[dict]:
        response = (
            self._svc()
            .users()
            .messages()
            .list(userId="me", q=query or None, maxResults=max_results)
            .execute()
        )
        return response.get("messages", [])

    @_gmail_http_errors
    def get_json(self, message_id: str, fmt: str = "metadata") -> dict:
        return (
            self._svc()
            .users()
            .messages()
            .get(userId="me", id=message_id, format=fmt, metadataHeaders=["From", "To", "Subject", "Date", "Cc", "Bcc"])
            .execute()
        )

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        return self.list_message_metadata(query=query, max_results=max_results)

    @_gmail_http_errors
    def create_draft(self, to: str, subject: str, body: str) -> dict:
        raw = _encode_message(to, subject, body)
        return (
            self._svc()
            .users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )

    @_gmail_http_errors
    def list_drafts(self, max_results: int = 50) -> list[dict]:
        response = self._svc().users().drafts().list(userId="me", maxResults=max_results).execute()
        return response.get("drafts", [])

    @_gmail_http_errors
    def get_draft(self, draft_id: str, fmt: str = "metadata") -> dict:
        return self._svc().users().drafts().get(userId="me", id=draft_id, format=fmt).execute()

    @_gmail_http_errors
    def send_draft(self, draft_id: str) -> dict:
        return self._svc().users().drafts().send(userId="me", body={"id": draft_id}).execute()


def decode_body(payload: dict) -> str:
    """Best-effort plain-text extraction from a message payload (handles
    multipart nesting and base64url-encoded bytes)."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _b64(payload["body"]["data"])
    for part in payload.get("parts", []):
        text = decode_body(part)
        if text:
            return text
    return ""


def header(payload: dict, name: str) -> str | None:
    for h in payload.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def addresses(value: str | None) -> list[str]:
    """Extract bare emails from a 'Name <a@b.c>' style header value."""
    if not value:
        return []
    match = re.search(r"<([^>]+)>", value)
    if match:
        return [match.group(1)]
    return [value.strip()]


def _b64(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")


def _encode_message(to: str, subject: str, body: str) -> str:
    import email.message

    msg = email.message.EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()