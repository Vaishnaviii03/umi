"""Phase 6 — Calendar service tests (no real Google calls)."""

import pytest

from app.services.calendar import CalendarError, CalendarNotConnected, CalendarService
from app.services.calendar.api import normalize_event
from app.services.gmail.token_store import TokenStore


class _FakeAPI:
    def __init__(self, events=None):
        self.events = list(events or [])
        self.calls = []

    def list_events(self, **kwargs):
        self.calls.append(("list", kwargs))
        return self.events

    def create_event(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"id": "ev-new", "summary": kwargs["summary"], "start": {"dateTime": kwargs["start"]},
                "end": {"dateTime": kwargs["end"]}}

    def update_event(self, event_id, **kwargs):
        self.calls.append(("update", event_id, kwargs))
        return {"id": event_id, "summary": kwargs.get("summary", "S"), "start": {"dateTime": "2026-09-09T09:00:00"}}

    def delete_event(self, event_id, **kwargs):
        self.calls.append(("delete", event_id))
        return {"id": event_id}


EVENT = {"id": "e1", "summary": "Physics study", "start": {"dateTime": "2026-09-09T14:00:00+05:30"},
         "end": {"dateTime": "2026-09-09T15:00:00+05:30"}, "location": "Home", "description": "chp 9"}


def _service(fake=None, store_path="tok.json", tmp_path=""):
    return CalendarService(store=TokenStore(str(tmp_path / store_path)), api=fake or _FakeAPI())


def test_normalize_event():
    e = normalize_event(EVENT)
    assert e["id"] == "e1"
    assert e["summary"] == "Physics study"
    assert e["start"] == "2026-09-09T14:00:00+05:30"
    assert e["location"] == "Home"


def test_list_events_uses_default_window(tmp_path):
    fake = _FakeAPI([EVENT])
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=fake)
    out = svc.list_events()
    assert out[0]["summary"] == "Physics study"
    _, kwargs = fake.calls[0]
    assert kwargs["time_min"] and kwargs["time_max"]
    assert kwargs["time_max"] > kwargs["time_min"]


def test_list_events_passes_query_and_bounds(tmp_path):
    fake = _FakeAPI([EVENT])
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=fake)
    svc.list_events(time_min="2026-09-09T00:00:00", time_max="2026-09-10T00:00:00", q="meeting", max_results=5)
    _, kwargs = fake.calls[0]
    assert kwargs["q"] == "meeting"
    assert kwargs["max_results"] == 5


def test_create_event_normalizes_and_audits(tmp_path):
    fake = _FakeAPI()
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=fake)
    out = svc.create_event(summary="Team sync", start="2026-09-09T14:00:00", end="2026-09-09T15:00:00")
    assert out["id"] == "ev-new"
    assert out["summary"] == "Team sync"


def test_update_and_delete(tmp_path):
    fake = _FakeAPI()
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=fake)
    upd = svc.update_event("e1", location="Office")
    assert upd["id"] == "e1"
    assert fake.calls[0][0] == "update"
    svc.delete_event("e1")
    assert fake.calls[1] == ("delete", "e1")


def test_summarize_output_contains_titles(tmp_path):
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=_FakeAPI([EVENT]))
    brief = svc.summarize([normalize_event(EVENT)])
    assert "Physics study" in brief
    assert "Upcoming calendar events" in brief
    assert svc.summarize([]) == "No upcoming calendar events in this window."


def test_not_connected_without_token(tmp_path):
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")))
    with pytest.raises(CalendarNotConnected):
        svc._get_api()


def test_create_event_injects_timezone_for_naive_times():
    """Google 400s on dateTimes without a zone — we must inject one (regression
    for the live 'Missing time zone definition' 500)."""
    from app.services.calendar import api as capi

    captured = {}

    class _Events:
        def insert(self, calendarId, body):
            captured["body"] = body
            return type("_R", (), {"execute": lambda self: body})()

    class _Svc:
        def events(self):
            return _Events()

    capi.CalendarAPI(service=_Svc()).create_event(
        summary="s", start="2026-09-09T10:00:00", end="2026-09-09T11:00:00"
    )
    body = captured["body"]
    assert body["start"]["dateTime"] == "2026-09-09T10:00:00"
    assert body["start"]["timeZone"], "expected an injected per-start IANA timezone"
    assert "/" in body["start"]["timeZone"]
    assert body["end"]["timeZone"] == body["start"]["timeZone"]


def test_api_400_calendar_error_comes_through_as_calendar_error(tmp_path):
    """A Google HttpError must surface as CalendarError, not a raw 500."""
    from app.services.calendar import api as capi
    from googleapiclient.errors import HttpError
    from httplib2 import Response

    def _boom(*args, **kwargs):
        resp = Response({"status": 400})
        raise HttpError(resp, b'{"error": {"message": "Missing time zone"}}', uri="https://calendar.example")

    class _Events:
        def insert(self, calendarId, body):
            return type("_R", (), {"execute": _boom})()

    class _Svc:
        def events(self):
            return _Events()

    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")), api=capi.CalendarAPI(service=_Svc()))
    with pytest.raises(CalendarError):
        svc.create_event(summary="s", start="2026-09-09T10:00:00", end="2026-09-09T11:00:00")
    svc = CalendarService(store=TokenStore(str(tmp_path / "t.json")))
    assert svc.status() == {"connected": False, "email": None}


def test_status_connected_with_api(tmp_path):
    store = TokenStore(str(tmp_path / "t.json"))
    store.save({"token": "x"})  # make the file exist so status probes the api
    svc = CalendarService(store=store, api=_FakeAPI([EVENT]))
    assert svc.status()["connected"] is True