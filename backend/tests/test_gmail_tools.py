"""Phase 5 — Gmail tool tests (execution with a stubbed GmailService)."""

import pytest

from app.config import settings
from app.tools import (
    ConfirmationRequired,
    PermissionDenied,
    ToolContext,
    ToolExecutionError,
    tool_manager,
)
import app.tools.gmail as tools_gmail

OWNER = str(settings.owner_id)


def ctx():
    return ToolContext(user_id=OWNER)


SAMPLE = {
    "id": "m1",
    "subject": "URGENT: invoice due today",
    "from_header": "Billing <billing@example.com>",
    "from_email": "billing@example.com",
    "date": "2026-09-08T10:00:00+00:00",
    "unread": True,
    "snippet": "pay by eod",
    "importance_level": "high",
    "importance_score": 0.8,
}


def test_list_emails_wire(monkeypatch):
    monkeypatch.setattr(tools_gmail.gmail_service, "list_emails", lambda **kw: [SAMPLE])
    result = tool_manager.execute_tool("list_emails", {"unread_only": True, "limit": 5}, ctx())
    assert result.status == "success"
    assert result.data["count"] == 1
    assert result.data["emails"][0]["subject"].startswith("URGENT")


def test_get_email_wire(monkeypatch):
    body = "please pay by end of day"
    monkeypatch.setattr(tools_gmail.gmail_service, "get_email", lambda mid: {**SAMPLE, "body": body})
    result = tool_manager.execute_tool("get_email", {"message_id": "m1"}, ctx())
    assert result.status == "success"
    assert body in result.data["email"]["body"]


def test_search_emails_wire(monkeypatch):
    monkeypatch.setattr(tools_gmail.gmail_service, "search", lambda q, max_results=10: [SAMPLE])
    result = tool_manager.execute_tool("search_emails", {"query": "invoice"}, ctx())
    assert result.status == "success"
    assert result.data["count"] == 1


def test_summarize_emails_wire(monkeypatch):
    monkeypatch.setattr(tools_gmail.gmail_service, "list_emails", lambda **kw: [SAMPLE])
    monkeypatch.setattr(tools_gmail.gmail_service, "summarize", lambda emails, statement=None: "You have one urgent invoice.")
    result = tool_manager.execute_tool("summarize_emails", {}, ctx())
    assert result.status == "success"
    assert "urgent" in result.data["brief"]


def test_compose_draft_wire(monkeypatch):
    monkeypatch.setattr(
        tools_gmail.gmail_service, "create_draft", lambda to, subject, body: {"id": "d1", "to": to, "subject": subject}
    )
    result = tool_manager.execute_tool(
        "compose_draft", {"to": "a@b.com", "subject": "Hi", "body": "hello"}, ctx()
    )
    assert result.status == "success"
    assert result.data["id"] == "d1"


def test_send_email_requires_confirmation(monkeypatch):
    sent = []
    monkeypatch.setattr(tools_gmail.gmail_service, "send_draft", lambda did: sent.append(did) or {"message_id": "x"})
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("send_email", {"draft_id": "d1"}, ctx())
    assert sent == []
    # Explicit confirmation allows it.
    confirmed = ToolContext(user_id=OWNER, extra={"confirmed": True})
    result = tool_manager.execute_tool("send_email", {"draft_id": "d1"}, confirmed)
    assert result.status == "success"
    assert sent == ["d1"]


def test_send_email_non_owner_denied(monkeypatch):
    monkeypatch.setattr(tools_gmail.gmail_service, "send_draft", lambda did: {"message_id": "x"})
    with pytest.raises(PermissionDenied):
        tool_manager.execute_tool(
            "send_email", {"draft_id": "d1"}, ToolContext(user_id="someone-else", extra={"confirmed": True})
        )


def test_tools_report_gmail_not_connected(tmp_path, monkeypatch):
    """Gmail tools fail clearly when no account is connected (no DB dependency)."""
    from app.services.gmail.service import gmail_service
    from app.services.gmail.token_store import TokenStore

    monkeypatch.setattr(gmail_service, "store", TokenStore(str(tmp_path / "none.json")))
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("list_emails", {}, ctx())


def _raise(exc):
    def _fn(**kw):
        raise exc

    return _fn


def test_list_emails_maps_reauth_required(monkeypatch):
    """Stale/revoked auth surfaces 'renewed/reconnect', not a generic fallback."""
    from app.services.gmail import GmailReauthRequired

    monkeypatch.setattr(
        tools_gmail.gmail_service,
        "list_emails",
        _raise(GmailReauthRequired("Google authorization needs to be renewed")),
    )
    with pytest.raises(ToolExecutionError) as excinfo:
        tool_manager.execute_tool("list_emails", {}, ctx())
    assert "renewed" in str(excinfo.value)
    assert "reconnect" in str(excinfo.value)


def test_list_emails_maps_permission_missing(monkeypatch):
    """Missing scope surfaces 'permission' + reconnect, not a generic fallback."""
    from app.services.gmail import GmailPermissionMissing

    monkeypatch.setattr(
        tools_gmail.gmail_service,
        "list_emails",
        _raise(GmailPermissionMissing("Umi doesn't have the required Gmail permission")),
    )
    with pytest.raises(ToolExecutionError) as excinfo:
        tool_manager.execute_tool("list_emails", {}, ctx())
    assert "permission" in str(excinfo.value)
    assert "reconnect" in str(excinfo.value)