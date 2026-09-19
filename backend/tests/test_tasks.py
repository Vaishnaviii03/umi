"""Phase 4 — task repository + API tests."""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.repositories import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    update_task,
)
from app.db.session import get_db
from app.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #
def test_list_tasks_defaults_to_empty(db_session):
    assert list_tasks(db_session) == []


def test_create_and_list_tasks(db_session):
    create_task(db_session, "study physics")
    create_task(
        db_session, "call the dentist", due_at=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    )
    db_session.commit()

    tasks = list_tasks(db_session)
    assert sorted(t.title for t in tasks) == ["call the dentist", "study physics"]
    assert any(t.due_at is not None for t in tasks)


def test_get_task_returns_owner_task(db_session):
    task = create_task(db_session, "buy groceries")
    db_session.commit()
    fetched = get_task(db_session, task.id)
    assert fetched is not None
    assert fetched.title == "buy groceries"


def test_update_task_partial(db_session):
    task = create_task(db_session, "water plants")
    db_session.commit()
    updated = update_task(
        db_session, task.id, status="done", due_at=datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
    )
    assert updated is not None
    assert updated.status == "done"
    assert updated.title == "water plants"
    db_session.commit()
    assert get_task(db_session, task.id).status == "done"


def test_update_task_status_filter(db_session):
    create_task(db_session, "a")
    create_task(db_session, "b", due_at=None)
    db_session.commit()
    done = update_task(db_session, list_tasks(db_session)[0].id, status="done")
    assert done is not None
    db_session.commit()
    assert [t.title for t in list_tasks(db_session, status="done")] == ["a"]
    assert [t.title for t in list_tasks(db_session, status="pending")] == ["b"]


def test_delete_task(db_session):
    task = create_task(db_session, "delete me")
    db_session.commit()
    assert delete_task(db_session, task.id) is True
    db_session.commit()
    assert list_tasks(db_session) == []


def test_delete_task_unknown_or_foreign(db_session):
    assert delete_task(db_session, uuid.uuid4()) is False


# --------------------------------------------------------------------------- #
# API lifecycle
# --------------------------------------------------------------------------- #
def test_tasks_api_lifecycle():
    created = client.post("/tasks", json={"title": "finish TRD"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["status"] == "pending"
    assert created.json()["due_at"] is None

    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert any(t["id"] == task_id for t in listed.json())

    updated = client.patch(f"/tasks/{task_id}", json={"status": "done"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"

    done = client.get("/tasks", params={"status": "done"})
    assert any(t["id"] == task_id for t in done.json())

    deleted = client.delete(f"/tasks/{task_id}")
    assert deleted.status_code == 204
    assert all(t["id"] != task_id for t in client.get("/tasks").json())


def test_tasks_api_accepts_due_at():
    created = client.post(
        "/tasks", json={"title": "remind me tomorrow", "due_at": "2026-09-10T17:00:00"}
    )
    assert created.status_code == 201
    assert created.json()["due_at"] is not None


def test_tasks_api_rejects_invalid_due_at():
    response = client.post("/tasks", json={"title": "bad", "due_at": "not-a-date"})
    assert response.status_code == 422


def test_tasks_api_rejects_empty_title_and_bad_status():
    assert client.post("/tasks", json={"title": ""}).status_code == 422
    assert (
        client.patch(f"/tasks/{uuid.uuid4()}", json={"status": "wip"}).status_code == 422
    )


def test_tasks_api_404_for_unknown_task():
    assert client.patch(f"/tasks/{uuid.uuid4()}", json={"status": "done"}).status_code == 404
    assert client.delete(f"/tasks/{uuid.uuid4()}").status_code == 404


# --------------------------------------------------------------------------- #
# Graceful degradation when the database is unavailable
# --------------------------------------------------------------------------- #
def test_tasks_endpoints_503_when_db_disabled():
    app.dependency_overrides.update({get_db: lambda: None})
    try:
        assert client.get("/tasks").status_code == 503
        assert client.post("/tasks", json={"title": "x"}).status_code == 503
        assert client.patch(f"/tasks/{uuid.uuid4()}", json={"status": "done"}).status_code == 503
        assert client.delete(f"/tasks/{uuid.uuid4()}").status_code == 503
    finally:
        app.dependency_overrides.clear()