"""Phase 5 — Gmail REST API.

Exposes connect/lifecycle + read operations and an explicit, UI-driven send
path. Sending never happens automatically: the LLM's ``send_email`` tool is
blocked by the confirmation gate, so the only way an email goes out is a
deliberate action here (or the confirmed tool call).
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.services.gmail import (
    GmailError,
    GmailNotConfigured,
    GmailNotConnected,
    gmail_service,
)

logger = logging.getLogger("umi.api.gmail")

router = APIRouter(prefix="/gmail", tags=["gmail"])

_LOCALHOST_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class DraftCreate(BaseModel):
    to: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100_000)


class SendDraft(BaseModel):
    draft_id: str = Field(min_length=1, max_length=200)


class SummarizeRequest(BaseModel):
    ids: list[str] | None = None
    unread_only: bool = True


def _gmail_error(exc: GmailError) -> HTTPException:
    if isinstance(exc, GmailNotConfigured):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, GmailNotConnected):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail="Gmail is unavailable right now.")


def _frontend_origin(request: Request) -> str:
    """Return the requesting frontend's origin so the OAuth callback lands back
    on the window that started it (dev 3000 or desktop 3456)."""
    origin = request.headers.get("origin") or request.headers.get("referer", "")
    if origin:
        origin = origin.split("?")[0].rstrip("/")
        if _LOCALHOST_RE.match(origin) or origin in settings.cors_origins:
            return origin
    return settings.cors_origins[0] if settings.cors_origins else "http://127.0.0.1:3000"


@router.get("/status")
def gmail_status() -> dict:
    """Connected? + which account. Safe to call before any setup."""
    try:
        return gmail_service.status()
    except GmailError:
        return {"connected": False, "email": None}


@router.get("/auth")
def gmail_auth() -> dict:
    try:
        return {"authorization_url": gmail_service.authorize_url()}
    except GmailError as exc:
        raise _gmail_error(exc)


@router.get("/oauth/callback")
def gmail_callback(request: Request, code: str | None = None, error: str | None = None) -> RedirectResponse:
    base = _frontend_origin(request)
    if not code:
        # Google refused (user cancelled / denied). Fall through to a gentle
        # redirect — never an error page.
        reason = "access_denied" if error == "access_denied" else "denied"
        return RedirectResponse(f"{base}/?gmail=error&error={reason}")

    try:
        gmail_service.connect(code)
    except GmailError as exc:
        logger.warning("[gmail] OAuth callback failed: %s", exc)
        return RedirectResponse(f"{base}/?gmail=error&error=auth-failed")
    except Exception as exc:  # noqa: BLE001 — degrade to a redirect, never a raw 500
        # Log only the exception type — the message could echo request data.
        logger.error("[gmail] OAuth callback unexpected error type=%s", type(exc).__name__)
        return RedirectResponse(f"{base}/?gmail=error&error=auth-failed")
    return RedirectResponse(f"{base}/?gmail=connected")


@router.post("/disconnect")
def gmail_disconnect() -> dict:
    gmail_service.disconnect()
    return {"connected": False}


@router.get("/emails")
def gmail_emails(
    unread_only: bool = False,
    limit: int = Query(default=25, ge=1, le=50),
) -> list[dict]:
    try:
        return gmail_service.list_emails(unread_only=unread_only, max_results=limit)
    except GmailError as exc:
        raise _gmail_error(exc)


@router.get("/emails/{message_id}")
def gmail_email(message_id: str) -> dict:
    try:
        return gmail_service.get_email(message_id)
    except GmailError as exc:
        raise _gmail_error(exc)


@router.get("/search")
def gmail_search(q: str = Query(min_length=1), limit: int = Query(default=25, ge=1, le=50)) -> list[dict]:
    try:
        return gmail_service.search(q, max_results=limit)
    except GmailError as exc:
        raise _gmail_error(exc)


@router.get("/drafts")
def gmail_drafts() -> list[dict]:
    try:
        return gmail_service.draft()
    except GmailError as exc:
        raise _gmail_error(exc)


@router.post("/drafts", status_code=201)
def gmail_draft_create(payload: DraftCreate) -> dict:
    try:
        return gmail_service.create_draft(payload.to, payload.subject, payload.body)
    except GmailError as exc:
        raise _gmail_error(exc)


@router.post("/send")
def gmail_send(payload: SendDraft) -> dict:
    """Explicit user-initiated send (the dashboard/panel button)."""
    try:
        return gmail_service.send_draft(payload.draft_id)
    except GmailError as exc:
        raise _gmail_error(exc)


@router.post("/summarize")
def gmail_summarize(payload: SummarizeRequest) -> dict:
    try:
        if payload.ids:
            emails = [gmail_service.get_email(i) for i in payload.ids]
        else:
            emails = gmail_service.list_emails(unread_only=payload.unread_only, max_results=12)
        return {"brief": gmail_service.summarize(emails)}
    except GmailError as exc:
        raise _gmail_error(exc)