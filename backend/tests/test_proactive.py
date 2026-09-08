"""Phase 9 — proactive (idle) turns through the orchestrator and API.

The idle policy is enforced server-side on every proactive turn: a proactive
request is refused while the owner was recently active, outside active hours,
inside the cooldown, or at the hourly cap. Accepted turns generate the opener
from PROACTIVE_OPENER and never fabricate a user message in history.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.db.models import Conversation, Message, utcnow
from app.db.repositories import OWNER_USER_ID, get_or_create_conversation
from app.main import app
from app.orchestrator.core import PROACTIVE_OPENER, ProactiveNotAllowed

client = TestClient(app)


def _make_conversation(db_session):
    return get_or_create_conversation(db_session, None)


def _seed_activity(db_session, conversation, age):
    """Add a real user message so idleness is measured from it."""
    msg = Message(
        conversation_id=conversation.id,
        role="user",
        content="I'll be away for a bit.",
    )
    db_session.add(msg)
    db_session.flush()
    msg.created_at = utcnow() - age
    db_session.commit()


def _wide_hours(monkeypatch):
    monkeypatch.setattr(settings, "umi_idle_enabled", True)
    monkeypatch.setattr(settings, "umi_idle_start_hour", 0)
    monkeypatch.setattr(settings, "umi_idle_end_hour", 24)
    monkeypatch.setattr(settings, "umi_idle_threshold_seconds", 45)
    monkeypatch.setattr(settings, "umi_idle_cooldown_seconds", 300)
    monkeypatch.setattr(settings, "umi_idle_max_prompts_per_hour", 4)


# ------------------------------------------------------ repository level

def test_entitlement_rejects_while_recently_active(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(seconds=5))
    from app.db.repositories import evaluate_proactive_entitlement

    decision = evaluate_proactive_entitlement(db_session, conv)
    assert decision.can_engage is False
    assert decision.reason == "not-idle-yet"


def test_entitlement_allows_after_idle_threshold(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(minutes=5))
    from app.db.repositories import evaluate_proactive_entitlement

    decision = evaluate_proactive_entitlement(db_session, conv)
    assert decision.can_engage is True
    assert decision.reason == "ok"


def test_entitlement_respects_cooldown(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(minutes=5))
    conv.last_proactive_at = utcnow() - timedelta(seconds=10)
    db_session.commit()
    from app.db.repositories import evaluate_proactive_entitlement

    decision = evaluate_proactive_entitlement(db_session, conv)
    assert decision.reason == "within-cooldown"


def test_entitlement_rolls_over_hourly_cap(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    monkeypatch.setattr(settings, "umi_idle_max_prompts_per_hour", 2)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(minutes=5))
    conv.last_proactive_at = utcnow() - timedelta(hours=2)
    conv.proactive_count_last_hour = 2
    db_session.commit()
    from app.db.repositories import evaluate_proactive_entitlement

    decision = evaluate_proactive_entitlement(db_session, conv)
    assert decision.can_engage is True


def test_record_proactive_increments_then_rolls_over(db_session):
    conv = _make_conversation(db_session)
    from app.db.repositories import record_proactive

    record_proactive(db_session, conv)
    assert conv.proactive_count_last_hour == 1
    assert conv.last_proactive_at is not None
    record_proactive(db_session, conv)
    assert conv.proactive_count_last_hour == 2
    # Hour passes → the counter resets on the next record.
    conv.last_proactive_at = utcnow() - timedelta(hours=2)
    record_proactive(db_session, conv)
    assert conv.proactive_count_last_hour == 1


# ------------------------------------------------------------ orchestrator

def test_handle_proactive_uses_opener_and_skips_user_message(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(minutes=5))
    user_before = (
        db_session.query(Message)
        .filter(Message.conversation_id == conv.id, Message.role == "user")
        .count()
    )
    llm = MagicMock()
    llm.generate_reply.return_value = "Hey, Boss — a question for you."
    with patch("app.orchestrator.core.llm_manager", llm):
        from app.orchestrator.core import handle_message

        reply, conversation_id = handle_message(
            db_session, "", conv.id, proactive=True
        )
    assert reply == "Hey, Boss — a question for you."
    assert conversation_id == str(conv.id)
    assert llm.generate_reply.call_args.args[0] == PROACTIVE_OPENER
    user_after = (
        db_session.query(Message)
        .filter(Message.conversation_id == conv.id, Message.role == "user")
        .count()
    )
    assert user_after == user_before  # no fabricated user turn
    db_session.refresh(conv)
    assert conv.last_proactive_at is not None
    assert conv.proactive_count_last_hour == 1


def test_handle_proactive_raises_when_recently_active(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(seconds=5))
    llm = MagicMock()
    llm.generate_reply.return_value = "should never run"
    with patch("app.orchestrator.core.llm_manager", llm):
        from app.orchestrator.core import handle_message

        import pytest

        with pytest.raises(ProactiveNotAllowed) as excinfo:
            handle_message(db_session, "", conv.id, proactive=True)
    assert excinfo.value.reason == "not-idle-yet"
    llm.generate_reply.assert_not_called()


def test_stream_proactive_denied_yields_code(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(seconds=5))
    from app.orchestrator.core import stream_message

    events = list(stream_message(db_session, "", conv.id, proactive=True))
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "proactive-denied"
    assert events[0][1]["detail"] == "not-idle-yet"


# ------------------------------------------------------------------- API

def test_api_proactive_rejected_while_active(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(seconds=5))
    response = client.post(
        "/chat",
        json={"message": "", "conversation_id": str(conv.id), "proactive": True},
    )
    assert response.status_code == 429
    assert isinstance(response.json()["detail"], str) and response.json()["detail"]


def test_api_proactive_accepted_when_idle(db_session, monkeypatch):
    _wide_hours(monkeypatch)
    conv = _make_conversation(db_session)
    _seed_activity(db_session, conv, age=timedelta(minutes=5))
    llm = MagicMock()
    llm.generate_reply.return_value = "Still here, Boss."
    with patch("app.orchestrator.core.llm_manager", llm):
        response = client.post(
            "/chat",
            json={"message": "", "conversation_id": str(conv.id), "proactive": True},
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Still here, Boss."