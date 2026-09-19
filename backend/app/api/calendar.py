"""Phase 6 — Google Calendar REST API.

Read operations (list/summarize) and explicit, user-initiated writes. Writes
are plain POST/PATCH/DELETE here — they only happen on a deliberate action;
the LLM's event tools carry the confirmation gate for destructive deletes.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.calendar import CalendarError, CalendarNotConnected, calendar_service

logger = logging.getLogger("umi.api.calendar")

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=300)
    start: str = Field(min_length=1, max_length=40, description="ISO datetime or all-day date (YYYY-MM-DD)")
    end: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=20_000)
    location: str = Field(default="", max_length=500)


class EventUpdate(BaseModel):
    summary: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    location: str | None = Field(default=None, max_length=500)
    start: str | None = Field(default=None, min_length=1, max_length=40)
    end: str | None = Field(default=None, min_length=1, max_length=40)


class SummarizeRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    q: str | None = Field(default=None, max_length=200)


def _calendar_error(exc: CalendarError) -> HTTPException:
    if isinstance(exc, CalendarNotConnected):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail="Calendar is unavailable right now.")


@router.get("/status")
def calendar_status() -> dict:
    """Connected? (Calendar works off the same Google token as Gmail.)"""
    try:
        return calendar_service.status()
    except CalendarError:
        return {"connected": False, "email": None}


@router.get("/events")
def calendar_events(
    days: int = Query(default=7, ge=1, le=90),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> list[dict]:
    now = datetime.now(timezone.utc)
    try:
        return calendar_service.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(days=days)).isoformat(),
            q=q,
            max_results=limit,
        )
    except CalendarError as exc:
        raise _calendar_error(exc)


@router.post("/events", status_code=201)
def calendar_event_create(payload: EventCreate) -> dict:
    try:
        return calendar_service.create_event(
            summary=payload.summary,
            start=payload.start,
            end=payload.end,
            description=payload.description,
            location=payload.location,
        )
    except CalendarError as exc:
        raise _calendar_error(exc)


@router.patch("/events/{event_id}")
def calendar_event_update(event_id: str, payload: EventUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    try:
        return calendar_service.update_event(event_id, **changes)
    except CalendarError as exc:
        raise _calendar_error(exc)


@router.delete("/events/{event_id}")
def calendar_event_delete(event_id: str) -> dict:
    try:
        return calendar_service.delete_event(event_id)
    except CalendarError as exc:
        raise _calendar_error(exc)


@router.post("/summarize")
def calendar_summarize(payload: SummarizeRequest) -> dict:
    now = datetime.now(timezone.utc)
    try:
        events = calendar_service.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(days=payload.days)).isoformat(),
            q=payload.q,
            max_results=25,
        )
        return {"brief": calendar_service.summarize(events)}
    except CalendarError as exc:
        raise _calendar_error(exc)