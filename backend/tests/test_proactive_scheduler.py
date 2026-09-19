"""Phase 11 — Unit tests for ProactiveScheduler service."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.services.proactive_scheduler import ProactiveScheduler, ProactiveNotification


def test_quiet_hours_check():
    scheduler = ProactiveScheduler()
    scheduler.quiet_hours_start = 23
    scheduler.quiet_hours_end = 8

    # 2 AM is quiet hours
    night = datetime(2026, 9, 17, 2, 0, 0, tzinfo=timezone.utc)
    assert scheduler.is_quiet_hours(night) is True
    assert scheduler.can_emit_alert(night) is False

    # 10 AM is outside quiet hours
    morning = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    assert scheduler.is_quiet_hours(morning) is False
    assert scheduler.can_emit_alert(morning) is True


def test_cooldown_and_hourly_limits():
    scheduler = ProactiveScheduler()
    scheduler.cooldown_seconds = 600  # 10 min
    scheduler.max_per_hour = 2

    t0 = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert scheduler.can_emit_alert(t0) is True

    # Emit first alert
    scheduler.create_notification(
        notif_type="system",
        title="Alert 1",
        message="Message 1",
        now=t0,
    )

    # 5 minutes later: rejected due to cooldown (needs 10 min)
    t1 = t0 + timedelta(minutes=5)
    assert scheduler.can_emit_alert(t1) is False

    # 11 minutes later: allowed
    t2 = t0 + timedelta(minutes=11)
    assert scheduler.can_emit_alert(t2) is True

    # Emit second alert
    scheduler.create_notification(
        notif_type="system",
        title="Alert 2",
        message="Message 2",
        now=t2,
    )

    # 25 minutes later: rejected due to hourly max (2/hour reached)
    t3 = t0 + timedelta(minutes=25)
    assert scheduler.can_emit_alert(t3) is False

    # 65 minutes later: new hour resets hourly count
    t4 = t0 + timedelta(minutes=65)
    assert scheduler.can_emit_alert(t4) is True


def test_notification_creation_and_dismiss():
    scheduler = ProactiveScheduler()
    n = scheduler.create_notification(
        notif_type="task_due",
        title="Meeting prep",
        message="Prep slides",
    )
    assert n.dismissed is False
    assert n.type == "task_due"
    assert "event: notification" in n.to_sse()

    all_notifs = scheduler.list_notifications()
    assert len(all_notifs) >= 1
    assert any(x.id == n.id for x in all_notifs)

    success = scheduler.dismiss_notification(n.id)
    assert success is True
    assert scheduler._notifications[n.id].dismissed is True

    # Unknown ID returns False
    assert scheduler.dismiss_notification("fake-id-12345") is False


@pytest.mark.anyio
async def test_upcoming_tasks_scan_mocked_db():
    scheduler = ProactiveScheduler()
    now = datetime(2026, 9, 17, 14, 0, 0, tzinfo=timezone.utc)

    fake_task = MagicMock()
    fake_task.id = "task-uuid-1"
    fake_task.title = "Finish Phase 11"
    fake_task.due_at = now + timedelta(minutes=15)
    fake_task.status = "pending"

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.all.return_value = [fake_task]
    mock_session.query.return_value = mock_query

    with patch("app.services.proactive_scheduler.db_enabled", return_value=True), \
         patch("app.services.proactive_scheduler.get_session_factory", return_value=lambda: mock_session):
        emitted = await scheduler.check_upcoming_tasks(now)
        assert len(emitted) == 1
        assert emitted[0].title == "Task Due Soon"
        assert "Finish Phase 11" in emitted[0].message
