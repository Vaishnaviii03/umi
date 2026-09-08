"""Phase 5 — Gmail service facade.

The one object routes and tools talk to. Owns the token store, builds the API
client on demand (refreshing expired creds), normalizes Gmail's raw JSON into
stable dicts, applies the importance heuristic, and provides summaries. Tests
inject a fake ``api`` or ``api_factory`` so nothing here needs the network.
"""

from __future__ import annotations

import logging
import secrets
from email.utils import parsedate_to_datetime
from typing import Callable

from app.services.gmail.api import (
    GOOGLE_SCOPES,
    GmailAPI,
    GmailError,
    GmailNotConfigured,
    GmailNotConnected,
    GmailPermissionMissing,
    GmailReauthRequired,
    addresses,
    credentials_from_store,
    decode_body,
    header,
)
from app.services.gmail.importance import scale_email
from app.services.gmail.summaries import build_brief
from app.services.gmail.token_store import TokenStore, token_store

logger = logging.getLogger("umi.gmail")

MAX_BODY_CHARS = 20_000
LIST_BATCH = 25


class GmailService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: GmailAPI | None = None,
        api_factory: Callable[[dict], GmailAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory
        # OAuth PKCE: the code_verifier is generated here (authorize step) and
        # replayed on the callback exchange. Held in memory only — no disk.
        self._code_verifier: str | None = None

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> GmailAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise GmailNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return GmailAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            # Stored token can't be rebuilt (corrupt/partial file) -> treat as
            # not connected instead of leaking a 500 to the caller.
            logger.warning("[gmail] stored token is invalid; reconnect required")
            raise GmailNotConnected("no valid Google credentials stored — reconnect")

    def _save_creds(self, creds) -> None:
        """Persist exactly the fields google-auth needs to rebuild and refresh.

        Stored keys must match what ``Credentials.from_authorized_user_info``
        expects. google-auth stores refresh_token/client_id/client_secret under
        underscore-prefixed attribute names, so scraping ``__dict__`` dropped
        them — the saved token file could then never be rebuilt.
        """
        scopes = creds.scopes
        if isinstance(scopes, str):
            scopes = scopes.split()
        self.store.save(
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(scopes or ()),
                "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
            }
        )

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            profile = self._get_api().profile()
            return {"connected": True, "email": profile.get("emailAddress")}
        except GmailError:
            logger.warning("[gmail] status check failed (token may be invalid)")
            return {"connected": False, "email": None}
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            logger.warning("[gmail] status check failed (token invalid or API unavailable)")
            return {"connected": False, "email": None}

    def authorize_url(self) -> str:
        self._code_verifier = secrets.token_urlsafe(128)
        return GmailAPI().authorization_url(code_verifier=self._code_verifier)

    def connect(self, code: str) -> str:
        creds = GmailAPI().exchange_code(code, code_verifier=self._code_verifier)
        self._code_verifier = None
        self._save_creds(creds)
        email = self.status().get("email")
        logger.info("[gmail] connected account=%s", email)
        return email

    def disconnect(self) -> None:
        self.store.clear()

    # -- mailbox ------------------------------------------------------------- #
    def _connected_email(self) -> str | None:
        profile = self._get_api().profile()
        return profile.get("emailAddress")

    def list_emails(self, query: str = "", unread_only: bool = False, max_results: int = LIST_BATCH) -> list[dict]:
        api = self._get_api()
        q = query
        if unread_only:
            q = f"{q} in:unread" if q else "in:unread"
        raw = api.list_message_metadata(query=q, max_results=max_results)
        thread_counts: dict[str, int] = {}
        for item in raw:
            thread_counts[item.get("threadId", "")] = thread_counts.get(item.get("threadId", ""), 0) + 1
        emails = []
        for item in raw:
            full = api.get_json(item["id"])
            normalized = self.normalize_message(full, thread_length=thread_counts.get(item.get("threadId", ""), 1))
            emails.append(normalized)
        return emails

    def get_email(self, message_id: str) -> dict:
        full = self._get_api().get_json(message_id, fmt="full")
        email = self.normalize_message(full)
        email["body"] = decode_body(full.get("payload") or {})[:MAX_BODY_CHARS]
        email["has_attachment"] = _has_attachment(full.get("payload") or {})
        return email

    def search(self, query: str, max_results: int = LIST_BATCH) -> list[dict]:
        if not query.strip():
            return self.list_emails(max_results=max_results)
        api = self._get_api()
        raw = api.search(query.strip(), max_results=max_results)
        emails = []
        for item in raw:
            full = api.get_json(item["id"])
            emails.append(self.normalize_message(full, thread_length=1))
        return emails

    def draft(self) -> list[dict]:
        api = self._get_api()
        drafts = []
        for item in api.list_drafts():
            try:
                payload = api.get_draft(item["id"], fmt="metadata").get("message", {})
            except GmailError:
                continue
            payload = payload.get("payload") or {}
            drafts.append(
                {
                    "id": item["id"],
                    "to": ",".join(addresses(header(payload, "To"))),
                    "subject": header(payload, "Subject") or "(no subject)",
                    "snippet": (header(payload, "Subject") or "Untitled draft"),
                }
            )
        return drafts

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        api = self._get_api()
        created = api.create_draft(to, subject, body)
        logger.info("[gmail][audit] draft created to=%s subject=%r", to, subject)
        return {"id": created.get("id"), "to": to, "subject": subject}

    def send_draft(self, draft_id: str) -> dict:
        api = self._get_api()
        sent = api.send_draft(draft_id)
        logger.info("[gmail][audit] draft SENT id=%s message=%s", draft_id, sent.get("id"))
        return {"message_id": sent.get("id")}

    # -- analysis ------------------------------------------------------------ #
    def normalize_message(self, raw: dict, *, thread_length: int = 1) -> dict:
        payload = raw.get("payload") or {}
        subject = header(payload, "Subject") or "(no subject)"
        from_header = header(payload, "From") or ""
        label_ids = raw.get("labelIds") or []
        date_raw = header(payload, "Date")
        try:
            date_iso = parsedate_to_datetime(date_raw).isoformat() if date_raw else None
        except (TypeError, ValueError):
            date_iso = None
        email = {
            "id": raw.get("id"),
            "thread_id": raw.get("threadId"),
            "subject": subject,
            "from_header": from_header,
            "from_name": "",
            "from_email": "",
            "to": header(payload, "To"),
            "date": date_iso,
            "snippet": raw.get("snippet", ""),
            "unread": "UNREAD" in label_ids,
            "labels": label_ids,
            "thread_length": thread_length,
        }
        if from_header:
            name, email_addr = _split_from(from_header)
            email["from_name"] = name
            email["from_email"] = email_addr
        importance = scale_email(email)
        email["importance_score"] = importance["score"]
        email["importance_level"] = importance["level"]
        email["importance_reasons"] = importance["reasons"]
        return email

    def summarize(self, emails: list[dict], statement: str | None = None) -> str:
        ordered = sorted(
            emails,
            key=lambda e: e.get("importance_score", 0),
            reverse=True,
        )
        return build_brief(ordered, statement=statement)


def _split_from(header_value: str) -> tuple[str, str]:
    addresses_list = addresses(header_value)
    email_addr = addresses_list[0] if addresses_list else ""
    name = header_value
    if "<" in header_value and ">" in header_value:
        name = header_value.split("<")[0].strip().strip('"')
    return name or email_addr, email_addr


def _has_attachment(payload: dict) -> bool:
    if any(p.get("filename") for p in payload.get("parts", [])):
        return True
    ctype = payload.get("mimeType", "")
    return "attachment" in ctype or "multipart/mixed" == ctype or "application/" in ctype and len(payload.get("parts", [])) > 0


gmail_service = GmailService()

__all__ = [
    "GOOGLE_SCOPES",
    "GmailError",
    "GmailNotConfigured",
    "GmailNotConnected",
    "GmailPermissionMissing",
    "GmailReauthRequired",
    "GmailService",
    "gmail_service",
]