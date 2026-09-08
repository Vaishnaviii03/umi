import time

from app.config import settings
from app.integrations.supervisor import (
    STATUS_DISABLED,
    STATUS_ERROR,
    IntegrationSupervisor,
)


def test_disabled_when_no_tokens():
    sup = IntegrationSupervisor()
    sup.start()
    status = sup.status()
    assert status["discord"]["enabled"] is False
    assert status["telegram"]["enabled"] is False
    assert status["discord"]["status"] == STATUS_DISABLED
    sup.stop()


def test_start_never_raises_when_worker_raises(monkeypatch):
    import app.integrations.supervisor as sup_mod

    monkeypatch.setattr(settings, "discord_bot_token", "tok")

    def boom(token, reporter):
        raise RuntimeError("boom")

    monkeypatch.setitem(sup_mod._WORKER_TARGETS, "discord", boom)
    sup = IntegrationSupervisor()
    sup.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if sup.status()["discord"]["status"] == STATUS_ERROR:
            break
        time.sleep(0.02)
    assert sup.status()["discord"]["status"] == STATUS_ERROR
    sup.stop()


def test_status_has_no_token_material():
    sup = IntegrationSupervisor()
    sup.start()
    raw = str(sup.status())
    assert "bot_token" not in raw.lower()
    assert "secret" not in raw.lower()
    sup.stop()


def test_reporter_updates_status_directly(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "tok")
    sup = IntegrationSupervisor()
    reporter = sup._report("telegram")
    reporter("connected", None)
    assert sup.status()["telegram"]["status"] == "connected"
    sup.stop()


def test_stop_is_idempotent():
    sup = IntegrationSupervisor()
    sup.stop()
    sup.stop()