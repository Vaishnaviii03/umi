import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session  # type: ignore[reportMissingImports]

from app.db import models
from app.db.repositories import (
    claim_greeting,
    create_memory,
    create_task,
    delete_memory,
    delete_task,
    get_conversation,
    get_or_create_conversation,
    get_messages,
    greeting_owed,
    list_conversations,
    list_memories,
    list_tasks,
    update_task,
)
from app.db.session import get_db
from app.llm.manager import LLMError
from app.orchestrator.core import (
    CASUAL_MESSAGE_MAX_CHARS,
    ProactiveNotAllowed,
    handle_message,
    stream_message,
)
from app.services.elevenlabs_token import ElevenLabsTokenError, token_minter
from app.services.idle_policy import idle_policy_payload
from app.services.local_tts import TTSError, tts_service
from app.tools import tool_manager
from app.tools.tasks import parse_due_at as _parse_due_at
from app.tools.base import ToolExecutionError

logger = logging.getLogger("umi.api")

router = APIRouter()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)
    conversation_id: str | None = None
    voice: bool = False
    # Phase 9 — an idle/proactive opener. True means "no user message exists";
    # the backend enforces the idle policy and generates Umi's opening line.
    proactive: bool = False

    @model_validator(mode="after")
    def _message_required_unless_proactive(self):
        if not self.message.strip() and not self.proactive:
            raise ValueError("message must not be empty")
        return self


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str | None = None


class SessionOut(BaseModel):
    conversation_id: str
    resumed: bool
    greeting: dict
    idle: dict | None
    server_time: str


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: str


class MemoryOut(BaseModel):
    id: str
    content: str
    created_at: str
    updated_at: str


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TaskOut(BaseModel):
    id: str
    title: str
    status: str
    due_at: str | None
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: str | None = Field(default=None, max_length=64)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: str | None = Field(default=None, max_length=64)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def _status_must_be_valid(cls, value: str | None) -> str | None:
        if value is not None and value not in ("pending", "done"):
            raise ValueError("status must be 'pending' or 'done'")
        return value


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail=f"{label} not found")


def require_db(db: Session | None) -> None:
    if db is None:
        raise HTTPException(status_code=503, detail="Umi's database isn't configured yet.")


def _conversation_out(conv: models.Conversation) -> ConversationOut:
    return ConversationOut(
        id=str(conv.id),
        title=conv.title,
        updated_at=conv.updated_at.isoformat(),
    )


def _message_out(msg: models.Message) -> MessageOut:
    return MessageOut(
        id=str(msg.id),
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at.isoformat(),
    )


def _memory_out(mem: models.Memory) -> MemoryOut:
    return MemoryOut(
        id=str(mem.id),
        content=mem.content,
        created_at=mem.created_at.isoformat(),
        updated_at=mem.updated_at.isoformat(),
    )


def _task_out(task: models.Task) -> TaskOut:
    return TaskOut(
        id=str(task.id),
        title=task.title,
        status=task.status,
        due_at=task.due_at.isoformat() if task.due_at is not None else None,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


def _due_at_value(value: str | None):
    """Parse an ISO due date for API input, or 422 on garbage."""
    if value is None:
        return None
    try:
        return _parse_due_at(value)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/tools")
def list_tools() -> dict:
    """Public catalog of available tools (metadata only — no secrets)."""
    return {"tools": tool_manager.catalog(), "enabled": True}


def _proactive_denied_detail(reason: str) -> str:
    """Map a policy reason to a friendly, internal-free user message."""
    friendly = {
        "disabled": "I'm keeping quiet today — proactive greetings are off.",
        "not-idle-yet": "You just said something — I'll stay out of the way.",
        "outside-active-hours": "It's outside my active hours — I'll wait.",
        "within-cooldown": "I spoke up a moment ago — one opener at a time.",
        "hourly-cap-reached": "I've already reached out enough for now.",
    }
    return friendly.get(reason, "I'd rather not interrupt right now.")


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        reply, conversation_id = handle_message(
            db,
            payload.message,
            payload.conversation_id,
            voice=payload.voice,
            proactive=payload.proactive,
        )
    except ProactiveNotAllowed as exc:
        raise HTTPException(
            status_code=429,
            detail=_proactive_denied_detail(exc.reason),
        )
    except LLMError:
        logger.exception("chat request failed")
        raise HTTPException(status_code=502, detail="Umi couldn't reach the reasoning engine right now.")
    return ChatResponse(reply=reply, conversation_id=conversation_id)


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream the assistant's reply token-by-token over Server-Sent Events.

    The frontend reads real model text as it is generated and can start
    sentence-level TTS immediately instead of waiting for the full reply.
    """
    started = time.perf_counter()

    def generate():
        try:
            for event, data in stream_message(
                db,
                payload.message,
                payload.conversation_id,
                voice=payload.voice,
                proactive=payload.proactive,
            ):
                if event == "chunk":
                    yield _sse_event({"text": data["text"]})
                elif event == "error":
                    metrics = dict(data.get("metrics") or {})
                    metrics["chat_request_ms"] = round((time.perf_counter() - started) * 1000)
                    metrics["turn_failed"] = True
                    logger.info("[latency] chat turn failed %s", metrics)
                    detail = (
                        _proactive_denied_detail(data["detail"])
                        if data.get("code") == "proactive-denied"
                        else data["detail"]
                    )
                    yield _sse_event({"error": detail, "code": data.get("code")})
                elif event == "done":
                    metrics = dict(data.get("metrics") or {})
                    metrics["chat_request_ms"] = round((time.perf_counter() - started) * 1000)
                    logger.info(
                        "[latency] chat turn done conversation_id=%s greeted=%s proactive=%s fast=%s voice=%s "
                        "chat_request_ms=%s llm_first_token_ms=%s llm_total_ms=%s reply_chars=%s",
                        data.get("conversation_id"),
                        metrics.get("greeted"),
                        metrics.get("proactive"),
                        payload.voice or len(payload.message) <= CASUAL_MESSAGE_MAX_CHARS,
                        payload.voice,
                        metrics.get("chat_request_ms"),
                        metrics.get("llm_first_token_ms"),
                        metrics.get("llm_total_ms"),
                        len(data["reply"]),
                    )
                    yield _sse_event(
                        {
                            "done": True,
                            "reply": data["reply"],
                            "conversation_id": data["conversation_id"],
                        }
                    )
        except LLMError:
            logger.exception("chat stream failed")
            yield _sse_event({"error": "Umi couldn't reach the reasoning engine right now."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/stt/token")
def stt_token() -> dict:
    """Mint a short-lived ElevenLabs token for client-side realtime STT.

    The real API key stays on the backend; the browser receives only a
    single-use, ~15-minute token consumed on first connection. If STT isn't
    configured or the mint fails, the frontend gracefully falls back to the
    browser's Web Speech API — so the voice session always has a working path.
    """
    if not token_minter.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Umi's live voice input isn't configured — text and browser voice still works.",
        )
    try:
        token = token_minter.mint()
    except ElevenLabsTokenError:
        logger.exception("stt token request failed")
        raise HTTPException(
            status_code=502,
            detail="Umi's live voice input isn't available right now — browser voice still works.",
        )
    return {"token": token}


@router.post("/tts")
def text_to_speech(payload: TTSRequest) -> Response:
    """Synthesize Umi's reply locally with pyttsx3 and return WAV bytes.

    All synthesis happens on this machine via the macOS system speech engine —
    no external TTS API, no key, no network call. Kept separate from /chat so
    the text response always succeeds even when voice synthesis is unavailable.
    Failures degrade to a safe message — provider internals never reach the
    client. Voice/rate/volume are recorded in the backend logs by the service.
    """
    if not tts_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Umi's voice isn't configured yet — text response still works.",
        )
    metrics: dict = {}
    started = time.perf_counter()
    try:
        audio = tts_service.synthesize(payload.text, metrics=metrics)
    except TTSError as exc:
        logger.exception("tts request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Umi's voice isn't available right now — text response still works.",
        )
    logger.info(
        "[latency] tts done tts_first_audio_ms=%s tts_total_ms=%s chars=%s",
        metrics.get("tts_first_audio_ms"),
        round((time.perf_counter() - started) * 1000),
        len(payload.text),
    )
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
        status_code=status.HTTP_200_OK,
    )


@router.get("/tts/voices")
def list_tts_voices() -> dict:
    """Diagnostic: list locally available speech voices (ids/names only)."""
    if not tts_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Umi's voice isn't configured yet — text response still works.",
        )
    try:
        return {
            "default_voice": tts_service.current_voice(),
            "total": len(tts_service.list_voices()),
            "voices": tts_service.list_voices(),
        }
    except TTSError as exc:
        logger.exception("voices request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Umi's voice isn't available right now — text response still works.",
        )


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(db: Session = Depends(get_db)) -> list[ConversationOut]:
    require_db(db)
    return [_conversation_out(conv) for conv in list_conversations(db)]


@router.get("/conversations/active/messages", response_model=list[MessageOut])
def active_conversation_messages(db: Session = Depends(get_db)) -> list[MessageOut]:
    require_db(db)
    conversation = get_or_create_conversation(db, None)
    return [_message_out(m) for m in get_messages(db, conversation.id)]


@router.get("/session", response_model=SessionOut)
def session_state(db: Session = Depends(get_db)) -> SessionOut:
    """Resume the active desktop conversation and report greeting entitlement.

    Called by the frontend (and pushed to it) at launch. ``conversation_id`` is
    the conversation the next text/voice turn will join; ``resumed`` says whether
    it already has history; ``greeting.owed`` is true only when a launch greeting
    is entitled (new conversation, or an ungreated one inside the greeting
    window); ``idle`` carries the proactive-conversation policy. This endpoint is
    read-only — claiming a greeting is a separate, explicit mutation.
    """
    require_db(db)
    conversation = get_or_create_conversation(db, None)
    resumed = bool(get_messages(db, conversation.id, limit=1))
    return SessionOut(
        conversation_id=str(conversation.id),
        resumed=resumed,
        greeting={
            "owed": greeting_owed(db, conversation),
            "new": bool(getattr(conversation, "_was_created", False)),
        },
        idle=idle_policy_payload(),
        server_time=models.utcnow().isoformat(),
    )


@router.post("/session/claim-greeting", status_code=204)
def session_claim_greeting(db: Session = Depends(get_db)) -> Response:
    """Mark the launch greeting as delivered (exactly-once entitlement).

    The desktop/frontend calls this after actually speaking the greeting so a
    relaunch inside the same conversation's greeting window stays silent.
    """
    require_db(db)
    conversation = get_or_create_conversation(db, None)
    claim_greeting(db, conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def conversation_messages(conversation_id: str, db: Session = Depends(get_db)) -> list[MessageOut]:
    require_db(db)
    conv_id = parse_uuid(conversation_id, "Conversation")
    conversation = get_conversation(db, conv_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [_message_out(m) for m in get_messages(db, conversation.id)]


@router.get("/memories", response_model=list[MemoryOut])
def memories(db: Session = Depends(get_db)) -> list[MemoryOut]:
    require_db(db)
    return [_memory_out(m) for m in list_memories(db)]


@router.post("/memories", response_model=MemoryOut, status_code=201)
def memories_create(payload: MemoryCreate, db: Session = Depends(get_db)) -> MemoryOut:
    require_db(db)
    memory = create_memory(db, payload.content)
    db.commit()
    return _memory_out(memory)


@router.delete("/memories/{memory_id}", status_code=204)
def memories_delete(memory_id: str, db: Session = Depends(get_db)) -> None:
    require_db(db)
    mem_id = parse_uuid(memory_id, "Memory")
    if not delete_memory(db, mem_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    db.commit()


@router.get("/tasks", response_model=list[TaskOut])
def tasks(status: str | None = None, db: Session = Depends(get_db)) -> list[TaskOut]:
    """List the owner's tasks, most recently updated first.

    Query param ``status`` filters to ``pending`` or ``done``.
    """
    require_db(db)
    return [_task_out(t) for t in list_tasks(db, status=status)]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def tasks_create(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    require_db(db)
    task = create_task(db, payload.title, due_at=_due_at_value(payload.due_at))
    db.commit()
    return _task_out(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def tasks_update(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskOut:
    require_db(db)
    t_id = parse_uuid(task_id, "Task")
    updates: dict = {}
    if "title" in payload.model_fields_set:
        updates["title"] = payload.title
    if "due_at" in payload.model_fields_set:
        updates["due_at"] = _due_at_value(payload.due_at)
    if "status" in payload.model_fields_set:
        updates["status"] = payload.status
    task = update_task(db, t_id, **updates)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.commit()
    return _task_out(task)


@router.delete("/tasks/{task_id}", status_code=204)
def tasks_delete(task_id: str, db: Session = Depends(get_db)) -> None:
    require_db(db)
    t_id = parse_uuid(task_id, "Task")
    if not delete_task(db, t_id):
        raise HTTPException(status_code=404, detail="Task not found")
    db.commit()