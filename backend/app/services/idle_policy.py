"""Idle/proactive conversation policy.

Pure policy evaluation (no I/O): given the last observed activity and the
previous proactive turns, decide whether Umi may open a conversation on its
own. The frontend times the idle trigger and asks this module (via the backend)
whether engaging is entitled right now; the backend also enforces the same
policy on every ``proactive`` turn so the frontend can never bypass it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import settings


@dataclass(frozen=True)
class IdleDecision:
    can_engage: bool
    reason: str


def _hour_in_range(hour: int, start: int, end: int) -> bool:
    """True when ``hour`` is within [start, end), supporting overnight ranges."""
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def evaluate_idle(
    *,
    now: datetime,
    last_activity_at: datetime | None,
    last_proactive_at: datetime | None,
    proactive_count_last_hour: int,
    enabled: bool | None = None,
    threshold_seconds: int | None = None,
    cooldown_seconds: int | None = None,
    max_prompts_per_hour: int | None = None,
    start_hour: int | None = None,
    end_hour: int | None = None,
) -> IdleDecision:
    """Whether a proactive turn is entitled at ``now``.

    Order of checks (first failure wins):
    1. feature disabled
    2. still within the idle threshold (no inactivity measured yet)
    3. outside the active hours window
    4. still cooling down from the last proactive turn
    5. hourly prompt cap reached
    """
    if enabled is None:
        enabled = settings.umi_idle_enabled
    if threshold_seconds is None:
        threshold_seconds = settings.umi_idle_threshold_seconds
    if cooldown_seconds is None:
        cooldown_seconds = settings.umi_idle_cooldown_seconds
    if max_prompts_per_hour is None:
        max_prompts_per_hour = settings.umi_idle_max_prompts_per_hour
    if start_hour is None:
        start_hour = settings.umi_idle_start_hour
    if end_hour is None:
        end_hour = settings.umi_idle_end_hour

    if not enabled:
        return IdleDecision(False, "disabled")

    if last_activity_at is None:
        return IdleDecision(False, "not-idle-yet")

    age = now - last_activity_at
    if age < timedelta(seconds=threshold_seconds):
        return IdleDecision(False, "not-idle-yet")

    if not _hour_in_range(now.hour, start_hour, end_hour):
        return IdleDecision(False, "outside-active-hours")

    if last_proactive_at is not None and now - last_proactive_at < timedelta(
        seconds=cooldown_seconds
    ):
        return IdleDecision(False, "within-cooldown")

    if proactive_count_last_hour >= max_prompts_per_hour:
        return IdleDecision(False, "hourly-cap-reached")

    return IdleDecision(True, "ok")


def idle_policy_payload() -> dict | None:
    """Serializable policy the frontend uses to time its idle trigger.

    ``None`` when the feature is disabled; otherwise the config values with the
    shared terminology (enabled/threshold_seconds/cooldown_seconds/
    max_prompts_per_hour/start_hour/end_hour).
    """
    if not settings.umi_idle_enabled:
        return None
    return {
        "enabled": True,
        "threshold_seconds": settings.umi_idle_threshold_seconds,
        "cooldown_seconds": settings.umi_idle_cooldown_seconds,
        "max_prompts_per_hour": settings.umi_idle_max_prompts_per_hour,
        "start_hour": settings.umi_idle_start_hour,
        "end_hour": settings.umi_idle_end_hour,
    }