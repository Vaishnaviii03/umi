import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Conversation, Memory, Message, Task, utcnow
from app.services.idle_policy import IdleDecision, evaluate_idle

# The local owner is a real Supabase Auth user (see backend/.env UMI_OWNER_ID);
# scaffold FKs for conversations/memories point at auth.users.
OWNER_USER_ID = uuid.UUID(settings.owner_id)


# --------------------------------------------------------------------------- #
# Conversations / messages
# --------------------------------------------------------------------------- #
def get_or_create_conversation(
    db: Session,
    conversation_id=None,
    *,
    source: str = "desktop",
    conversation_key: str | None = None,
    title: str = "Conversation",
) -> Conversation:
    """Return the requested conversation (if present), else the owner's latest
    conversation matching ``source``/``conversation_key``, else create one.

    Desktop callers pass no extras and keep today's behavior (resolve the
    latest owner conversation). Platform adapters pass ``source`` +
    ``conversation_key`` so each server/channel/chat gets its own isolated
    thread while memories stay shared.
    """
    if isinstance(conversation_id, str):
        try:
            conversation_id = uuid.UUID(conversation_id)
        except ValueError:
            conversation_id = None
    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if conv is not None and conv.user_id == OWNER_USER_ID:
            # A "_was_created" marker set during an earlier create in the same
            # session must never make this resumed conversation look fresh.
            if getattr(conv, "_was_created", False):
                delattr(conv, "_was_created")
            return conv
    query = db.query(Conversation).filter(
        Conversation.user_id == OWNER_USER_ID,
        Conversation.source == source,
    )
    if conversation_key is None:
        query = query.filter(Conversation.conversation_key.is_(None))
    else:
        query = query.filter(Conversation.conversation_key == conversation_key)
    conv = query.order_by(Conversation.updated_at.desc()).first()
    if conv is None:
        conv = Conversation(
            user_id=OWNER_USER_ID,
            title=title,
            source=source,
            conversation_key=conversation_key,
        )
        # Transient marker so callers can tell a genuinely fresh conversation
        # from a resumed one (used for greeting entitlement). Not a column.
        conv._was_created = True
        db.add(conv)
        db.flush()
    return conv


def greeting_owed(db: Session, conversation: Conversation, *, now: datetime | None = None) -> bool:
    """Whether a launch greeting is entitled for this conversation.

    Owed when the conversation was just created on this request, or when it
    was created within the configured greeting window and has never been
    greeted. Claimed greetings stay silent until a new conversation appears.
    """
    if conversation.last_greeted_at is not None:
        return False
    if getattr(conversation, "_was_created", False):
        return True
    created = conversation.created_at
    if created is None:
        return True
    now = now or utcnow()
    if created.tzinfo is None:  # SQLite server_default returns a naive value
        created = created.replace(tzinfo=timezone.utc)
    age = now - created
    if age < timedelta(seconds=settings.umi_greeting_window_s):
        return True
    return False


def claim_greeting(db: Session, conversation: Conversation, *, now: datetime | None = None) -> None:
    """Stamp the conversation as greeted (exactly-once entitlement)."""
    conversation.last_greeted_at = now or utcnow()
    db.flush()


# --------------------------------------------------------------------------- #
# Proactive (idle) policy
# --------------------------------------------------------------------------- #
def _roll_over_proactive_counter(conversation: Conversation, now: datetime) -> None:
    """Reset the rolling hourly cap when an hour has passed since the last
    proactive turn (applied lazily on read so the check never spuriously caps)."""
    if conversation.last_proactive_at is None:
        return
    if now - conversation.last_proactive_at >= timedelta(hours=1):
        conversation.proactive_count_last_hour = 0


def get_last_user_activity(db: Session, conversation: Conversation) -> datetime:
    """Most recent point at which the owner actually spoke, else conversation
    creation (a brand-new thread counts as "just active" — never ambush it)."""
    msg = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .first()
    )
    if msg is not None and msg.created_at is not None:
        created = msg.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created
    created_at = conversation.created_at
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at or utcnow()


def evaluate_proactive_entitlement(
    db: Session, conversation: Conversation, *, now: datetime | None = None
) -> IdleDecision:
    """Whether Umi may open a proactive turn in this conversation right now.

    Last activity is measured from the owner's most recent message, so a
    proactive opener that just fired does not count as the owner's activity.
    """
    now = now or utcnow()
    _roll_over_proactive_counter(conversation, now)
    last_activity = get_last_user_activity(db, conversation)
    return evaluate_idle(
        now=now,
        last_activity_at=last_activity,
        last_proactive_at=conversation.last_proactive_at,
        proactive_count_last_hour=conversation.proactive_count_last_hour,
    )


def record_proactive(
    db: Session, conversation: Conversation, *, now: datetime | None = None
) -> None:
    """Count a proactive opener (updates cooldown pin + rolling hourly cap)."""
    now = now or utcnow()
    _roll_over_proactive_counter(conversation, now)
    if conversation.last_proactive_at is None or (
        now - conversation.last_proactive_at >= timedelta(hours=1)
    ):
        conversation.proactive_count_last_hour = 1
    else:
        conversation.proactive_count_last_hour += 1
    conversation.last_proactive_at = now
    db.flush()


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


# --------------------------------------------------------------------------- #
# Tasks (Phase 4)
# --------------------------------------------------------------------------- #
def list_tasks(db: Session, status: str | None = None, limit: int = 200) -> list[Task]:
    """Owner-scoped task list, most recently updated first.

    ``status`` is ``"pending"`` or ``"done"``; ``None`` returns everything.
    """
    query = db.query(Task).filter(Task.user_id == OWNER_USER_ID)
    if status is not None:
        query = query.filter(Task.status == status)
    return query.order_by(Task.updated_at.desc()).limit(limit).all()


def create_task(db: Session, title: str, due_at=None) -> Task:
    task = Task(user_id=OWNER_USER_ID, title=title, due_at=due_at)
    db.add(task)
    db.flush()
    return task


def get_task(db: Session, task_id) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.user_id != OWNER_USER_ID:
        return None
    return task


def update_task(
    db: Session, task_id, *, title: str | None = None, due_at=None, status: str | None = None
) -> Task | None:
    """Partial update of an owner task. ``None`` fields are left unchanged."""
    task = get_task(db, task_id)
    if task is None:
        return None
    if title is not None:
        task.title = title
    if due_at is not None:
        task.due_at = due_at
    if status is not None:
        task.status = status
    db.flush()
    return task


def delete_task(db: Session, task_id) -> bool:
    task = get_task(db, task_id)
    if task is None:
        return False
    db.delete(task)
    db.flush()
    return True