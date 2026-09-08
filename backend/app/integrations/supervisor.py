from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from app.config import settings

logger = logging.getLogger("umi.integrations")

STATUS_DISABLED = "disabled"
STATUS_STARTING = "starting"
STATUS_CONNECTED = "connected"
STATUS_RECONNECTING = "reconnecting"
STATUS_ERROR = "error"

# Worker entrypoints, resolved lazily (they live in the discord/telegram
# subpackages which are created by later phases). Tests can swap entries.
_WORKER_TARGETS: dict[str, Callable] = {}

WorkerTarget = Callable[[str, Callable[[str, str | None], None]], None]


@dataclass
class _Worker:
    platform: str
    thread: threading.Thread | None = None
    status: str = STATUS_DISABLED
    detail: str | None = None


def _token_for(platform: str) -> str:
    if platform == "discord":
        return settings.discord_bot_token
    return settings.telegram_bot_token


def _enabled(platform: str) -> bool:
    return bool(_token_for(platform))


def _target_for(platform: str) -> WorkerTarget:
    if platform not in _WORKER_TARGETS:
        import importlib

        if platform == "discord":
            _WORKER_TARGETS["discord"] = getattr(
                importlib.import_module("app.integrations.discord.bot"),
                "run_discord_bot",
            )
        else:
            _WORKER_TARGETS["telegram"] = getattr(
                importlib.import_module("app.integrations.telegram.poller"),
                "run_telegram_poller",
            )
    return _WORKER_TARGETS[platform]


class IntegrationSupervisor:
    """Owns the Discord/Telegram background worker threads.

    Workers are daemons so a crashed or misconfigured integration can never
    take down uvicorn. ``start``/``stop`` are idempotent and never raise.
    Status reporting never includes token material.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workers: dict[str, _Worker] = {
            "discord": _Worker("discord"),
            "telegram": _Worker("telegram"),
        }

    def start(self) -> None:
        for platform in ("discord", "telegram"):
            if _enabled(platform):
                self._spawn(platform, _target_for(platform), _token_for(platform))

    def _spawn(self, platform: str, target: WorkerTarget, token: str) -> None:
        def _wrapped() -> None:
            try:
                target(token, reporter=self._report(platform))
            except Exception:  # noqa: BLE001 — a worker must never kill the app
                logger.exception("[%s] worker stopped unexpectedly", platform)
                self._report(platform)(STATUS_ERROR, "worker stopped unexpectedly")

        self._set(platform, STATUS_STARTING, None)
        thread = threading.Thread(target=_wrapped, name=f"umi-{platform}", daemon=True)
        self._workers[platform].thread = thread
        thread.start()

    def _report(self, platform: str):
        def report(status: str, detail: str | None = None) -> None:
            self._set(platform, status, detail)

        return report

    def _set(self, platform: str, status: str, detail: str | None) -> None:
        with self._lock:
            worker = self._workers[platform]
            worker.status = status
            worker.detail = detail

    def stop(self) -> None:
        """Best-effort: threads are daemons, so shutdown is process-scoped."""
        with self._lock:
            for worker in self._workers.values():
                worker.thread = None

    def status(self) -> dict:
        with self._lock:
            return {
                name: {
                    "enabled": _enabled(name),
                    "status": worker.status if _enabled(name) else STATUS_DISABLED,
                    "detail": worker.detail,
                }
                for name, worker in self._workers.items()
            }


integration_supervisor = IntegrationSupervisor()