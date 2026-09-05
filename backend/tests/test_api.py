from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_success():
    with patch("app.api.routes.handle_message", return_value=("hello back", None)):
        response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json() == {"reply": "hello back", "conversation_id": None}


def test_chat_rejects_empty_message():
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_llm_failure_returns_safe_error():
    from app.llm.manager import LLMError

    with patch("app.api.routes.handle_message", side_effect=LLMError("boom")):
        response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 502
    assert "reasoning engine" in response.json()["detail"]


def test_preflight_allowed_for_desktop_shell_origin():
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://127.0.0.1:3456",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3456"


def test_preflight_allowed_for_localhost_desktop_origin():
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3456",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3456"


def test_preflight_rejects_remote_origin_when_not_listed():
    response = client.options(
        "/chat",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400


def test_post_chat_reaches_backend_from_desktop_origin():
    with patch("app.api.routes.handle_message", return_value=("hello back", None)):
        response = client.post(
            "/chat",
            headers={"Origin": "http://127.0.0.1:3456"},
            json={"message": "hello"},
        )
    assert response.status_code == 200
    assert response.json() == {"reply": "hello back", "conversation_id": None}
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3456"


def _fake_stream(db, message, conversation_id=None, voice=False):
    yield ("chunk", {"text": "Hello"})
    yield ("chunk", {"text": " there."})
    yield (
        "done",
        {
            "reply": "Hello there.",
            "conversation_id": None,
            "metrics": {"llm_first_token_ms": 42, "llm_total_ms": 90},
        },
    )


def test_chat_stream_returns_sse_text_and_done():
    with patch("app.api.routes.stream_message", side_effect=_fake_stream):
        with client.stream("POST", "/chat/stream", json={"message": "hi"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
    assert 'data: {"text": "Hello"}' in body
    assert 'data: {"text": " there."}' in body
    assert '"reply": "Hello there."' in body
    assert '"done": true' in body


def test_chat_stream_error_event_is_safe():
    def failing_stream(db, message, conversation_id=None, voice=False):
        yield ("error", {"detail": "Umi couldn't reach the reasoning engine right now.", "metrics": {}})

    with patch("app.api.routes.stream_message", side_effect=failing_stream):
        with client.stream("POST", "/chat/stream", json={"message": "hi"}) as response:
            body = "".join(response.iter_text())
    assert response.status_code == 200
    assert '"error"' in body
    assert "Umi couldn't reach the reasoning engine right now." in body
