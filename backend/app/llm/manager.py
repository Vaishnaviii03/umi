import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Optional
import asyncio

from openai import OpenAI, OpenAIError

from app.config import settings
from app.tools import ToolContext, ToolError, ToolResult, tool_manager, tool_registry

logger = logging.getLogger("umi.llm")

# Per-turn latency telemetry (dev logging keyed by http request).
DEFAULT_MAX_TOKENS = 250
FAST_MAX_TOKENS_TEXT = 200
VOICE_MAX_TOKENS = 150


# How many LLM↔tool round trips a single turn may make before being forced to
# answer with what it has. Keeps runaway tool chains from looping forever.
TOOL_MAX_ROUNDS = 3


class LLMError(Exception):
    """Raised when the LLM provider fails to produce a response."""


@dataclass
class _ToolCallRef:
    """Lightweight stand-in for a completed tool call (name/arguments/id)."""

    id: str
    function: "_ToolCallFunctionRef"
    extra_content: dict | None = None


@dataclass
class _ToolCallFunctionRef:
    name: str
    arguments: str


VOICE_GUIDANCE = (
    "You are currently speaking out loud to the user, so keep this response "
    "brief and natural: 1-4 short sentences. Prefer conversational phrasing "
    "for casual chat. Only give a longer answer if the user explicitly asked "
    "for an explanation. Do not use lists, markdown, or bullet points. "
    "Your name is Umi (sounds like 'you-me'); never spell out U-M-I."
)


class LLMManager:
    """Provider-agnostic wrapper around the reasoning model.

    Rest of the backend talks to this interface only — never to the
    provider SDK directly — so the model can be swapped later. Casual /
    voice turns can be routed to a faster model via `fast=True` while longer,
    complex queries keep the configured flagship model.
    """

    _gemini_client: Any = None
    _primary_exhausted_until: float = 0.0

    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        self._model = settings.llm_model
        self._gemini_client = (
            OpenAI(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url)
            if settings.gemini_api_key
            else None
        )
        self._primary_exhausted_until: float = 0.0

    @staticmethod
    def _is_exhaustion_error(exc: Exception) -> bool:
        err_msg = str(exc).lower()
        return any(
            hint in err_msg
            for hint in (
                "402",
                "429",
                "insufficient credits",
                "credits",
                "quota",
                "rate limit",
                "free-models-per-day",
                "payment required",
            )
        )

    @staticmethod
    def _build_messages(
        *,
        system: str | None,
        memories: str | None,
        voice: bool,
        history: list[dict] | None,
        message: str,
    ) -> list[dict]:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        if memories:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Here are some memories about the user you may use when "
                        f"relevant:\n{memories}"
                    ),
                }
            )
        if voice:
            messages.append({"role": "system", "content": VOICE_GUIDANCE})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})
        return messages

    def _tools_payload(self) -> list[dict] | None:
        """OpenAI tool definitions from the registry, or None if none exist."""
        tools = tool_registry.openai_tools()
        return tools or None

    def _create(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        stream: bool,
        tools: list[dict] | None = None,
    ):
        """Run one completion, falling back to a tool-less request if the model
        rejects the tool payload, and seamlessly falling back to Google Gemini if
        primary OpenRouter daily credits / rate limits are exhausted."""
        if max_tokens:
            max_tokens = min(max_tokens, 250)

        now = time.time()
        # If primary OpenRouter was recently exhausted, route directly to Gemini fallback
        if self._gemini_client and now < self._primary_exhausted_until:
            return self._create_gemini(
                messages=messages,
                max_tokens=max_tokens,
                stream=stream,
                tools=tools,
            )

        try:
            return self._client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                stream=stream,
                tools=tools,
                tool_choice="auto" if tools else None,
            )
        except OpenAIError as exc:
            if self._gemini_client and self._is_exhaustion_error(exc):
                # Mark primary exhausted for 30 minutes before re-checking
                self._primary_exhausted_until = now + 1800
                logger.warning(
                    "Primary LLM (%s) quota/credits exhausted (%s). Seamlessly falling back to Google Gemini (%s).",
                    model,
                    exc,
                    settings.gemini_model,
                )
                return self._create_gemini(
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=stream,
                    tools=tools,
                )

            if tools:
                logger.warning("model %s rejected tool payload; retrying without tools", model)
                try:
                    return self._client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        stream=stream,
                    )
                except OpenAIError as inner_exc:
                    if self._gemini_client and self._is_exhaustion_error(inner_exc):
                        self._primary_exhausted_until = now + 1800
                        logger.warning(
                            "Primary LLM exhausted on retry (%s). Seamlessly falling back to Google Gemini.",
                            inner_exc,
                        )
                        return self._create_gemini(
                            messages=messages,
                            max_tokens=max_tokens,
                            stream=stream,
                            tools=None,
                        )
                    raise
            raise

    def _create_gemini(
        self,
        *,
        messages: list[dict],
        max_tokens: int,
        stream: bool,
        tools: list[dict] | None = None,
    ):
        models = [
            settings.gemini_model,
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
        ]
        seen: set[str] = set()
        candidate_models = [m for m in models if m and not (m in seen or seen.add(m))]

        last_exc: Exception | None = None
        for model in candidate_models:
            try:
                return self._gemini_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=stream,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                )
            except OpenAIError as exc:
                last_exc = exc
                err_str = str(exc).lower()
                # If tool payload was rejected, retry without tools on this model
                if tools and ("tool" in err_str or "unsupported" in err_str):
                    logger.warning("Gemini model %s rejected tool payload; retrying without tools", model)
                    try:
                        return self._gemini_client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            stream=stream,
                        )
                    except OpenAIError as inner_exc:
                        last_exc = inner_exc
                # If quota/rate limit error, try the next model candidate
                if "429" in str(exc) or "quota" in err_str or "resource_exhausted" in err_str:
                    logger.warning("Gemini model %s quota exceeded; trying next model in pool", model)
                    continue
                raise
        if last_exc:
            raise last_exc

    def _run_tool_call(self, call, db=None) -> ToolResult:
        """Validate + execute a single LLM-proposed tool call, normalizing every
        failure into a ToolResult the LLM can answer naturally about."""
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
            if not isinstance(args, dict):
                args = {}
        except json.JSONDecodeError:
            return ToolResult.failure("tool arguments were not valid JSON")
        ctx = ToolContext(user_id=str(settings.owner_id), db=db)
        try:
            return tool_manager.execute_tool(name, args, ctx)
        except ToolError as exc:
            return ToolResult.failure(str(exc), type(exc).__name__)

    def generate_reply(
        self,
        message: str,
        *,
        system: str | None = None,
        history: list[dict] | None = None,
        memories: str | None = None,
        voice: bool = False,
        fast: bool = False,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        db=None,
    ) -> str:
        messages = self._build_messages(
            system=system, memories=memories, voice=voice, history=history, message=message
        )
        tools = self._tools_payload()
        try:
            response = self._create(
                model=settings.model_for(fast),
                messages=messages,
                max_tokens=max_tokens,
                stream=False,
                tools=tools,
            )
            choice = response.choices[0].message
            tool_rounds = 0
            while choice.tool_calls:
                tool_rounds += 1
                tc_dicts = []
                for tc in choice.tool_calls:
                    extra = getattr(tc, "extra_content", None) or (getattr(tc, "model_extra", None) or {}).get("extra_content")
                    tc_dict = {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "",
                        },
                    }
                    if extra:
                        tc_dict["extra_content"] = extra
                    tc_dicts.append(tc_dict)

                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.content or None,
                        "tool_calls": tc_dicts,
                    }
                )
                for tc in choice.tool_calls:
                    result = self._run_tool_call(tc, db)
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result.to_json()}
                    )
                logger.info("[tool] turn executed %d tool call(s) (round %d)", len(choice.tool_calls), tool_rounds)
                if tool_rounds >= TOOL_MAX_ROUNDS:
                    tools = None
                response = self._create(
                    model=settings.model_for(fast),
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=False,
                    tools=tools,
                )
                choice = response.choices[0].message
        except OpenAIError as exc:
            logger.error("LLM request failed: %s", exc)
            raise LLMError("LLM provider request failed") from exc

        text = choice.content or ""
        if not text:
            raise LLMError("LLM returned an empty response")
        return text

    def stream_reply(
        self,
        message: str,
        *,
        system: str | None = None,
        history: list[dict] | None = None,
        memories: str | None = None,
        voice: bool = False,
        fast: bool = False,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        metrics: dict | None = None,
        abort_event: Optional[asyncio.Event] = None,
        db=None,
    ) -> Iterator[str]:
        """Stream the assistant's reply as text chunks (content only).

        Hidden reasoning tokens (if the provider emits them) are skipped so
        the first yielded chunk is real answer text as early as possible.
        If the model proposes tool calls instead, they are executed through the
        ToolManager and a follow-up completion streams the natural-language
        answer (bounded by ``TOOL_MAX_ROUNDS``). `metrics` is filled with
        llm_first_token_ms / llm_total_ms (+ tool_rounds) for latency logging.
        If `abort_event` is set, streaming stops and the iterator ends early.
        """
        messages = self._build_messages(
            system=system, memories=memories, voice=voice, history=history, message=message
        )
        metrics = {} if metrics is None else metrics
        started = time.perf_counter()
        first_seen = False
        tools = self._tools_payload()
        tool_rounds = 0
        try:
            while True:
                stream = self._create(
                    model=settings.model_for(fast),
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=True,
                    tools=tools,
                )
                tool_calls: dict[int, dict] = {}
                content_parts: list[str] = []
                for chunk in stream:
                    if abort_event is not None and abort_event.is_set():
                        return
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index if tc_delta.index is not None else 0
                            slot = tool_calls.setdefault(
                                idx, {"id": "", "name": "", "arguments": "", "extra_content": None}
                            )
                            if tc_delta.id:
                                slot["id"] = tc_delta.id
                            fn = tc_delta.function
                            if fn is not None:
                                if fn.name:
                                    slot["name"] += fn.name
                                if fn.arguments:
                                    slot["arguments"] += fn.arguments
                            extra = getattr(tc_delta, "extra_content", None) or (getattr(tc_delta, "model_extra", None) or {}).get("extra_content")
                            if extra:
                                slot["extra_content"] = extra
                    if delta.content:
                        content_parts.append(delta.content)
                        if not tool_calls:
                            if not first_seen:
                                first_seen = True
                                metrics["llm_first_token_ms"] = round(
                                    (time.perf_counter() - started) * 1000
                                )
                            yield delta.content
                if not tool_calls:
                    break

                completed = []
                for index in sorted(tool_calls):
                    slot = tool_calls[index]
                    completed.append(
                        _ToolCallRef(
                            id=slot["id"] or f"call_{index}",
                            function=_ToolCallFunctionRef(
                                name=slot["name"],
                                arguments=slot["arguments"] or "{}",
                            ),
                            extra_content=slot.get("extra_content"),
                        )
                    )
                tc_dicts = []
                for call in completed:
                    tc_dict = {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    if call.extra_content:
                        tc_dict["extra_content"] = call.extra_content
                    tc_dicts.append(tc_dict)

                messages.append(
                    {
                        "role": "assistant",
                        "content": "".join(content_parts) or None,
                        "tool_calls": tc_dicts,
                    }
                )
                for call in completed:
                    result = self._run_tool_call(call, db)
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": result.to_json()}
                    )
                tool_rounds += 1
                metrics["tool_rounds"] = tool_rounds
                logger.info("[tool] turn executed %d tool call(s) (round %d)", len(completed), tool_rounds)
                if tool_rounds >= TOOL_MAX_ROUNDS:
                    tools = None  # force the model to answer from what it has
        except OpenAIError as exc:
            logger.error("LLM stream request failed: %s", exc)
            raise LLMError("LLM provider request failed") from exc
        finally:
            metrics["llm_total_ms"] = round((time.perf_counter() - started) * 1000)


llm_manager = LLMManager()