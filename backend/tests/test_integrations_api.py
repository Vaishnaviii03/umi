import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.integrations.supervisor import (
    STATUS_CONNECTED,
    STATUS_DISABLED,
    integration_supervisor,
)
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _no_worker_threads():
    integration_supervisor.stop()
    yield
    integration_supervisor.stop()


def test_status_reports_disabled_without_tokens():
    body = client.get("/integrations/status").json()
    assert body["discord"]["enabled"] is False
    assert body["telegram"]["enabled"] is False
    assert body["discord"]["status"] == STATUS_DISABLED
    assert body["telegram"]["status"] == STATUS_DISABLED


def test_status_reflects_supervisor_state(monkeypatch):
    monkeypatch.setattr(settings, "discord_bot_token", "disc-token")
    monkeypatch.setattr(settings, "telegram_bot_token", "tg-token")
    integration_supervisor._set("discord", STATUS_CONNECTED, None)
    integration_supervisor._set("telegram", STATUS_CONNECTED, None)
    body = client.get("/integrations/status").json()
    assert body["discord"]["enabled"] is True
    assert body["discord"]["status"] == STATUS_CONNECTED
    assert body["telegram"]["enabled"] is True
    assert body["telegram"]["status"] == STATUS_CONNECTED


def test_status_never_leaks_token_material(monkeypatch):
    monkeypatch.setattr(settings, "discord_bot_token", "disc-super-secret")
    monkeypatch.setattr(settings, "telegram_bot_token", "tg-super-secret")
    raw = client.get("/integrations/status").content.decode()
    assert "disc-super-secret" not in raw
    assert "tg-super-secret" not in raw
    assert "bot_token" not in raw