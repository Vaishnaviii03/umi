import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import models
from app.db.repositories import (
    create_memory,
    delete_memory,
    get_conversation,
    get_or_create_conversation,
    get_messages,
    list_conversations,
    list_memories,
)
from app.db.session import get_db
from app.llm.manager import LLMError
from app.orchestrator.core import handle_message, stream_message
from app.services.elevenlabs_token import ElevenLabsTokenError, token_minter
from app.services.elevenlabs_tts import TTSError, tts_service
from app.tools import tool_manager

logger = logging.getLogger("umi.api")

router = APIRouter()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    voice: bool = False


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str | None = None


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


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        reply, conversation_id = handle_message(
            db, payload.message, payload.conversation_id, voice=payload.voice
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
                db, payload.message, payload.conversation_id, voice=payload.voice
            ):
                if event == "chunk":
                    yield _sse_event({"text": data["text"]})
                elif event == "error":
                    metrics = dict(data.get("metrics") or {})
                    metrics["chat_request_ms"] = round((time.perf_counter() - started) * 1000)
                    metrics["turn_failed"] = True
                    logger.info("[latency] chat turn failed %s", metrics)
                    yield _sse_event({"error": data["detail"]})
                elif event == "done":
                    metrics = dict(data.get("metrics") or {})
                    metrics["chat_request_ms"] = round((time.perf_counter() - started) * 1000)
                    logger.info(
                        "[latency] chat turn done chat_request_ms=%s llm_first_token_ms=%s "
                        "llm_total_ms=%s reply_chars=%s",
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
    """Synthesize Umi's reply with ElevenLabs and return the audio bytes.

    Kept separate from /chat so the text response always succeeds even when
    voice synthesis is unavailable. Failures degrade to a safe message — the
    API key and provider internals never reach the client.
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
    except TTSError:
        logger.exception("tts request failed")
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
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
        status_code=status.HTTP_200_OK,
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