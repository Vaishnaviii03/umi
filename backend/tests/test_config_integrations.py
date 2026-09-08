import importlib
import os

import pytest

import app.config as config_module

_ENV_KEYS = [
    "DISCORD_APPLICATION_ID",
    "DISCORD_PUBLIC_KEY",
    "DISCORD_BOT_TOKEN",
    "DISCORD_OWNER_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_OWNER_ID",
]


@pytest.fixture()
def reload_settings(monkeypatch):
    """Set env vars, reload app.config, and restore everything afterwards."""
    original = {k: os.environ.get(k) for k in _ENV_KEYS}

    def apply(values: dict[str, str]) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        importlib.reload(config_module)

    yield apply

    for key, old in original.items():
        if old is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, old)
    importlib.reload(config_module)


def test_discord_settings_load_from_env(reload_settings):
    reload_settings(
        {
            "DISCORD_APPLICATION_ID": "11111111",
            "DISCORD_PUBLIC_KEY": "pub-key",
            "DISCORD_BOT_TOKEN": "disc-token",
            "DISCORD_OWNER_ID": "22222222",
        }
    )
    assert config_module.settings.discord_application_id == "11111111"
    assert config_module.settings.discord_public_key == "pub-key"
    assert config_module.settings.discord_bot_token == "disc-token"
    assert config_module.settings.discord_owner_id == "22222222"
    assert config_module.settings.discord_enabled is True


def test_telegram_settings_load_from_env(reload_settings):
    reload_settings({"TELEGRAM_BOT_TOKEN": "333:tok", "TELEGRAM_OWNER_ID": "444"})
    assert config_module.settings.telegram_bot_token == "333:tok"
    assert config_module.settings.telegram_owner_id == "444"
    assert config_module.settings.telegram_enabled is True


def test_integrations_disabled_when_tokens_empty(reload_settings):
    reload_settings({})
    assert config_module.settings.discord_bot_token == ""
    assert config_module.settings.telegram_bot_token == ""
    assert config_module.settings.discord_enabled is False
    assert config_module.settings.telegram_enabled is False