"""Phase 6 — Calendar tool tests (execution with a stubbed CalendarService)."""

import pytest

from app.config import settings
from app.tools import (
    ConfirmationRequired,
    ToolContext,
    ToolExecutionError,
    tool_manager,
)
import app.tools.calendar as tools_calendar

OWNER = str(settings.owner_id)


def ctx():
    return ToolContext(user_id=OWNER)


SAMPLE = {
    "id": "e1",
    "summary": "Physics study",
    "start": "2026-09-09T14:00:00+05:30",
    "end": "2026-09-09T15:00:00+05:30",
    "location": "Home",
    "attendees": [],
    "link": None,
}


def test_list_events_wire(monkeypatch):
    monkeypatch.setattr(tools_calendar.calendar_service, "list_events", lambda **kw: [SAMPLE])
    result = tool_manager.execute_tool("list_events", {"days": 3}, ctx())
    assert result.status == "success"
    assert result.data["count"] == 1
    assert result.data["events"][0]["summary"].startswith("Physics")


def test_summarize_calendar_wire(monkeypatch):
    monkeypatch.setattr(tools_calendar.calendar_service, "list_events", lambda **kw: [SAMPLE])
    monkeypatch.setattr(tools_calendar.calendar_service, "summarize", lambda events: "One event: Physics study.")
    result = tool_manager.execute_tool("summarize_calendar", {"days": 3}, ctx())
    assert result.status == "success"
    assert "Physics study" in result.data["brief"]


def test_create_event_wire(monkeypatch):
    monkeypatch.setattr(
        tools_calendar.calendar_service,
        "create_event",
        lambda **kw: {"id": "e-new", "summary": kw["summary"], "start": kw["start"]},
    )
    result = tool_manager.execute_tool(
        "create_event", {"summary": "Team sync", "start": "2026-09-09T14:00:00", "end": "2026-09-09T15:00:00"}, ctx()
    )
    assert result.status == "success"
    assert result.data["id"] == "e-new"


def test_update_event_wire(monkeypatch):
    monkeypatch.setattr(
        tools_calendar.calendar_service,
        "update_event",
        lambda event_id, **kw: {"id": event_id, "summary": kw.get("summary", "s"), "start": "2026-09-09T10:00:00"},
    )
    result = tool_manager.execute_tool("update_event", {"event_id": "e1", "location": "Office"}, ctx())
    assert result.status == "success"


def test_delete_event_requires_confirmation(monkeypatch):
    monkeypatch.setattr(tools_calendar.calendar_service, "delete_event", lambda event_id: {"id": event_id})
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("delete_event", {"event_id": "e1"}, ctx())


def test_not_connected_error_maps(monkeypatch):
    from app.services.calendar import CalendarNotConnected

    def _raise(**kw):
        raise CalendarNotConnected("no Google account connected yet")

    monkeypatch.setattr(tools_calendar.calendar_service, "list_events", _raise)
    with pytest.raises(ToolExecutionError, match="connect"):
        tool_manager.execute_tool("list_events", {}, ctx())