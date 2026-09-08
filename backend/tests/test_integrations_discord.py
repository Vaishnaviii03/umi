import asyncio
from types import SimpleNamespace

from app.integrations.discord.bot import build_platform_message, handle_on_message


def make_author(bot=False, ident="123", name="UmiOwner"):
    return SimpleNamespace(bot=bot, id=ident, display_name=name)


def make_channel(ident=222, name="general", send_enabled=True):
    channel = SimpleNamespace(id=ident, name=name)
    if send_enabled:
        channel.send = async_send
    return channel


async def async_send(text):
    return None


def make_message(author=None, content="hello", channel=None, guild=None):
    return SimpleNamespace(
        author=author or make_author(),
        content=content,
        channel=channel or make_channel(),
        guild=guild,
    )


def test_build_platform_message_owner_in_guild_channel():
    msg = make_message(
        guild=SimpleNamespace(id=1, name="HQ"), channel=make_channel()
    )
    pm = build_platform_message(msg)
    assert pm.platform == "discord"
    assert pm.platform_user_id == "123"
    assert pm.conversation_key == "1:222"
    assert "HQ" in pm.context_summary
    assert "#general" in pm.conversation_title


def test_build_platform_message_dm():
    msg = make_message(guild=None)
    pm = build_platform_message(msg)
    assert pm.conversation_key.startswith("dm:")
    assert pm.conversation_title == "Discord DM"


def test_build_platform_message_ignores_bots():
    assert build_platform_message(make_message(author=make_author(bot=True))) is None


def test_on_message_unknown_user_refused(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "other")
    sent = []
    channel = SimpleNamespace(id=222, name="general", send=lambda t: sent.append(t))

    def fake_respond(pm):
        return "I only respond to my owner on this platform."

    monkeypatch.setattr("app.integrations.discord.bot.respond_to", fake_respond)
    reporter = lambda status, detail=None: None  # noqa: E731

    async def scenario():
        await handle_on_message(make_message(channel=channel), reporter)
        assert sent == ["I only respond to my owner on this platform."]

    asyncio.run(scenario())


def test_on_message_owner_sends_reply(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "discord_owner_id", "123")
    sent = []
    channel = SimpleNamespace(id=222, name="general", send=lambda t: sent.append(t))

    def fake_respond(pm):
        return "hi there"

    monkeypatch.setattr("app.integrations.discord.bot.respond_to", fake_respond)
    reporter = lambda status, detail=None: None  # noqa: E731

    async def scenario():
        await handle_on_message(make_message(channel=channel), reporter)
        assert sent == ["hi there"]

    asyncio.run(scenario())


def test_on_message_skips_channel_without_send():
    channel = make_channel(send_enabled=False)
    reporter = lambda status, detail=None: None  # noqa: E731

    async def scenario():
        await handle_on_message(make_message(channel=channel), reporter)

    asyncio.run(scenario())


def test_on_message_empty_text_is_dropped():
    channel = SimpleNamespace(id=222, name="general", send=lambda t: sent.append(t))
    sent = []
    reporter = lambda status, detail=None: None  # noqa: E731

    async def scenario():
        msg = make_message(channel=channel, content="   ")
        await handle_on_message(msg, reporter)
        assert sent == []

    asyncio.run(scenario())