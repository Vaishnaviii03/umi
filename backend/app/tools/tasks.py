"""Phase 4 — task tools.

Persistent, owner-scoped to-dos/reminders. Unlike the Phase 3 built-ins these
read and write ``tasks`` via the shared database session (``ctx.db``), so the
LLM can create/list/complete/update tasks in natural conversation and over
voice. ``list_tasks`` is read-only (permission 1); every mutation is a write
(permission 2), sitting comfortably under the default ceiling.

Relative due dates ("tomorrow 5pm", "next Monday") are resolved by the LLM to
an ISO timestamp before calling the tool — the system context always includes
the user's current local time, which the model anchors on.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.db.repositories import (
    create_task as repo_create_task,
    delete_task as repo_delete_task,
    get_task as repo_get_task,
    list_tasks as repo_list_tasks,
    update_task as repo_update_task,
)
from app.tools.base import Tool, ToolContext, ToolExecutionError, ToolResult

TASK_TITLE_MAX = 200
TASK_STATUSES = ("pending", "done")

_DUE_AT_HELP = (
    "ISO 8601 date/time (e.g. '2026-09-09T17:00:00' or a bare date '2026-09-09'). "
    "Resolve relative phrasings like 'tomorrow' / 'next Monday' against the "
    "user's current local time shown in the system context before you fill this."
)


def _task_dict(task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status,
        "due_at": task.due_at.isoformat() if task.due_at is not None else None,
    }


def parse_due_at(value: str | None) -> datetime | None:
    """Parse an ISO date/datetime into an aware local datetime."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
        return datetime.combine(parsed, datetime.min.time()).astimezone()
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ToolExecutionError(
            "due_at must be an ISO 8601 date/time like '2026-09-09' or '2026-09-09T17:00:00'"
        ) from exc
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return parsed.replace(tzinfo=local_tz)
    return parsed.astimezone()


def _require_db(ctx: ToolContext):
    if ctx.db is None:
        raise ToolExecutionError("Umi's database isn't configured yet — tasks can't be saved")


class CreateTaskArgs(BaseModel):
    title: str = Field(min_length=1, max_length=TASK_TITLE_MAX)
    due_at: str | None = Field(default=None, max_length=64, description=_DUE_AT_HELP)


class TaskOut(BaseModel):
    id: str
    title: str
    status: str
    due_at: str | None


class CreateTaskOutput(BaseModel):
    task: TaskOut


class CreateTaskTool(Tool):
    name = "create_task"
    description = (
        "Create a new to-do or reminder for the user. Pass `title` and an "
        "optional `due_at` ISO timestamp (resolved from relative phrasing like "
        "'tomorrow' against the current local time in the system context). "
        "Returns the created task."
    )
    permission_level = 2
    owner_only = True
    args_model = CreateTaskArgs
    output_model = CreateTaskOutput

    def run(self, ctx: ToolContext, title: str, due_at: str | None = None, **kwargs) -> ToolResult:
        _require_db(ctx)
        task = repo_create_task(ctx.db, title, due_at=parse_due_at(due_at))
        ctx.db.commit()
        return ToolResult.success({"task": _task_dict(task)})


class ListTasksArgs(BaseModel):
    status: str | None = Field(default=None, description="Filter: 'pending' or 'done'.")


class ListTasksOutput(BaseModel):
    count: int
    tasks: list[TaskOut]


class ListTasksTool(Tool):
    name = "list_tasks"
    description = (
        "List the user's tasks, most recently updated first. `status` may be "
        "'pending' or 'done' to filter; omit for everything."
    )
    permission_level = 1
    owner_only = True
    args_model = ListTasksArgs
    output_model = ListTasksOutput

    def run(self, ctx: ToolContext, status: str | None = None, **kwargs) -> ToolResult:
        _require_db(ctx)
        tasks = repo_list_tasks(ctx.db, status=status)
        return ToolResult.success(
            {"count": len(tasks), "tasks": [_task_dict(t) for t in tasks]}
        )


class TaskIdArgs(BaseModel):
    task_id: str = Field(min_length=1, description="The task's id (UUID).")


class TaskIdOutput(BaseModel):
    task: TaskOut


class CompleteTaskTool(Tool):
    name = "complete_task"
    description = "Mark a task as done, e.g. when the user says they finished something."
    permission_level = 2
    owner_only = True
    args_model = TaskIdArgs
    output_model = TaskIdOutput

    def run(self, ctx: ToolContext, task_id: str, **kwargs) -> ToolResult:
        _require_db(ctx)
        task = repo_update_task(ctx.db, _parse_task_id(task_id), status="done")
        if task is None:
            raise ToolExecutionError("no such task — check the id with list_tasks")
        ctx.db.commit()
        return ToolResult.success({"task": _task_dict(task)})


class UpdateTaskArgs(BaseModel):
    task_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=TASK_TITLE_MAX)
    due_at: str | None = Field(default=None, max_length=64)


class UpdateTaskTool(Tool):
    name = "update_task"
    description = (
        "Update an existing task's title and/or due_at (ISO timestamp). Only "
        "pass the fields that change. To mark something finished use "
        "complete_task instead."
    )
    permission_level = 2
    owner_only = True
    args_model = UpdateTaskArgs
    output_model = TaskIdOutput

    def run(self, ctx: ToolContext, task_id: str, title: str | None = None, due_at: str | None = None, **kwargs) -> ToolResult:
        _require_db(ctx)
        task = repo_update_task(
            ctx.db,
            _parse_task_id(task_id),
            title=title,
            due_at=parse_due_at(due_at),
        )
        if task is None:
            raise ToolExecutionError("no such task — check the id with list_tasks")
        ctx.db.commit()
        return ToolResult.success({"task": _task_dict(task)})


class DeleteTaskOutput(BaseModel):
    deleted: bool


class DeleteTaskTool(Tool):
    name = "delete_task"
    description = "Delete a task entirely (not just mark it done)."
    permission_level = 2
    owner_only = True
    args_model = TaskIdArgs
    output_model = DeleteTaskOutput

    def run(self, ctx: ToolContext, task_id: str, **kwargs) -> ToolResult:
        _require_db(ctx)
        if not repo_delete_task(ctx.db, _parse_task_id(task_id)):
            raise ToolExecutionError("no such task — check the id with list_tasks")
        ctx.db.commit()
        return ToolResult.success({"deleted": True})


def _parse_task_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise ToolExecutionError("task_id must be a valid UUID") from exc