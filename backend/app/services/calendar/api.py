"""Phase 6 — Google Calendar API boundary.

Thin wrapper around the Calendar REST client. Reuses the token/credentials
handling from the Gmail layer (same Google account, same OAuth consent), so
everything above this layer can inject a fake object for tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.gmail.api import credentials_from_store

logger = logging.getLogger("umi.calendar")


class CalendarError(Exception):
    """Base class — message is always safe to show the user."""


class CalendarNotConnected(CalendarError):
    pass


def _default_tz() -> str:
    """Best-effort IANA zone from /etc/localtime (macOS/Linux), else UTC."""
    try:
        target = str(Path("/etc/localtime").resolve())
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    except OSError:
        pass
    return "UTC"


def _naive(value: str) -> bool:
    """True when an ISO string has no explicit timezone/offset."""
    time_part = value[11:] if "T" in value else ""
    return "Z" not in time_part.upper() and "+" not in time_part


def _start(value: str) -> dict:
    if "T" not in value:
        return {"date": value}
    item = {"dateTime": value}
    if _naive(value):
        # Google requires the zone inside EventDateTime when dateTime is naive.
        item["timeZone"] = _default_tz()
    return item


class CalendarAPI:
    """Thin wrapper around the Calendar REST client (injectable for tests)."""

    def __init__(self, *, credentials=None, service=None) -> None:
        self._creds = credentials
        self._service = service  # injectable for tests

    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise CalendarNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("calendar", "v3", credentials=self._creds, cache_discovery=False)

    def list_events(
        self,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        q: str | None = None,
        max_results: int = 25,
        calendar_id: str = "primary",
    ) -> list[dict]:
        response = (
            self._svc()
            .events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min or None,
                timeMax=time_max or None,
                q=q or None,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return response.get("items", [])

    def create_event(
        self,
        *,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        calendar_id: str = "primary",
    ) -> dict:
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": _start(start),
            "end": _start(end),
        }
        return self._svc().events().insert(calendarId=calendar_id, body=body).execute()

    def update_event(
        self,
        event_id: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        location: str | None = None,
        start: str | None = None,
        end: str | None = None,
        calendar_id: str = "primary",
    ) -> dict:
        body: dict = {}
        for key in ("summary", "description", "location"):
            value = locals()[key]
            if value is not None:
                body[key] = value
        if start is not None:
            body["start"] = _start(start)
        if end is not None:
            body["end"] = _start(end)
        return self._svc().events().patch(calendarId=calendar_id, eventId=event_id, body=body).execute()

    def delete_event(self, event_id: str, *, calendar_id: str = "primary") -> dict:
        self._svc().events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"id": event_id}


def normalize_event(raw: dict) -> dict:
    """Stable dict for routes/tools/LLM context from raw Calendar JSON."""
    start = raw.get("start") or {}
    end = raw.get("end") or {}
    return {
        "id": raw.get("id"),
        "summary": raw.get("summary") or "(no title)",
        "description": raw.get("description") or "",
        "location": raw.get("location") or "",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": bool(start.get("date")),
        "status": raw.get("status"),
        "attendees": [a.get("email") for a in (raw.get("attendees") or []) if a.get("email")],
        "link": raw.get("htmlLink"),
    }


__all__ = [
    "CalendarAPI",
    "CalendarError",
    "CalendarNotConnected",
    "credentials_from_store",
    "normalize_event",
]