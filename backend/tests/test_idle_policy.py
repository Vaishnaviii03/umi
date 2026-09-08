import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.services.idle_policy import (
    IdleDecision,
    _hour_in_range,
    evaluate_idle,
    idle_policy_payload,
)

TZ = timezone.utc


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 9, 8, hour, minute, second, tzinfo=TZ)


# ---------------------------------------------------------------- hour range

def test_hour_in_range_covers_normal_and_overnight_ranges():
    assert _hour_in_range(9, 8, 23) is True
    assert _hour_in_range(23, 8, 23) is False
    assert _hour_in_range(8, 8, 23) is True
    assert _hour_in_range(7, 8, 23) is False
    assert _hour_in_range(3, 22, 4) is True
    assert _hour_in_range(22, 22, 4) is True
    assert _hour_in_range(4, 22, 4) is False
    assert _hour_in_range(12, 22, 4) is False


# ------------------------------------------------------------------ evaluate

def decision(**overrides) -> IdleDecision:
    params = {
        "now": at(14),
        "last_activity_at": at(10),
        "last_proactive_at": None,
        "proactive_count_last_hour": 0,
    }
    params.update(overrides)
    return evaluate_idle(**params)


def test_disabled_feature_never_engages():
    d = decision(enabled=False)
    assert d.can_engage is False
    assert d.reason == "disabled"


def test_no_measured_activity_is_not_yet_idle():
    d = decision(last_activity_at=None)
    assert d.reason == "not-idle-yet"


def test_rejects_within_threshold():
    d = decision(now=at(10, 0, 30), last_activity_at=at(10), threshold_seconds=45)
    assert (at(10, 0, 30) - at(10)).total_seconds() == 30
    assert d.reason == "not-idle-yet"


def test_accepts_past_threshold():
    d = decision(now=at(10, 1), threshold_seconds=45)
    assert d.can_engage is True
    assert d.reason == "ok"


def test_rejects_outside_active_hours():
    d = decision(now=at(7), last_activity_at=at(6), start_hour=8, end_hour=23, threshold_seconds=0)
    assert d.reason == "outside-active-hours"


def test_boundary_hour_is_inclusive_of_start():
    d = decision(now=at(8), last_activity_at=at(6), start_hour=8, end_hour=23, threshold_seconds=0)
    assert d.can_engage is True


def test_accepts_inside_active_hours_overnight():
    d = decision(now=at(23), start_hour=22, end_hour=4, threshold_seconds=0)
    assert d.can_engage is True


def test_rejects_within_cooldown_of_last_proactive():
    d = decision(
        now=at(10, 3),
        last_activity_at=at(9),
        last_proactive_at=at(10, 2),
        cooldown_seconds=120,
        threshold_seconds=0,
    )
    assert d.reason == "within-cooldown"


def test_accepts_after_cooldown_elapsed():
    d = decision(
        now=at(10, 3),
        last_activity_at=at(9),
        last_proactive_at=at(10, 1),
        cooldown_seconds=120,
        threshold_seconds=0,
    )
    assert d.can_engage is True


def test_rejects_at_hourly_cap():
    d = decision(proactive_count_last_hour=4, max_prompts_per_hour=4, threshold_seconds=0)
    assert d.reason == "hourly-cap-reached"


def test_accepts_below_hourly_cap():
    d = decision(proactive_count_last_hour=3, max_prompts_per_hour=4, threshold_seconds=0)
    assert d.can_engage is True


def test_check_order_cooldown_precedes_cap():
    d = decision(
        last_activity_at=at(9),
        last_proactive_at=at(13, 59),
        proactive_count_last_hour=9,
        max_prompts_per_hour=4,
        cooldown_seconds=3600,
        threshold_seconds=0,
    )
    assert d.reason == "within-cooldown"


# --------------------------------------------------------------- payload

def test_payload_is_none_when_disabled(monkeypatch):
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_enabled", False)
    assert idle_policy_payload() is None


def test_payload_roundtrips_config(monkeypatch):
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_enabled", True)
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_threshold_seconds", 60)
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_cooldown_seconds", 180)
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_max_prompts_per_hour", 2)
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_start_hour", 8)
    monkeypatch.setattr("app.services.idle_policy.settings.umi_idle_end_hour", 23)
    assert idle_policy_payload() == {
        "enabled": True,
        "threshold_seconds": 60,
        "cooldown_seconds": 180,
        "max_prompts_per_hour": 2,
        "start_hour": 8,
        "end_hour": 23,
    }