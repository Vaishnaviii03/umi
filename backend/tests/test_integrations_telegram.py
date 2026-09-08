import asyncio
import logging

import httpx

from app.integrations.telegram.poller import build_platform_message, poll_forever
from app.integrations.telegram.telegram import TelegramAPI


def _updates_payload(updates):
    return {"ok": True, "result": updates}


def test_build_platform_message_owner_message():
    update = {
        "update_id": 7,
        "message": {
            "message_id": 1,
            "from": {"id": 42, "first_name": "V"},
            "chat": {"id": 99, "username": "umi_hq"},
            "text": "hello",
        },
    }
    pm = build_platform_message(update)
    assert pm is not None
    assert pm.platform == "telegram"
    assert pm.platform_user_id == "42"
    assert pm.conversation_key == "99"
    assert "umi_hq" in pm.context_summary


def test_build_platform_message_ignores_empty():
    assert build_platform_message({}) is None
    assert build_platform_message({"message": {"from": {"id": 1}, "chat": {"id": 2}}}) is None


def test_poll_round_trip_sends_reply(monkeypatch):
    async def scenario():
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/getUpdates"):
                return httpx.Response(
                    200,
                    json=_updates_payload(
                        [
                            {
                                "update_id": 5,
                                "message": {
                                    "message_id": 1,
                                    "from": {"id": "own", "first_name": "V"},
                                    "chat": {"id": 99, "username": "umi_hq"},
                                    "text": "hi",
                                },
                            }
                        ]
                    ),
                )
            if request.url.path.endswith("/sendMessage"):
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404, json={})

        api = TelegramAPI("T:tok", transport=httpx.MockTransport(handler))
        sent = []

        async def fake_send(chat_id, text):
            sent.append((chat_id, text))

        monkeypatch.setattr(api, "send_message", fake_send)

        calls = {"n": 0, "replies": []}

        def fake_respond(pm):
            calls["n"] += 1
            calls["replies"].append(pm.text)
            return "reply-here"

        monkeypatch.setattr("app.integrations.telegram.poller.respond_to", fake_respond)

        statuses = []
        reporter = lambda status, detail=None: statuses.append(status)  # noqa: E731

        await poll_forever(api, reporter, max_iterations=1, backoff_base=0)
        assert calls["n"] == 1
        assert calls["replies"] == ["hi"]
        assert sent == [(99, "reply-here")]
        assert "connected" in statuses

    asyncio.run(scenario())


def test_poll_401_marks_error_and_stops(monkeypatch, caplog):
    async def scenario():
        def handler(request):
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

        api = TelegramAPI("SNEAKY:tok-value", transport=httpx.MockTransport(handler))
        statuses = []
        reporter = lambda status, detail=None: statuses.append(status)  # noqa: E731
        with caplog.at_level(logging.DEBUG):
            await poll_forever(api, reporter, max_iterations=5, backoff_base=0)
        assert statuses[-1] == "error"
        assert "SNEAKY" not in caplog.text

    asyncio.run(scenario())


def test_poll_retries_after_network_error():
    async def scenario():
        state = {"calls": 0}

        def handler(request):
            state["calls"] += 1
            if state["calls"] == 1:
                raise httpx.ConnectError("down")
            return httpx.Response(200, json=_updates_payload([]))

        api = TelegramAPI("T:tok", transport=httpx.MockTransport(handler))
        statuses = []
        reporter = lambda status, detail=None: statuses.append(status)  # noqa: E731
        await poll_forever(api, reporter, max_iterations=2, backoff_base=0)
        assert state["calls"] == 2
        assert "reconnecting" in statuses
        assert "connected" in statuses

    asyncio.run(scenario())