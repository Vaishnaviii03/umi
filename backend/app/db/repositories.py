import re
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Conversation, Memory, Message

# The local owner is a real Supabase Auth user (see backend/.env UMI_OWNER_ID);
# scaffold FKs for conversations/memories point at auth.users.
OWNER_USER_ID = uuid.UUID(settings.owner_id)


# --------------------------------------------------------------------------- #
# Conversations / messages
# --------------------------------------------------------------------------- #
def get_or_create_conversation(db: Session, conversation_id=None) -> Conversation:
    """Return the requested conversation (if present), else the user's latest,
    else create a fresh one."""
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id == OWNER_USER_ID:
            return conv
    conv = (
        db.query(Conversation)
        .filter(Conversation.user_id == OWNER_USER_ID)
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conv is None:
        conv = Conversation(user_id=OWNER_USER_ID, title="Conversation")
        db.add(conv)
        db.flush()
    return conv


def list_conversations(db: Session, limit: int = 50) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == OWNER_USER_ID)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation(db: Session, conversation_id) -> Conversation | None:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != OWNER_USER_ID:
        return None
    return conv


def get_messages(db: Session, conversation_id, limit: int = 200) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .all()
    )


def append_message(db: Session, conversation_id, role: str, content: str) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    db.flush()
    return message


# --------------------------------------------------------------------------- #
# Memories
# --------------------------------------------------------------------------- #
def list_memories(db: Session, limit: int = 100) -> list[Memory]:
    return (
        db.query(Memory)
        .filter(Memory.user_id == OWNER_USER_ID)
        .order_by(Memory.updated_at.desc())
        .limit(limit)
        .all()
    )


def create_memory(db: Session, content: str, source_conversation_id=None) -> Memory:
    memory = Memory(
        user_id=OWNER_USER_ID,
        content=content,
        source_conversation_id=source_conversation_id,
    )
    db.add(memory)
    db.flush()
    return memory


def delete_memory(db: Session, memory_id) -> bool:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.user_id != OWNER_USER_ID:
        return False
    db.delete(memory)
    db.flush()
    return True


def retrieve_relevant_memories(db: Session, query: str, limit: int = 5) -> list[Memory]:
    """Keyword-based retrieval: match any content token, fall back to the most
    recent memories when nothing matches. Embedding-based search replaces this
    in a later phase."""
    tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) >= 3]
    if tokens:
        conditions = [Memory.content.ilike(f"%{token}%") for token in tokens]
        matches = (
            db.query(Memory)
            .filter(Memory.user_id == OWNER_USER_ID)
            .filter(or_(*conditions))
            .order_by(Memory.updated_at.desc())
            .limit(limit)
            .all()
        )
        if matches:
            return matches
    return (
        db.query(Memory)
        .filter(Memory.user_id == OWNER_USER_ID)
        .order_by(Memory.updated_at.desc())
        .limit(limit)
        .all()
    )