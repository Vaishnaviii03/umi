import threading
import time
from collections import deque
from collections.abc import Iterator

from app.db.models import Message, utcnow
from app.db.repositories import (
    claim_greeting,
    evaluate_proactive_entitlement,
    get_messages,
    get_or_create_conversation,
    record_proactive,
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
from app.services.knowledge_service import get_knowledge_service, KnowledgeContext

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

# Proactive (idle) openers: the text the model sees as the triggering message
# when Umi starts a conversation unprompted. Keeps the spawner honest — Umi can
# never use the idle path to answer a user turn.
PROACTIVE_OPENER = (
    "[Umi is opening this conversation unprompted — the owner has not typed or "
    "spoken anything. Greet lightly, acknowledge the last topic if there is "
    "one, stay brief, and end by inviting a short reply.]"
)

PROACTIVE_GUIDANCE = (
    "This turn is proactive: you are starting the conversation on your own "
    "because the owner has been quiet. Keep it short and natural, and do not "
    "ask a barrage of questions — a single easy reply is enough."
)


class ProactiveNotAllowed(Exception):
    """Raised when an idle/proactive turn violates the idle policy."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason

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


def _build_context(
    db,
    message: str,
    conversation_id=None,
    voice: bool = False,
    include_memories: bool = True,
    include_greeting: bool | None = None,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    conversation_title: str = "Conversation",
    platform_context: str | None = None,
    proactive: bool = False,
):
    """Return (system_prompt, context_block, history, conversation, created_now).

    Builds context with boss profile, relevant memories, and optional greeting.
    ``include_greeting=None`` (the default) means "greet only when the
    conversation was actually created on this request" — a resumed conversation
    never re-triggers the greeting. Platform adapters pass ``platform_context``
    (appended to the system prompt) and a ``source``/``conversation_key`` so
    each external channel gets its own isolated conversation thread.
    """
    system = SYSTEM_PROMPT if not platform_context else f"{SYSTEM_PROMPT}\n\n{platform_context}"
    if proactive:
        system = f"{system}\n\n{PROACTIVE_GUIDANCE}"
    time_block = f"The user's current local date and time is {local_time_description()}."

    if db is None:
        return system, time_block, None, None, False

    conversation = get_or_create_conversation(
        db,
        conversation_id,
        source=source,
        conversation_key=conversation_key,
        title=conversation_title,
    )
    # The creator marker is transient and request-scoped: consume it so the
    # same in-memory object (identity map) never reports "created now" again.
    created_now = bool(getattr(conversation, "_was_created", False))
    try:
        delattr(conversation, "_was_created")
    except AttributeError:
        pass
    if include_greeting is None:
        # Greet only a genuinely fresh conversation that hasn't already been
        # greeted (e.g. by the desktop's spoken launch greeting).
        include_greeting = created_now and conversation.last_greeted_at is None
    history_limit = VOICE_HISTORY_MESSAGES if voice else TEXT_HISTORY_MESSAGES
    history = _cached_history(conversation.id, history_limit)
    if history is None:
        recent = get_messages(db, conversation.id, limit=24)
        history = [{"role": m.role, "content": m.content} for m in recent][-history_limit:]
        _cache_history(conversation.id, history)

    # Use knowledge service for profile-aware context
    knowledge = get_knowledge_service()
    knowledge_context = knowledge.build_context(
        user_message=message,
        db=db,
        include_greeting=include_greeting,
        greeting_context="voice_chat" if voice else "text_chat",
    )

    # Build memory block from relevant memories
    memory_lines = []
    if knowledge_context.relevant_memories:
        memory_lines.extend(f"- {m[:MAX_MEMORY_ITEM_CHARS]}" for m in knowledge_context.relevant_memories)

    # Add profile context
    profile_text = knowledge_context.profile_summary

    # Build context block
    context_parts = [time_block, profile_text]
    if memory_lines:
        context_parts.append("\n".join(memory_lines))
    if knowledge_context.greeting:
        context_parts.insert(0, f"[Greeting: {knowledge_context.greeting}]")

    context_block = "\n\n".join(context_parts)
    return system, context_block, history, conversation, created_now


def _max_tokens_for(voice: bool, fast: bool) -> int:
    if voice:
        return VOICE_MAX_TOKENS
    return FAST_MAX_TOKENS_TEXT if fast else DEFAULT_MAX_TOKENS


def _is_casual(message: str) -> bool:
    """Short everyday utterances (greetings, chit-chat, quick asks) stay fast."""
    return len(message.strip()) <= CASUAL_MESSAGE_MAX_CHARS


def _persist(
    db, conversation, message: str, reply: str, proactive: bool = False
) -> str | None:
    if conversation is None:
        return None
    if not proactive:
        # A proactive opener never fabricates a user message — only the reply
        # is stored so conversation history stays truthful.
        db.add(Message(conversation_id=conversation.id, role="user", content=message))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
    conversation.updated_at = utcnow()
    db.commit()
    if not proactive:
        _append_cached_message(conversation.id, "user", message)
    _append_cached_message(conversation.id, "assistant", reply)
    return str(conversation.id)


def _ensure_proactive_allowed(db, conversation, created_now: bool) -> None:
    """Enforce the idle policy; raise ``ProactiveNotAllowed`` when refused."""
    if created_now:
        raise ProactiveNotAllowed("not-idle-yet")
    decision = evaluate_proactive_entitlement(db, conversation)
    if not decision.can_engage:
        raise ProactiveNotAllowed(decision.reason)


def handle_message(
    db,
    message: str,
    conversation_id=None,
    voice: bool = False,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    conversation_title: str = "Conversation",
    platform_context: str | None = None,
    include_greeting: bool | None = None,
    proactive: bool = False,
) -> tuple[str, str | None]:
    """Central coordination point for a user request.

    - Without a database: replies with no persistence (graceful degradation).
    - With a database: injects retrieved memories + recent history into the
      LLM context, then persists both the user message and the reply.
    - `voice=True`: appends voice-specific brevity guidance and the response is
      expected to be read aloud.
    - `fast=True` (voice or short casual messages): routed to the fast model.
    - `proactive=True`: an idle opener — the idle policy is enforced first and
      no user message is fabricated; only the reply is persisted.
    - The current local time is always injected so Umi answers time questions
      from a reliable source rather than guessing.
    """
    fast = voice or _is_casual(message)
    knowledge = get_knowledge_service()
    is_profile_query = knowledge._is_profile_query(message)
    if proactive:
        include_greeting = False

    system, context_block, history, conversation, created_now = _build_context(
        db,
        message,
        conversation_id,
        voice=voice,
        include_memories=not fast,
        include_greeting=include_greeting,
        source=source,
        conversation_key=conversation_key,
        conversation_title=conversation_title,
        platform_context=platform_context,
        proactive=proactive,
    )
    if proactive:
        _ensure_proactive_allowed(db, conversation, created_now)
    if include_greeting is not False and created_now:
        # A genuinely new conversation is greeted exactly once; stamp the
        # entitlement so a relaunch inside the greeting window stays silent.
        claim_greeting(db, conversation)
    llm_message = PROACTIVE_OPENER if proactive else message
    reply = llm_manager.generate_reply(
        llm_message,
        system=system,
        history=history,
        memories=context_block or None,
        voice=voice,
        fast=fast,
        max_tokens=_max_tokens_for(voice, fast),
        db=db,
    )
    if proactive:
        record_proactive(db, conversation)
    return reply, _persist(db, conversation, message, reply, proactive=proactive)


def stream_message(
    db,
    message: str,
    conversation_id=None,
    voice: bool = False,
    abort_event=None,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    conversation_title: str = "Conversation",
    platform_context: str | None = None,
    proactive: bool = False,
) -> Iterator[tuple[str, dict]]:
    """Stream a single turn as (event, payload) pairs.

    Events:
      ("chunk", {"text": <partial reply text>})
      ("done",  {"reply": <full reply>, "conversation_id": <id|None>, "metrics": {...}})
      ("error", {"detail": <safe user-facing message>, "metrics": {...}})
    A refused proactive turn yields ("error", {"code": "proactive-denied", ...}).
    """
    fast = voice or _is_casual(message)
    knowledge = get_knowledge_service()
    is_profile_query = knowledge._is_profile_query(message)

    system, context_block, history, conversation, created_now = _build_context(
        db,
        message,
        conversation_id,
        voice=voice,
        include_memories=not fast,
        source=source,
        conversation_key=conversation_key,
        conversation_title=conversation_title,
        platform_context=platform_context,
        proactive=proactive,
    )
    if proactive:
        try:
            _ensure_proactive_allowed(db, conversation, created_now)
        except ProactiveNotAllowed as exc:
            yield ("error", {"detail": exc.reason, "code": "proactive-denied", "metrics": {}})
            return
    if created_now:
        claim_greeting(db, conversation)
    max_tokens = _max_tokens_for(voice, fast)
    metrics: dict = {}
    try:
        parts: list[str] = []
        for chunk in llm_manager.stream_reply(
            PROACTIVE_OPENER if proactive else message,
            system=system,
            history=history,
            memories=context_block or None,
            voice=voice,
            fast=fast,
            max_tokens=max_tokens,
            metrics=metrics,
            abort_event=abort_event,
            db=db,
        ):
            parts.append(chunk)
            yield ("chunk", {"text": chunk})
    except LLMError:
        metrics["llm_failed"] = True
        yield ("error", {"detail": "Umi couldn't reach the reasoning engine right now.", "metrics": metrics})
        return

    reply = "".join(parts)
    if proactive:
        record_proactive(db, conversation)
    if proactive:
        metrics["proactive"] = True
    conversation_id_out = _persist(db, conversation, message, reply, proactive=proactive)
    yield ("done", {"reply": reply, "conversation_id": conversation_id_out, "metrics": metrics})