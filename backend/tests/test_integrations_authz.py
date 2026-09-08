from app.config import settings
from app.integrations.authz import refusal_text, resolve_role


def test_owner_matches_discord_owner_id(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "12345")
    assert resolve_role("discord", "12345") == "owner"


def test_non_owner_is_unknown(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "12345")
    monkeypatch.setattr(settings, "telegram_owner_id", "678")
    assert resolve_role("discord", "999") == "unknown"
    assert resolve_role("telegram", "12345") == "unknown"


def test_numeric_telegram_id_matches(monkeypatch):
    monkeypatch.setattr(settings, "telegram_owner_id", "42")
    assert resolve_role("telegram", 42) == "owner"


def test_missing_owner_id_means_unknown(monkeypatch):
    monkeypatch.setattr(settings, "discord_owner_id", "")
    monkeypatch.setattr(settings, "telegram_owner_id", "")
    assert resolve_role("discord", "anything") == "unknown"
    assert resolve_role("telegram", "anything") == "unknown"


def test_unknown_platform_is_never_owner(monkeypatch):
    monkeypatch.setattr(settings, "telegram_owner_id", "1")
    assert resolve_role("bogus", "1") == "unknown"


def test_refusal_text_is_polite_and_does_not_call_llm():
    text = refusal_text("discord", "Alice")
    assert "owner" in text
    assert "Alice" not in text