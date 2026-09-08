import app.config as config_module


def test_discord_settings_properties(monkeypatch):
    s = config_module.settings
    monkeypatch.setattr(s, "discord_application_id", "11111111")
    monkeypatch.setattr(s, "discord_public_key", "pub-key")
    monkeypatch.setattr(s, "discord_bot_token", "disc-token")
    monkeypatch.setattr(s, "discord_owner_id", "22222222")
    assert s.discord_application_id == "11111111"
    assert s.discord_public_key == "pub-key"
    assert s.discord_bot_token == "disc-token"
    assert s.discord_owner_id == "22222222"
    assert s.discord_enabled is True
    assert s.telegram_enabled is False


def test_telegram_settings_properties(monkeypatch):
    s = config_module.settings
    monkeypatch.setattr(s, "telegram_bot_token", "333:tok")
    monkeypatch.setattr(s, "telegram_owner_id", "444")
    assert s.telegram_bot_token == "333:tok"
    assert s.telegram_owner_id == "444"
    assert s.telegram_enabled is True
    assert s.discord_enabled is False


def test_integrations_disabled_when_tokens_empty(monkeypatch):
    s = config_module.settings
    monkeypatch.setattr(s, "discord_bot_token", "")
    monkeypatch.setattr(s, "telegram_bot_token", "")
    assert s.discord_bot_token == ""
    assert s.telegram_bot_token == ""
    assert s.discord_enabled is False
    assert s.telegram_enabled is False