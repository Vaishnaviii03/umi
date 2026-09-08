from __future__ import annotations

import asyncio
import logging

from app.integrations.shared import respond_to
from app.integrations.supervisor import (
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_RECONNECTING,
)
from app.integrations.telegram.telegram import TelegramAPI
from app.integrations.types import PlatformMessage

logger = logging.getLogger("umi.integrations.telegram")


def build_platform_message(update: dict) -> PlatformMessage | None:
    """Normalize one Telegram update into a PlatformMessage, or None to skip."""
    message = update.get("message") or {}
    from_user = message.get("from") or {}
    chat = message.get("chat") or {}
    text = message.get("text") or ""
    if not from_user.get("id") or not chat.get("id") or not text:
        return None
    chat_name = (
        chat.get("title")
        or chat.get("username")
        or chat.get("first_name")
        or f"chat {chat['id']}"
    )
    first = from_user.get("first_name") or ""
    last = from_user.get("last_name") or ""
    author_name = f"{first} {last}".strip() or str(from_user["id"])
    return PlatformMessage(
        platform="telegram",
        platform_user_id=str(from_user["id"]),
        author_name=author_name,
        text=text,
        conversation_key=str(chat["id"]),
        conversation_title=f"Telegram · {chat_name}"[:200],
        context_summary=(
            f"You are talking to the user via Telegram in chat '{chat_name}'."
        ),
    )


def _chat_id(message: PlatformMessage) -> int:
    return int(message.conversation_key)


async def poll_forever(
    api: TelegramAPI,
    reporter,
    *,
    max_iterations: int | None = None,
    backoff_base: float = 4.0,
) -> None:
    """Long-poll Telegram updates and pipe messages through ``respond_to``.

    Offset-based acking gives at-least-once delivery. Network failures flip to
    RECONNECTING with exponential backoff and resume; a 401 (invalid token)
    marks ERROR and stops. Tokens are never logged.
    """
    offset: int | None = None
    failures = 0
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        try:
            data = await api.get_updates(offset)
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                logger.error("[telegram] unauthorized (check the bot token)")
                reporter(STATUS_ERROR, "invalid bot token")
                return
            failures += 1
            backoff = min(60.0, backoff_base * (2 ** (failures - 1)))
            logger.warning("[telegram] polling error; reconnect in %.1fs", backoff)
            reporter(STATUS_RECONNECTING)
            await asyncio.sleep(backoff)
            continue

        failures = 0
        reporter(STATUS_CONNECTED, None)
        if not data.get("ok"):
            reporter(STATUS_ERROR, "Telegram API returned an error")
            return
        for update in data.get("result") or []:
            update_id = update.get("update_id")
            if update_id is not None:
                offset = update_id + 1
            message = build_platform_message(update)
            if message is None:
                continue
            try:
                reply = respond_to(message)
            except Exception:
                logger.exception("[telegram] message handling failed")
                continue
            if reply:
                try:
                    await api.send_message(_chat_id(message), reply)
                except Exception:
                    logger.exception("[telegram] failed to send reply")


def run_telegram_poller(
    bot_token: str,
    reporter,
    transport=None,
) -> None:
    """Blocking entrypoint for the supervisor thread (own event loop)."""
    asyncio.run(_main(bot_token, reporter, transport))


async def _main(bot_token: str, reporter, transport=None) -> None:
    api = TelegramAPI(bot_token, transport=transport)
    try:
        await poll_forever(api, reporter)
    finally:
        await api.aclose()