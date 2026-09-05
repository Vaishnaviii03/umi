"""Phase 3 — LLM tool-calling loop tests.

A mocked OpenAI client drives the LLMManager through tool-call rounds (both
non-streaming and streaming), verifying the manager executes real registry
tools and routes results back to the model.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.llm.manager import LLMManager, TOOL_MAX_ROUNDS
from app.tools import ToolResult


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(tc_id, name, arguments):
    return SimpleNamespace(
        id=tc_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _completion(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _chunk(content=None, tool_call=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_call)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_chunk(tc_id, name, arguments):
    return [
        SimpleNamespace(
            index=0,
            id=tc_id,
            function=SimpleNamespace(name=name, arguments=arguments),
        )
    ]


def _manager_with(client: MagicMock) -> LLMManager:
    manager = LLMManager.__new__(LLMManager)
    manager._client = client
    return manager


def _messages_for(client: MagicMock, call_index: int) -> list[dict]:
    called = client.chat.completions.create.call_args_list[call_index]
    return called.kwargs["messages"]


@pytest.fixture(autouse=True)
def _tools_enabled():
    from app.config import settings

    settings.tools_enabled = True


# --------------------------------------------------------------------------- #
# generate_reply (non-streaming)
# --------------------------------------------------------------------------- #
def test_generate_reply_executes_tool_then_answers_naturally():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _completion(
            _message(
                tool_calls=[
                    _tool_call("call_1", "calculate", '{"expression": "12 * 3"}')
                ]
            )
        ),
        _completion(_message(content="The answer is 36.")),
    ]
    manager = _manager_with(client)

    reply = manager.generate_reply("12 times 3?")

    assert reply == "The answer is 36."
    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 2
    tool_messages = [m for m in _messages_for(client, 1) if m["role"] == "tool"]
    assert len(tool_messages) == 1
    result = json.loads(tool_messages[0]["content"])
    assert result["status"] == "success"
    assert result["data"]["result"] == 36.0
    assert calls[1].kwargs.get("tool_choice") == "auto"


def test_generate_reply_surfaces_tool_failure_to_model():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _completion(
            _message(tool_calls=[_tool_call("call_1", "missing_tool", '{"x": 1}')])
        ),
        _completion(_message(content="I couldn't do that.")),
    ]
    manager = _manager_with(client)

    reply = manager.generate_reply("do the thing")

    assert reply == "I couldn't do that."
    tool_messages = [m for m in _messages_for(client, 1) if m["role"] == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["status"] == "error"


def test_generate_reply_plain_answer_no_tool_call():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        _message(content="Hello there!")
    )
    manager = _manager_with(client)

    assert manager.generate_reply("hi") == "Hello there!"
    client.chat.completions.create.assert_called_once()


# --------------------------------------------------------------------------- #
# stream_reply
# --------------------------------------------------------------------------- #
def test_stream_reply_executes_tool_and_streams_final_answer():
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        # First stream: name/id arrive on the first delta, args continue later.
        iter(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=_tool_chunk(
                                    "call_s", "calculate", '{"expression": "2 + 2"'
                                ),
                            )
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id=None,
                                        function=SimpleNamespace(name=None, arguments="}"),
                                    )
                                ],
                            )
                        )
                    ]
                ),
            ]
        ),
        iter([_chunk(content="Four!"), _chunk(content=" What?"), _chunk(content=None)]),
    ]
    manager = _manager_with(client)
    metrics: dict = {}

    streamed = list(
        manager.stream_reply(
            "what is 2+2?", system="sys", max_tokens=64, metrics=metrics
        )
    )

    assert streamed == ["Four!", " What?"]
    assert metrics.get("tool_rounds") == 1
    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 2
    tool_messages = [m for m in _messages_for(client, 1) if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"]) == {
        "status": "success",
        "data": {"expression": "2 + 2", "result": 4.0},
    }


def test_stream_reply_plain_answer_stays_single_pass():
    client = MagicMock()
    client.chat.completions.create.return_value = iter(
        [_chunk(content="Hi "), _chunk(content="there!")]
    )
    manager = _manager_with(client)

    streamed = list(manager.stream_reply("hi", system="sys", max_tokens=64))

    assert streamed == ["Hi ", "there!"]
    client.chat.completions.create.assert_called_once()


def test_stream_reply_tool_round_limit_forces_final_pass_without_tools():
    client = MagicMock()
    tool_rounds = [iter([_chunk(tool_call=_tool_chunk("call_r", "get_time", "{}"))]) for _ in range(TOOL_MAX_ROUNDS)]
    client.chat.completions.create.side_effect = tool_rounds + [
        iter([_chunk(content="It's early.")])
    ]

    manager = _manager_with(client)
    metrics: dict = {}

    streamed = list(manager.stream_reply("time?", system="sys", max_tokens=64, metrics=metrics))

    assert streamed == ["It's early."]
    assert metrics.get("tool_rounds") == 3


# --------------------------------------------------------------------------- #
# robustness
# --------------------------------------------------------------------------- #
def test_stream_reply_tool_arguments_invalid_json_is_safe():
    from openai import OpenAIError

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        iter([_chunk(tool_call=_tool_chunk("call_b", "calculate", "not-json"))]),
        iter([_chunk(content="Sorry, I couldn't parse that.")]),
    ]
    manager = _manager_with(client)

    streamed = list(manager.stream_reply("calc", system="sys", max_tokens=64))

    assert streamed == ["Sorry, I couldn't parse that."]
    tool_messages = [m for m in _messages_for(client, 1) if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"])["status"] == "error"


def test_create_falls_back_without_tools_when_provider_rejects():
    from openai import OpenAIError

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        OpenAIError("tools unsupported"),
        _completion(_message(content="works")),
    ]
    manager = _manager_with(client)

    assert manager.generate_reply("hi") == "works"
    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["tools"] is not None
    assert "tools" not in calls[1].kwargs
    # the follow-up stream/normal path would omit tools as well
    assert "tool_choice" not in calls[1].kwargs


def test_run_tool_call_invalid_arguments_returns_safe_failure():
    from app.llm.manager import _ToolCallRef, _ToolCallFunctionRef

    manager = _manager_with(MagicMock())
    result = manager._run_tool_call(
        _ToolCallRef(id="c", function=_ToolCallFunctionRef(name="calculate", arguments="{oops"))
    )
    assert isinstance(result, ToolResult)
    assert result.status == "error"