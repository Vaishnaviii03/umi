"""Phase 11 — Proactive UMI Background Scheduler and Notification Broker.

Monitors tasks and calendar events in the background and delivers notifications
over Server-Sent Events (SSE) while enforcing quiet hours and cooldown periods.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import uuid
from typing import Any, AsyncGenerator

from app.config import settings
from app.db.engine import db_enabled, get_session_factory
from app.db.models import Task, utcnow
from app.services.idle_policy import _hour_in_range

logger = logging.getLogger("umi.proactive_scheduler")


@dataclass
class ProactiveNotification:
    id: str
    type: str  # "task_due" | "calendar_alert" | "system"
    title: str
    message: str
    created_at: str
    dismissed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        data = json.dumps(self.to_dict())
        return f"event: notification\ndata: {data}\n\n"


class ProactiveScheduler:
    def __init__(self) -> None:
        self._notifications: dict[str, ProactiveNotification] = {}
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._seen_task_ids: set[str] = set()
        self._seen_event_ids: set[str] = set()
        self._last_alert_at: datetime | None = None
        self._hourly_alert_count: int = 0
        self._hourly_window_start: datetime | None = None
        self._running: bool = False
        self._loop_task: asyncio.Task[None] | None = None

        # Configuration defaults
        self.check_interval_seconds: int = 60
        self.cooldown_seconds: int = 900  # 15 minutes between proactive popups
        self.max_per_hour: int = 4
        self.quiet_hours_start: int = 23  # 11 PM
        self.quiet_hours_end: int = 8     # 8 AM

    def start(self) -> None:
        """Start the background check loop if not already running."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("[proactive_scheduler] Started background monitor.")

    def stop(self) -> None:
        """Stop background check loop."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            self._loop_task = None
        logger.info("[proactive_scheduler] Stopped background monitor.")

    def is_quiet_hours(self, now: datetime) -> bool:
        """Check if current time falls within configured quiet hours."""
        return _hour_in_range(now.hour, self.quiet_hours_start, self.quiet_hours_end)

    def can_emit_alert(self, now: datetime) -> bool:
        """Check quiet hours, cooldown, and hourly quota."""
        if self.is_quiet_hours(now):
            return False

        # Reset hourly window if > 1 hour has elapsed
        if self._hourly_window_start is None or (now - self._hourly_window_start).total_seconds() >= 3600:
            self._hourly_window_start = now
            self._hourly_alert_count = 0

        if self._hourly_alert_count >= self.max_per_hour:
            return False

        if self._last_alert_at is not None:
            elapsed = (now - self._last_alert_at).total_seconds()
            if elapsed < self.cooldown_seconds:
                return False

        return True

    def record_alert_emitted(self, now: datetime) -> None:
        self._last_alert_at = now
        self._hourly_alert_count += 1

    def create_notification(
        self,
        *,
        notif_type: str,
        title: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> ProactiveNotification:
        current_time = now or utcnow()
        notif_id = str(uuid.uuid4())
        notif = ProactiveNotification(
            id=notif_id,
            type=notif_type,
            title=title,
            message=message,
            created_at=current_time.isoformat(),
            metadata=metadata or {},
        )
        self._notifications[notif_id] = notif
        self.record_alert_emitted(current_time)
        self.broadcast(notif.to_sse())
        logger.info("[proactive_scheduler] Emitted alert: %s (%s)", title, notif_type)
        return notif

    def broadcast(self, sse_message: str) -> None:
        """Broadcast message to all connected SSE clients."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(sse_message)
            except asyncio.QueueFull:
                logger.warning("[proactive_scheduler] Dropping message for full queue.")

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe an SSE stream to notification events."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)

        # Initial connection handshake comment
        yield ": connected\n\n"

        # Also send any currently active, un-dismissed notifications
        for notif in self.list_notifications():
            if not notif.dismissed:
                yield notif.to_sse()

        try:
            while True:
                try:
                    # Heartbeat every 15s to keep SSE connection alive
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            self._subscribers.discard(queue)

    def list_notifications(self) -> list[ProactiveNotification]:
        return list(self._notifications.values())

    def dismiss_notification(self, notif_id: str) -> bool:
        if notif_id in self._notifications:
            self._notifications[notif_id].dismissed = True
            return True
        return False

    async def check_upcoming_tasks(self, now: datetime) -> list[ProactiveNotification]:
        """Check for pending tasks due within the next 30 minutes."""
        if not db_enabled():
            return []

        session_factory = get_session_factory()
        if session_factory is None:
            return []

        emitted: list[ProactiveNotification] = []
        try:
            session = session_factory()
            try:
                threshold = now + timedelta(minutes=30)
                yesterday = now - timedelta(hours=24)

                tasks = (
                    session.query(Task)
                    .filter(
                        Task.status == "pending",
                        Task.due_at.isnot(None),
                        Task.due_at <= threshold,
                        Task.due_at >= yesterday,
                    )
                    .all()
                )

                for task in tasks:
                    task_key = str(task.id)
                    if task_key in self._seen_task_ids:
                        continue

                    if not self.can_emit_alert(now):
                        break

                    due_dt = task.due_at
                    if due_dt:
                        diff_minutes = max(0, int((due_dt - now).total_seconds() // 60))
                        msg = (
                            f"Task '{task.title}' is due in {diff_minutes} minutes."
                            if diff_minutes > 0
                            else f"Task '{task.title}' is overdue."
                        )
                    else:
                        msg = f"Task '{task.title}' is due soon."

                    notif = self.create_notification(
                        notif_type="task_due",
                        title="Task Due Soon",
                        message=msg,
                        metadata={"task_id": str(task.id), "title": task.title},
                        now=now,
                    )
                    self._seen_task_ids.add(task_key)
                    emitted.append(notif)
            finally:
                session.close()
        except Exception as exc:
            logger.exception("[proactive_scheduler] Error checking tasks: %s", exc)

        return emitted

    async def check_upcoming_calendar(self, now: datetime) -> list[ProactiveNotification]:
        """Check connected calendar for events starting in < 15 minutes."""
        emitted: list[ProactiveNotification] = []
        try:
            from app.services.calendar.service import CalendarService
            from app.services.calendar.api import CalendarNotConnected

            cal_service = CalendarService()
            time_min = now
            time_max = now + timedelta(minutes=15)

            events = await asyncio.to_thread(
                cal_service.list_events,
                time_min=time_min,
                time_max=time_max,
                max_results=5,
            )

            for ev in events:
                ev_id = ev.get("id")
                if not ev_id or ev_id in self._seen_event_ids:
                    continue

                if not self.can_emit_alert(now):
                    break

                summary = ev.get("summary", "Upcoming meeting")
                start_iso = ev.get("start", "")
                notif = self.create_notification(
                    notif_type="calendar_alert",
                    title="Upcoming Calendar Event",
                    message=f"'{summary}' starts soon.",
                    metadata={"event_id": ev_id, "summary": summary, "start": start_iso},
                    now=now,
                )
                self._seen_event_ids.add(ev_id)
                emitted.append(notif)
        except CalendarNotConnected:
            pass  # Normal when calendar is not linked
        except Exception as exc:
            logger.debug("[proactive_scheduler] Calendar check bypassed: %s", exc)

        return emitted

    async def scan_all(self, now: datetime | None = None) -> list[ProactiveNotification]:
        current_time = now or utcnow()
        if self.is_quiet_hours(current_time):
            return []

        task_alerts = await self.check_upcoming_tasks(current_time)
        cal_alerts = await self.check_upcoming_calendar(current_time)
        return task_alerts + cal_alerts

    async def _run_loop(self) -> None:
        """Background continuous execution loop."""
        while self._running:
            try:
                await self.scan_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("[proactive_scheduler] Scan cycle error: %s", exc)

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break


proactive_scheduler = ProactiveScheduler()
