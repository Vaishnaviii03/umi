"""Phase 9 — greeting-once entitlement and GET /session.

Greeting must be owed exactly once: when the desktop conversation is brand new,
or when it was created within the greeting window and has never been greeted.
Once claimed, it is not owed again until a fresh conversation appears.
"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.db.models import Conversation, utcnow
from app.db.repositories import (
    OWNER_USER_ID,
    claim_greeting,
    get_messages,
    greeting_owed,
)
from app.main import app

client = TestClient(app)


def _make_conversation(db_session, *, created_at=None, last_greeted_at=None):
    conv = Conversation(user_id=OWNER_USER_ID, title="Session test")
    db_session.add(conv)
    db_session.flush()
    if created_at is not None:
        conv.created_at = created_at
    if last_greeted_at is not None:
        conv.last_greeted_at = last_greeted_at
    db_session.flush()
    db_session.commit()
    return conv


def test_greeting_owed_when_conversation_just_created(db_session):
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    assert greeting_owed(db_session, conv) is True


def test_greeting_owed_within_window_never_greeted(db_session):
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    assert greeting_owed(db_session, conv) is True


def test_greeting_not_owed_outside_window(db_session):
    _make_conversation(db_session, created_at=utcnow() - timedelta(days=2))
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    assert greeting_owed(db_session, conv) is False


def test_greeting_not_owed_when_last_greeted(db_session):
    _make_conversation(db_session, last_greeted_at=utcnow())
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    assert greeting_owed(db_session, conv) is False


def test_greeting_not_owed_after_claim(db_session):
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    assert greeting_owed(db_session, conv) is True
    claim_greeting(db_session, conv)
    db_session.commit()
    assert greeting_owed(db_session, conv) is False


def test_session_reports_resumed_conversation(db_session):
    from app.db.repositories import get_or_create_conversation

    conv = get_or_create_conversation(db_session, None)
    from app.db.repositories import append_message

    append_message(db_session, conv.id, "user", "hello")
    db_session.commit()

    response = client.get("/session")
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == str(conv.id)
    assert data["resumed"] is True
    assert data["greeting"]["owed"] is True
    assert data["greeting"]["new"] is False
    assert "server_time" in data


def test_session_reports_fresh_conversation_when_none_exists():
    response = client.get("/session")
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"]
    assert data["resumed"] is False
    assert data["greeting"]["owed"] is True
    assert data["greeting"]["new"] is True


def test_session_claim_greeting_then_not_owed():
    assert client.get("/session").json()["greeting"]["owed"] is True
    assert client.post("/session/claim-greeting").status_code == 204
    again = client.get("/session").json()
    assert again["greeting"]["owed"] is False


def test_session_idle_policy_payload():
    data = client.get("/session").json()
    idle = data["idle"]
    assert idle is not None
    assert idle["enabled"] is settings.umi_idle_enabled
    assert idle["threshold_seconds"] == settings.umi_idle_threshold_seconds
    assert idle["cooldown_seconds"] == settings.umi_idle_cooldown_seconds


def test_phase9_config_fields_exist():
    assert settings.umi_idle_enabled is True
    assert settings.umi_idle_threshold_seconds > 0
    assert settings.umi_idle_cooldown_seconds > 0
    assert settings.umi_idle_max_prompts_per_hour > 0
    assert 0 <= settings.umi_idle_start_hour < settings.umi_idle_end_hour <= 23
    assert settings.umi_greeting_window_s > 0