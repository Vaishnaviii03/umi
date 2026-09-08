from __future__ import annotations

import logging

import httpx

# httpx logs full request URLs at INFO, and the Telegram bot token lives in the
# URL path (api.telegram.org/bot<token>/...). Keep those URLs out of the logs —
# the token must never appear in output.
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramAPIError(Exception):
    """Wraps a failed Telegram Bot API call."""


class TelegramAPI:
    """Minimal async client for the official Telegram Bot API (long-poll).

    ``transport`` is injectable for tests (httpx.MockTransport). The bot token
    only ever appears inside the HTTPS base URL path to api.telegram.org.
    """

    def __init__(
        self,
        bot_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token}",
            transport=transport,
            timeout=timeout,
        )

    async def get_updates(self, offset: int | None, timeout: int = 50) -> dict:
        resp = await self._client.get(
            "/getUpdates",
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["message"]',
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_message(self, chat_id: int, text: str) -> None:
        resp = await self._client.post(
            "/sendMessage", data={"chat_id": chat_id, "text": text}
        )
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()