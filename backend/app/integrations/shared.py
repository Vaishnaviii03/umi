from __future__ import annotations

from app.db import engine as db_engine
from app.integrations.authz import refusal_text, resolve_role
from app.integrations.types import PlatformMessage
from app.orchestrator.core import handle_message

_PLATFORM_CONTEXT_TEMPLATE = (
    "You are talking to the user through {platform}. {context} "
    "Reply in plain text. If using a tool would need confirmation, do NOT "
    "perform the action here — say you can't do it from this channel and point "
    "the user to the desktop app."
)


def respond_to(message: PlatformMessage) -> str | None:
    """Route one inbound platform message into Umi's shared pipeline.

    Returns the reply text to send back on the originating channel. Unknown
    users get the fixed refusal text with zero LLM/tool/database access.
    Returns None only if the message should be dropped silently.
    """
    if resolve_role(message.platform, message.platform_user_id) != "owner":
        return refusal_text(message.platform, message.author_name)

    sender_context = _PLATFORM_CONTEXT_TEMPLATE.format(
        platform=message.platform,
        context=message.context_summary,
    )

    session = db_engine.get_session_factory()() if db_engine.db_enabled() else None
    try:
        reply, _conversation_id = handle_message(
            session,
            message.text,
            source=message.platform,
            conversation_key=message.conversation_key,
            conversation_title=message.conversation_title,
            platform_context=sender_context,
            include_greeting=False,
        )
        return reply
    finally:
        if session is not None:
            session.close()


__all__ = ["respond_to"]