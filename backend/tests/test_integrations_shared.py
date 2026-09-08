from app.integrations.shared import respond_to
from app.integrations.types import PlatformMessage


def make_message(text="hello", platform="discord", platform_user_id="123"):
    return PlatformMessage(
        platform=platform,
        platform_user_id=platform_user_id,
        author_name="UmiOwner",
        text=text,
        conversation_key="g:ch",
        conversation_title="Discord · #main",
        context_summary="You are talking to the user via Discord in server 'HQ', channel '#main'.",
    )


def test_unknown_user_refused_without_llm_or_db(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "111")

    def boom(*a, **k):
        raise AssertionError("must not touch LLM")

    monkeypatch.setattr("app.integrations.shared.handle_message", boom)
    reply = respond_to(make_message(platform_user_id="999"))
    assert "owner" in reply


def test_owner_routes_through_handle_message(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    calls = {}

    def fake_handle(db, message, **kw):
        calls["db"] = db
        calls["message"] = message
        calls["kw"] = kw
        return "hi back", None

    monkeypatch.setattr("app.integrations.shared.handle_message", fake_handle)
    reply = respond_to(make_message())
    assert reply == "hi back"
    assert calls["message"] == "hello"
    assert calls["kw"]["source"] == "discord"
    assert calls["kw"]["conversation_key"] == "g:ch"
    assert calls["kw"]["conversation_title"] == "Discord · #main"
    assert calls["kw"]["include_greeting"] is False
    assert "Discord" in calls["kw"]["platform_context"]


def test_owner_survives_without_database(monkeypatch):
    from app.config import settings
    from app.db import engine as db_engine

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    monkeypatch.setattr(db_engine, "db_enabled", lambda: False)
    calls = {}

    def fake_handle(db, message, **kw):
        calls["db"] = db
        return "ok", None

    monkeypatch.setattr("app.integrations.shared.handle_message", fake_handle)
    reply = respond_to(make_message())
    assert reply == "ok"
    assert calls["db"] is None