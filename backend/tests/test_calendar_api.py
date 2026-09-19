"""Phase 6 — Calendar REST API route tests (no real Google calls)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.calendar import calendar_service
from app.services.gmail.token_store import TokenStore

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_token_store(tmp_path, monkeypatch):
    store = TokenStore(str(tmp_path / "calendar_test.json"))
    monkeypatch.setattr(calendar_service, "store", store)
    return store


def test_status_200_when_not_connected():
    resp = client.get("/calendar/status")
    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "email": None}


def test_events_401_when_not_connected():
    assert client.get("/calendar/events").status_code == 401
    assert client.post("/calendar/events", json={"summary": "s", "start": "2026-09-09T10:00:00", "end": "2026-09-09T11:00:00"}).status_code == 401
    assert client.patch("/calendar/events/e1", json={"summary": "x"}).status_code == 401
    assert client.delete("/calendar/events/e1").status_code == 401
    assert client.post("/calendar/summarize", json={}).status_code == 401


def test_status_200_when_connected(monkeypatch, _isolate_token_store):
    _isolate_token_store.save({"token": "x"})  # so status() probes the api
    monkeypatch.setattr(calendar_service, "_get_api", lambda: _Api([{"id": "e1", "summary": "x", "start": {"dateTime": "2026-09-09T10:00:00"}, "end": {"dateTime": "2026-09-09T11:00:00"}}]))
    assert client.get("/calendar/status").json()["connected"] is True


def test_events_list_shape(monkeypatch):
    monkeypatch.setattr(calendar_service, "_get_api", lambda: _Api([{"id": "e1", "summary": "Team sync", "start": {"dateTime": "2026-09-09T14:00:00"}, "end": {"dateTime": "2026-09-09T15:00:00"}, "location": ""}]))
    resp = client.get("/calendar/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["summary"] == "Team sync"
    assert body[0]["start"] == "2026-09-09T14:00:00"


def test_summarize_returns_brief(monkeypatch):
    raw = {"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-09-09T09:30:00"}, "end": {"dateTime": "2026-09-09T09:45:00"}}
    monkeypatch.setattr(calendar_service, "_get_api", lambda: _Api([raw]))
    resp = client.post("/calendar/summarize", json={"days": 1})
    assert resp.status_code == 200
    assert "Standup" in resp.json()["brief"]


class _Api:
    def __init__(self, events=None):
        self._events = list(events or [])

    def list_events(self, **kwargs):
        return self._events

    def create_event(self, **kwargs):
        return {"id": "ev1", "summary": kwargs["summary"], "start": {"dateTime": kwargs["start"]}, "end": {"dateTime": kwargs["end"]}}

    def update_event(self, event_id, **kwargs):
        return {"id": event_id, "summary": kwargs.get("summary", "s"), "start": {"dateTime": "2026-09-09T10:00:00"}}

    def delete_event(self, event_id, **kwargs):
        return {"id": event_id}