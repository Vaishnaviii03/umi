from __future__ import annotations

import logging

import discord

from app.integrations.shared import respond_to
from app.integrations.supervisor import STATUS_CONNECTED, STATUS_ERROR
from app.integrations.types import PlatformMessage

logger = logging.getLogger("umi.integrations.discord")


def _client_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


def build_platform_message(message) -> PlatformMessage | None:
    """Map a discord.py Message to a PlatformMessage, or None to ignore it."""
    author = getattr(message, "author", None)
    if author is None or getattr(author, "bot", False):
        return None
    channel = getattr(message, "channel", None)
    guild = getattr(message, "guild", None)
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    if guild is None:
        key = f"dm:{channel_id}"
        title = "Discord DM"
        context = "a private direct message"
    else:
        guild_name = getattr(guild, "name", "?")
        channel_name = getattr(channel, "name", "?")
        key = f"{guild.id}:{channel_id}"
        title = f"Discord · {guild_name} · #{channel_name}"[:200]
        context = f"server '{guild_name}', channel '#{channel_name}'"
    author_name = getattr(author, "display_name", None) or str(getattr(author, "id", "?"))
    return PlatformMessage(
        platform="discord",
        platform_user_id=str(getattr(author, "id", "")),
        author_name=author_name,
        text=getattr(message, "content", "") or "",
        conversation_key=key,
        conversation_title=title,
        context_summary=f"You are talking to the user via Discord in {context}.",
    )


def _can_send(channel) -> bool:
    return callable(getattr(channel, "send", None))


async def handle_on_message(message, reporter) -> None:
    """Handle one on_message event; never raises out to the gateway loop."""
    try:
        pm = build_platform_message(message)
        if pm is None or not pm.text.strip():
            return
        reply = respond_to(pm)
        if reply and _can_send(message.channel):
            await message.channel.send(reply)
    except Exception:  # noqa: BLE001
        logger.exception("[discord] message handling failed")
        reporter(STATUS_ERROR, "message handling failed")


def make_client(reporter):
    client = discord.Client(intents=_client_intents())

    @client.event
    async def on_ready():
        logger.info("[discord] gateway ready")
        reporter(STATUS_CONNECTED, None)

    @client.event
    async def on_message(message):
        await handle_on_message(message, reporter)

    return client


def run_discord_bot(bot_token: str, reporter) -> None:
    """Blocking entrypoint for the supervisor thread."""
    client = make_client(reporter)
    try:
        client.run(bot_token)
    except Exception:  # noqa: BLE001
        logger.exception("[discord] gateway connection failed")
        reporter(STATUS_ERROR, "gateway connection failed")