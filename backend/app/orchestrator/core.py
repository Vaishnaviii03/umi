import threading
import time
from collections import deque
from collections.abc import Iterator

from app.db.models import Message, utcnow
from app.db.repositories import (
    get_messages,
    get_or_create_conversation,
    retrieve_relevant_memories,
)
from app.llm.manager import (
    DEFAULT_MAX_TOKENS,
    FAST_MAX_TOKENS_TEXT,
    LLMError,
    VOICE_MAX_TOKENS,
    llm_manager,
)
from app.services.local_time import local_time_description

SYSTEM_PROMPT = (
    "You are Umi, the user's personal AI companion. Be warm, curious, and "
    "intelligent with a scientific frame of mind. Sound like a trusted friend "
    "who happens to be very knowledgeable. Be concise. Use natural, varied "
    "language — never robotic fillers like 'How may I assist you today?'."
    "Your name is Umi (pronounced 'you-me'), and when the user asks your name "
    "you introduce yourself simply as Umi — never spell it out as U-M-I or "
    "call yourself UMI. Refer to yourself by name naturally when it fits. "
    "Acknowledge what the user says, answer what they actually asked, and "
    "occasionally ask a relevant follow-up — but do NOT end every reply with a "
    "question; you are having a conversation, not conducting an interview. "
    "Adapt to the mood of the conversation. Use memories and conversation "
    "history so the conversation feels continuous."
)

# Casual/short queries and voice turns go to the fast conversational model so
# Umi answers almost instantly; longer, complex questions keep the flagship.
CASUAL_MESSAGE_MAX_CHARS = 80

# Keep active context compact for low prompt-processing latency. The tail
# matters most, so we take the newest N messages only.
VOICE_HISTORY_MESSAGES = 6
TEXT_HISTORY_MESSAGES = 10
MEMORY_LIMIT = 4
MAX_MEMORY_ITEM_CHARS = 200

# The database may be remote (e.g. hosted Postgres), where every query costs a
# network round trip. Cache the recent message tail per conversation in-process
# so repeated voice turns skip the history query entirely; the cache is
# short-lived and bounded so it never serves stale context for long.
_HISTORY_CACHE_TTL_S = 60.0
_HISTORY_CACHE_MAX_ENTRIES = 64
_CACHE_LOCK = threading.Lock()
_history_cache: dict[str, tuple[float, deque[dict]]] = {}


def _cached_history(conversation_id, history_limit: int) -> list[dict] | None:
    if conversation_id is None:
        return None
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _history_cache.get(str(conversation_id))
        if entry is not None and now - entry[0] <= _HISTORY_CACHE_TTL_S:
            return list(entry[1])[-history_limit:]
    return None


def _cache_history(conversation_id, history: list[dict]) -> None:
    if conversation_id is None:
        return
    key = str(conversation_id)
    with _CACHE_LOCK:
        if key not in _history_cache and len(_history_cache) >= _HISTORY_CACHE_MAX_ENTRIES:
            _history_cache.clear()
        _history_cache[key] = (time.monotonic(), deque(history, maxlen=TEXT_HISTORY_MESSAGES))


def _append_cached_message(conversation_id, role: str, content: str) -> None:
    if conversation_id is None:
        return
    with _CACHE_LOCK:
        entry = _history_cache.get(str(conversation_id))
        if entry is None:
            return
        entry[1].append({"role": role, "content": content})


def _build_context(db, message: str, conversation_id=None, voice: bool = False, include_memories: bool = True):
    """Return (system_prompt, memory_block, history, conversation).

    Conversation history is capped to the most recent messages and the memory
    block is trimmed so prompt time-to-first-token stays low. Memory retrieval
    is skipped for fast/casual turns (one less database round trip before the
    LLM call — they rarely need remembered facts).
    """
    time_block = f"The user's current local date and time is {local_time_description()}."

    if db is None:
        return SYSTEM_PROMPT, time_block, None, None

    conversation = get_or_create_conversation(db, conversation_id)
    history_limit = VOICE_HISTORY_MESSAGES if voice else TEXT_HISTORY_MESSAGES
    history = _cached_history(conversation.id, history_limit)
    if history is None:
        recent = get_messages(db, conversation.id, limit=24)
        history = [{"role": m.role, "content": m.content} for m in recent][-history_limit:]
        _cache_history(conversation.id, history)
    memories = (
        retrieve_relevant_memories(db, message, limit=MEMORY_LIMIT)
        if include_memories
        else []
    )

    memory_block = "\n".join(
        f"- {m.content[:MAX_MEMORY_ITEM_CHARS]}" for m in memories
    )
    context_block = f"{time_block}\n{memory_block}" if memory_block else time_block
    return SYSTEM_PROMPT, context_block, history, conversation


def _max_tokens_for(voice: bool, fast: bool) -> int:
    if voice:
        return VOICE_MAX_TOKENS
    return FAST_MAX_TOKENS_TEXT if fast else DEFAULT_MAX_TOKENS


def _is_casual(message: str) -> bool:
    """Short everyday utterances (greetings, chit-chat, quick asks) stay fast."""
    return len(message.strip()) <= CASUAL_MESSAGE_MAX_CHARS


def _persist(db, conversation, message: str, reply: str) -> str | None:
    if conversation is None:
        return None
    # Add both rows and commit once so a remote (network) database only costs a
    # single round trip instead of one flush per row.
    db.add(Message(conversation_id=conversation.id, role="user", content=message))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
    conversation.updated_at = utcnow()
    db.commit()
    _append_cached_message(conversation.id, "user", message)
    _append_cached_message(conversation.id, "assistant", reply)
    return str(conversation.id)


def handle_message(db, message: str, conversation_id=None, voice: bool = False) -> tuple[str, str | None]:
    """Central coordination point for a user request.

    - Without a database: replies with no persistence (graceful degradation).
    - With a database: injects retrieved memories + recent history into the
      LLM context, then persists both the user message and the reply.
    - `voice=True`: appends voice-specific brevity guidance and the response is
      expected to be read aloud.
    - `fast=True` (voice or short casual messages): routed to the fast model.
    - The current local time is always injected so Umi answers time questions
      from a reliable source rather than guessing.
    """
    fast = voice or _is_casual(message)
    system, context_block, history, conversation = _build_context(
        db,
        message,
        conversation_id,
        voice=voice,
        include_memories=not fast,
    )
    reply = llm_manager.generate_reply(
        message,
        system=system,
        history=history,
        memories=context_block or None,
        voice=voice,
        fast=fast,
        max_tokens=_max_tokens_for(voice, fast),
    )
    return reply, _persist(db, conversation, message, reply)


def stream_message(db, message: str, conversation_id=None, voice: bool = False) -> Iterator[tuple[str, dict]]:
    """Stream a single turn as (event, payload) pairs.

    Events:
      ("chunk", {"text": <partial reply text>})
      ("done",  {"reply": <full reply>, "conversation_id": <id|None>, "metrics": {...}})
      ("error", {"detail": <safe user-facing message>, "metrics": {...}})
    """
    fast = voice or _is_casual(message)
    system, context_block, history, conversation = _build_context(
        db,
        message,
        conversation_id,
        voice=voice,
        include_memories=not fast,
    )
    max_tokens = _max_tokens_for(voice, fast)
    metrics: dict = {}
    try:
        parts: list[str] = []
        for chunk in llm_manager.stream_reply(
            message,
            system=system,
            history=history,
            memories=context_block or None,
            voice=voice,
            fast=fast,
            max_tokens=max_tokens,
            metrics=metrics,
        ):
            parts.append(chunk)
            yield ("chunk", {"text": chunk})
    except LLMError:
        metrics["llm_failed"] = True
        yield ("error", {"detail": "Umi couldn't reach the reasoning engine right now.", "metrics": metrics})
        return

    reply = "".join(parts)
    conversation_id_out = _persist(db, conversation, message, reply)
    yield ("done", {"reply": reply, "conversation_id": conversation_id_out, "metrics": metrics})