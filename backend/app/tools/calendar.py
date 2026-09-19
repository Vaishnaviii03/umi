"""Phase 6 — Calendar tools.

Reads are permission 1. Creating/updating events is permission 2 (visible
write). Deleting an event is permission 2 *and* requires explicit user
confirmation, so through the normal LLM loop it is gated exactly like Gmail's
send — a calendar entry can't be removed silently.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.services.calendar import CalendarError, CalendarNotConnected, calendar_service
from app.tools.base import Tool, ToolContext, ToolExecutionError, ToolResult


def _window(days: int) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.isoformat(), (now + timedelta(days=days)).isoformat()


def _check(exc: CalendarError):
    if isinstance(exc, CalendarNotConnected):
        raise ToolExecutionError("no Google account is connected yet — connect via the Gmail panel.")
    raise ToolExecutionError("Calendar is unavailable right now.")


def _events_out(events: list[dict]) -> list[dict]:
    return [
        {"id": e["id"], "summary": e["summary"], "start": e.get("start"), "end": e.get("end"),
         "location": e.get("location"), "attendees": e.get("attendees"), "link": e.get("link")}
        for e in events
    ]


class ListEventsArgs(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    query: str | None = Field(default=None, max_length=200)


class CalendarEventSlim(BaseModel):
    id: str
    summary: str
    start: str | None
    end: str | None
    location: str
    attendees: list[str] = []


class ListEventsOutput(BaseModel):
    count: int
    events: list[CalendarEventSlim]


class ListEventsTool(Tool):
    name = "list_events"
    description = (
        "List the user's upcoming Google Calendar events (default: next 7 days). "
        "Answers 'what's on my calendar?' / 'what's happening tomorrow?'. "
        "Optionally pass `days` to widen the window and `query` to filter "
        "(e.g. 'meeting')."
    )
    permission_level = 1
    owner_only = True
    args_model = ListEventsArgs
    output_model = ListEventsOutput

    def run(self, ctx: ToolContext, days: int = 7, query: str | None = None, **kwargs) -> ToolResult:
        try:
            tmin, tmax = _window(days)
            events = calendar_service.list_events(time_min=tmin, time_max=tmax, q=query, max_results=25)
        except CalendarError as exc:
            _check(exc)
            raise
        return ToolResult.success({"count": len(events), "events": _events_out(events)})


class SummarizeCalendarArgs(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class SummarizeCalendarOutput(BaseModel):
    brief: str


class SummarizeCalendarTool(Tool):
    name = "summarize_calendar"
    description = (
        "Summarize the user's upcoming calendar events into a short agenda. "
        "Use for 'can you sum up my week?' style requests."
    )
    permission_level = 1
    owner_only = True
    args_model = SummarizeCalendarArgs
    output_model = SummarizeCalendarOutput

    def run(self, ctx: ToolContext, days: int = 7, **kwargs) -> ToolResult:
        try:
            tmin, tmax = _window(days)
            events = calendar_service.list_events(time_min=tmin, time_max=tmax, max_results=25)
        except CalendarError as exc:
            _check(exc)
            raise
        return ToolResult.success({"brief": calendar_service.summarize(events)})


class CreateEventArgs(BaseModel):
    summary: str = Field(min_length=1, max_length=300)
    start: str = Field(min_length=1, max_length=40, description="ISO datetime, e.g. 2026-09-09T14:00:00")
    end: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=20_000)
    location: str = Field(default="", max_length=500)


class CreateEventOutput(BaseModel):
    id: str
    summary: str
    start: str | None


class CreateEventTool(Tool):
    name = "create_event"
    description = (
        "Add an event to the user's Google Calendar. Use local naive ISO times "
        "('2026-09-09T14:00:00' / '2026-09-09T16:00:00'); for all-day events pass "
        "'YYYY-MM-DD'. Confirm the details with the user before creating."
    )
    permission_level = 2
    owner_only = True
    args_model = CreateEventArgs
    output_model = CreateEventOutput

    def run(
        self,
        ctx: ToolContext,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        **kwargs,
    ) -> ToolResult:
        try:
            event = calendar_service.create_event(summary=summary, start=start, end=end, description=description, location=location)
        except CalendarError as exc:
            _check(exc)
            raise
        return ToolResult.success({"id": event["id"], "summary": event["summary"], "start": event.get("start")})


class UpdateEventArgs(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    location: str | None = Field(default=None, max_length=500)
    start: str | None = Field(default=None, min_length=1, max_length=40)
    end: str | None = Field(default=None, min_length=1, max_length=40)


class UpdateEventOutput(BaseModel):
    id: str
    summary: str
    start: str | None


class UpdateEventTool(Tool):
    name = "update_event"
    description = "Change or reschedule an existing calendar event. Only provided fields are changed."
    permission_level = 2
    owner_only = True
    args_model = UpdateEventArgs
    output_model = UpdateEventOutput

    def run(self, ctx: ToolContext, event_id: str, **kwargs) -> ToolResult:
        changes = {k: v for k, v in kwargs.items() if v is not None}
        try:
            event = calendar_service.update_event(event_id, **changes)
        except CalendarError as exc:
            _check(exc)
            raise
        return ToolResult.success({"id": event["id"], "summary": event["summary"], "start": event.get("start")})


class DeleteEventArgs(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)


class DeleteEventOutput(BaseModel):
    id: str


class DeleteEventTool(Tool):
    name = "delete_event"
    description = (
        "Remove a calendar event. Requires explicit user confirmation — the "
        "ToolManager blocks this automatically until the user approves."
    )
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = DeleteEventArgs
    output_model = DeleteEventOutput

    def run(self, ctx: ToolContext, event_id: str, **kwargs) -> ToolResult:
        try:
            deleted = calendar_service.delete_event(event_id)
        except CalendarError as exc:
            _check(exc)
            raise
        return ToolResult.success({"id": deleted["id"]})