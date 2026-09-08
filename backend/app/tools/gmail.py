"""Phase 5 — Gmail tools.

Reads are permission 1; drafting is a write (permission 2). ``send_email`` is
permission 2 *and* requires explicit user confirmation, so through the normal
LLM loop it is always blocked by the ToolManager gate — the only way an email
actually goes out is the confirmed path (e.g. the Gmail panel's Send button).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.gmail import (
    GmailError,
    GmailNotConfigured,
    GmailNotConnected,
    GmailPermissionMissing,
    GmailReauthRequired,
)
from app.services.gmail.service import gmail_service
from app.tools.base import Tool, ToolContext, ToolExecutionError, ToolResult


def _emails_out(emails: list[dict]) -> list[dict]:
    slim = []
    for e in emails:
        slim.append(
            {
                "id": e["id"],
                "subject": e["subject"],
                "from": e.get("from_email") or e.get("from_header"),
                "date": e.get("date"),
                "unread": e.get("unread"),
                "snippet": (e.get("snippet") or "")[:200],
                "importance_level": e.get("importance_level"),
                "importance_score": e.get("importance_score"),
            }
        )
    return slim


def _check(exc: GmailError):
    if isinstance(exc, GmailNotConfigured):
        raise ToolExecutionError("Gmail isn't configured yet — set GOOGLE_CLIENT_ID/SECRET.")
    if isinstance(exc, GmailNotConnected):
        raise ToolExecutionError("no Google account is connected yet — connect via the Gmail panel.")
    if isinstance(exc, GmailReauthRequired):
        raise ToolExecutionError("your Google authorization needs to be renewed — reconnect via the Gmail panel.")
    if isinstance(exc, GmailPermissionMissing):
        raise ToolExecutionError("Umi doesn't have the required Gmail permission — reconnect Google to grant it.")
    raise ToolExecutionError("Gmail is temporarily unavailable — please try again in a moment.")


class ListEmailsArgs(BaseModel):
    unread_only: bool = False
    limit: int = Field(default=10, ge=1, le=25)


class EmailSlim(BaseModel):
    id: str
    subject: str
    from_: str | None = Field(default=None, alias="from")
    date: str | None
    unread: bool
    snippet: str
    importance_level: str
    importance_score: float


class ListEmailsOutput(BaseModel):
    count: int
    emails: list[EmailSlim]


class ListEmailsTool(Tool):
    name = "list_emails"
    description = (
        "List the user's Gmail inbox (most recent first) with an importance "
        "level per message. `unread_only=True` for just unread mail. Good for "
        "'what came in?' questions before reading anything."
    )
    permission_level = 1
    owner_only = True
    args_model = ListEmailsArgs
    output_model = ListEmailsOutput

    def run(self, ctx: ToolContext, unread_only: bool = False, limit: int = 10, **kwargs) -> ToolResult:
        try:
            emails = gmail_service.list_emails(unread_only=unread_only, max_results=limit)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success({"count": len(emails), "emails": _emails_out(emails)})


class GetEmailArgs(BaseModel):
    message_id: str = Field(min_length=1)


class EmailFull(BaseModel):
    id: str
    subject: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None
    date: str | None
    body: str


class GetEmailOutput(BaseModel):
    email: EmailFull


class GetEmailTool(Tool):
    name = "get_email"
    description = "Read a single email by its id (returned by list_emails/search) including the body text."
    permission_level = 1
    owner_only = True
    args_model = GetEmailArgs
    output_model = GetEmailOutput

    def run(self, ctx: ToolContext, message_id: str, **kwargs) -> ToolResult:
        try:
            email = gmail_service.get_email(message_id)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success(
            {
                "email": {
                    "id": email["id"],
                    "subject": email["subject"],
                    "from": email.get("from_header"),
                    "to": email.get("to"),
                    "date": email.get("date"),
                    "body": (email.get("body") or "")[:10_000],
                }
            }
        )


class SearchEmailsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class SearchEmailsOutput(BaseModel):
    count: int
    emails: list[EmailSlim]


class SearchEmailsTool(Tool):
    name = "search_emails"
    description = (
        "Search Gmail with a Gmail search expression (e.g. 'from:alice' or "
        "'invoice after:2026/08/01'). Returns matching messages with importance."
    )
    permission_level = 1
    owner_only = True
    args_model = SearchEmailsArgs
    output_model = SearchEmailsOutput

    def run(self, ctx: ToolContext, query: str, limit: int = 10, **kwargs) -> ToolResult:
        try:
            emails = gmail_service.search(query, max_results=limit)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success({"count": len(emails), "emails": _emails_out(emails)})


class SummarizeEmailsArgs(BaseModel):
    unread_only: bool = True
    limit: int = Field(default=12, ge=1, le=25)
    focus: str | None = Field(default=None, max_length=200, description="Optional area the user cares about.")


class SummarizeEmailsOutput(BaseModel):
    brief: str


class SummarizeEmailsTool(Tool):
    name = "summarize_emails"
    description = (
        "Summarize the user's inbox (unread by default) into a short, "
        "importance-aware brief. Use when asked 'what's in my inbox?' / 'any "
        "important mail?'. Optionally pass `focus` to bias the brief toward a "
        "specific topic."
    )
    permission_level = 1
    owner_only = True
    args_model = SummarizeEmailsArgs
    output_model = SummarizeEmailsOutput

    def run(self, ctx: ToolContext, unread_only: bool = True, limit: int = 12, focus: str | None = None, **kwargs) -> ToolResult:
        try:
            emails = gmail_service.list_emails(unread_only=unread_only, max_results=limit)
        except GmailError as exc:
            _check(exc)
            raise
        try:
            brief = gmail_service.summarize(emails, statement=focus)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success({"brief": brief})


class ComposeDraftArgs(BaseModel):
    to: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(max_length=100_000)


class ComposeDraftOutput(BaseModel):
    id: str
    to: str
    subject: str


class ComposeDraftTool(Tool):
    name = "compose_draft"
    description = (
        "Create an email draft (does NOT send). Use when the user asks you to "
        "write a reply/email: confirm recipients, then compose_draft, then tell "
        "the user the draft is ready to review. Sending happens separately."
    )
    permission_level = 2
    owner_only = True
    args_model = ComposeDraftArgs
    output_model = ComposeDraftOutput

    def run(self, ctx: ToolContext, to: str, subject: str, body: str = "", **kwargs) -> ToolResult:
        try:
            draft = gmail_service.create_draft(to, subject, body)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success(draft)


class SendEmailArgs(BaseModel):
    draft_id: str = Field(min_length=1, max_length=200)


class SendEmailOutput(BaseModel):
    message_id: str


class SendEmailTool(Tool):
    name = "send_email"
    description = (
        "Send an existing draft. This requires explicit user confirmation — the "
        "ToolManager blocks it automatically until the user approves, so prefer "
        "compose_draft and let the user send from the Gmail panel."
    )
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = SendEmailArgs
    output_model = SendEmailOutput

    def run(self, ctx: ToolContext, draft_id: str, **kwargs) -> ToolResult:
        try:
            sent = gmail_service.send_draft(draft_id)
        except GmailError as exc:
            _check(exc)
            raise
        return ToolResult.success({"message_id": sent.get("message_id")})