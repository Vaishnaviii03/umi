from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlatformMessage:
    """Normalized inbound message from an external chat platform.

    Only safe display metadata is carried: ``context_summary`` is a name-based
    description meant for the LLM, never raw OAuth tokens or channel/user ids.
    ``conversation_key`` is internal routing (not shown to the LLM).
    """

    platform: str
    platform_user_id: str
    author_name: str
    text: str
    conversation_key: str
    conversation_title: str
    context_summary: str