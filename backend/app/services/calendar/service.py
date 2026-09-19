"""Phase 6 — Calendar service facade.

Owns no separate token: reuses the shared ``~/.umi/gmail_token.json`` and the
Gmail API's `credentials_from_store`, so Calendar and Gmail move with the one
Google account. Tests inject a fake ``api``/``api_factory`` like GmailService.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from googleapiclient.errors import HttpError

from app.services.calendar.api import (
    CalendarAPI,
    CalendarError,
    CalendarNotConnected,
    normalize_event,
)
from app.services.gmail.api import credentials_from_store
from app.services.gmail.token_store import TokenStore, token_store

logger = logging.getLogger("umi.calendar")

DEFAULT_WINDOW_DAYS = 7


def _http_safe(exc: HttpError) -> None:
    status = exc.status_code
    if status in (401, 403):
        logger.warning("[calendar] Google denied access status=%s", status)
        raise CalendarNotConnected("Google denied calendar access — reconnect in the Gmail panel.")
    if status == 400:
        raise CalendarError("Calendar rejected the request — check the event details.")
    logger.warning("[calendar] Google API error status=%s", status)
    raise CalendarError("Calendar is unavailable right now.")


class CalendarService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: CalendarAPI | None = None,
        api_factory: Callable[[dict], CalendarAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> CalendarAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise CalendarNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return CalendarAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            logger.warning("[calendar] stored token is invalid; reconnect required")
            raise CalendarNotConnected("no valid Google credentials stored — reconnect")

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            self._get_api().list_events(max_results=1)
            return {"connected": True, "email": None}
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            logger.warning("[calendar] status check failed (token invalid or API unavailable)")
            return {"connected": False, "email": None}

    # -- events -------------------------------------------------------------- #
    def _run(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            _http_safe(exc)

    def list_events(
        self,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        q: str | None = None,
        max_results: int = 25,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        tmin = time_min or now.isoformat()
        tmax = time_max or (now + timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat()
        raw = self._run(self._get_api().list_events, time_min=tmin, time_max=tmax, q=q, max_results=max_results)
        return [normalize_event(item) for item in raw]

    def get_event(self, event_id: str) -> dict:
        raw = self._get_api().list_events(q=f"id:{event_id}", max_results=1)
        if not raw:
            raise CalendarError(f"No calendar event {event_id!r}.")
        return normalize_event(raw[0])

    def create_event(self, *, summary: str, start: str, end: str, description: str = "", location: str = "") -> dict:
        created = self._run(
            self._get_api().create_event,
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
        )
        logger.info("[calendar][audit] event created summary=%r start=%s", summary, start)
        return normalize_event(created)

    def update_event(self, event_id: str, **changes) -> dict:
        updated = self._run(self._get_api().update_event, event_id, **changes)
        logger.info("[calendar][audit] event updated id=%s changes=%s", event_id, ", ".join(sorted(changes) or ["(none)"]))
        return normalize_event(updated)

    def delete_event(self, event_id: str) -> dict:
        self._run(self._get_api().delete_event, event_id)
        logger.info("[calendar][audit] event deleted id=%s", event_id)
        return {"id": event_id}

    # -- analysis ------------------------------------------------------------ #
    def summarize(self, events: list[dict]) -> str:
        if not events:
            return "No upcoming calendar events in this window."
        lines = ["Upcoming calendar events:"]
        for e in events:
            start = e.get("start") or "all-day"
            suffix = f" ({e['location']})" if e.get("location") else ""
            lines.append(f"- {e['summary']} — {start}{suffix}")
        return "\n".join(lines)


calendar_service = CalendarService()

__all__ = [
    "CalendarError",
    "CalendarNotConnected",
    "CalendarService",
    "calendar_service",
]