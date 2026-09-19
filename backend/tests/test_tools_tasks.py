"""Phase 4 — task tool tests (registry, execution with a DB session, permissions)."""

import uuid

import pytest

from app.config import settings
from app.db.repositories import get_task
from app.tools import (
    PermissionDenied,
    ToolContext,
    ToolExecutionError,
    tool_manager,
)
from app.tools.tasks import parse_due_at

OWNER = str(settings.owner_id)


def ctx(db, **extra):
    kwargs = {"user_id": OWNER, "db": db}
    kwargs.update(extra)
    return ToolContext(**kwargs)


# --------------------------------------------------------------------------- #
# Registry metadata
# --------------------------------------------------------------------------- #
def test_task_tools_metadata():
    catalog = {t["name"]: t for t in tool_manager.catalog()}
    assert catalog["list_tasks"]["permission_level"] == 1
    for name in ("create_task", "complete_task", "update_task", "delete_task"):
        assert catalog[name]["permission_level"] == 2
        assert catalog[name]["owner_only"] is True
        assert catalog[name]["requires_confirmation"] is False


# --------------------------------------------------------------------------- #
# create_task / list_tasks
# --------------------------------------------------------------------------- #
def test_create_task_persists(db_session):
    result = tool_manager.execute_tool(
        "create_task", {"title": "study physics"}, ctx(db_session)
    )
    assert result.status == "success"
    assert result.data["task"]["title"] == "study physics"
    assert result.data["task"]["status"] == "pending"
    db_session.commit()
    assert get_task(db_session, uuid.UUID(result.data["task"]["id"])).title == "study physics"


def test_create_task_with_due_at(db_session):
    result = tool_manager.execute_tool(
        "create_task",
        {"title": "call dentist", "due_at": "2026-09-11T09:30:00"},
        ctx(db_session),
    )
    assert result.status == "success"
    assert result.data["task"]["due_at"] is not None


def test_create_task_rejects_invalid_due_at(db_session):
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool(
            "create_task", {"title": "x", "due_at": "garbage"}, ctx(db_session)
        )


def test_list_tasks_after_create(db_session):
    tool_manager.execute_tool("create_task", {"title": "alpha"}, ctx(db_session))
    tool_manager.execute_tool(
        "create_task", {"title": "beta", "due_at": "2026-09-12"}, ctx(db_session)
    )
    db_session.commit()

    all_tasks = tool_manager.execute_tool("list_tasks", {}, ctx(db_session))
    assert all_tasks.status == "success"
    assert all_tasks.data["count"] == 2

    done = tool_manager.execute_tool("list_tasks", {"status": "done"}, ctx(db_session))
    assert done.data["count"] == 0

    pending = tool_manager.execute_tool("list_tasks", {"status": "pending"}, ctx(db_session))
    assert pending.data["count"] == 2


# --------------------------------------------------------------------------- #
# complete_task / update_task / delete_task
# --------------------------------------------------------------------------- #
def test_complete_task_sets_done(db_session):
    created = tool_manager.execute_tool(
        "create_task", {"title": "water plants"}, ctx(db_session)
    )
    task_id = created.data["task"]["id"]

    completed = tool_manager.execute_tool(
        "complete_task", {"task_id": task_id}, ctx(db_session)
    )
    assert completed.data["task"]["status"] == "done"


def test_update_task_changes_title_and_due(db_session):
    created = tool_manager.execute_tool(
        "create_task", {"title": "old title"}, ctx(db_session)
    )
    task_id = created.data["task"]["id"]
    updated = tool_manager.execute_tool(
        "update_task",
        {"task_id": task_id, "title": "new title", "due_at": "2026-09-13T18:00:00"},
        ctx(db_session),
    )
    assert updated.data["task"]["title"] == "new title"
    assert updated.data["task"]["due_at"] is not None


def test_delete_task_removes_it(db_session):
    created = tool_manager.execute_tool(
        "create_task", {"title": "temp"}, ctx(db_session)
    )
    task_id = created.data["task"]["id"]
    deleted = tool_manager.execute_tool(
        "delete_task", {"task_id": task_id}, ctx(db_session)
    )
    assert deleted.data["deleted"] is True
    result = tool_manager.execute_tool("list_tasks", {}, ctx(db_session))
    assert result.data["count"] == 0


def test_complete_task_unknown_id_fails(db_session):
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool(
            "complete_task",
            {"task_id": "00000000-0000-0000-0000-000000000000"},
            ctx(db_session),
        )


# --------------------------------------------------------------------------- #
# Availability / permissions
# --------------------------------------------------------------------------- #
def test_tasks_require_db():
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("create_task", {"title": "x"}, ctx(None))


def test_task_tool_denied_without_db_for_list():
    with pytest.raises(ToolExecutionError):
        tool_manager.execute_tool("list_tasks", {}, ctx(None))


def test_task_write_permission_ceiling_enforced(monkeypatch, db_session):
    monkeypatch.setattr(settings, "tools_max_permission_level", 1)
    with pytest.raises(PermissionDenied):
        tool_manager.execute_tool("create_task", {"title": "x"}, ctx(db_session))
    # Read-only list_tasks is still allowed at permission ceiling 1.
    result = tool_manager.execute_tool("list_tasks", {}, ctx(db_session))
    assert result.status == "success"


def test_non_owner_denied(db_session):
    with pytest.raises(PermissionDenied):
        tool_manager.execute_tool(
            "create_task", {"title": "x"}, ctx(db_session, user_id="someone-else")
        )


# --------------------------------------------------------------------------- #
# due_at parsing helper
# --------------------------------------------------------------------------- #
def test_parse_due_at_variants():
    assert parse_due_at(None) is None
    date_only = parse_due_at("2026-09-11")
    assert date_only is not None and date_only.tzinfo is not None
    aware = parse_due_at("2026-09-11T09:00:00+05:30")
    assert aware is not None
    naive = parse_due_at("2026-09-11T09:00:00")
    assert naive is not None and naive.tzinfo is not None
    with pytest.raises(ToolExecutionError):
        parse_due_at("nonsense")