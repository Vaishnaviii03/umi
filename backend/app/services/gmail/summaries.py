"""Phase 5 — inbox summaries via the LLM.

The heuristic layer orders the inbox; this turns the shortlist into a concise,
importance-aware brief. Falls back to a deterministic digest if the model is
unreachable so the feature never hard-fails.

The LLM manager is imported lazily to avoid a cycle: manager → tools → gmail
services → manager.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("umi.gmail")

_SUMMARY_SYSTEM = (
    "You are Umi, the user's personal AI companion, summarizing their inbox. "
    "Give a short, scannable brief (3-6 lines). Lead with what needs action or "
    "is time-sensitive, then the rest ordered by importance. For each item: "
    "who it's from, the subject, and a one-line reason it matters. Flag "
    "anything urgent with a short note. Do not use markdown bullets; plain "
    "short lines only."
)


def build_brief(emails: list[dict], statement: str | None = None) -> str:
    """Returns an LLM-written brief for the given normalized emails."""
    from app.llm.manager import LLMError, llm_manager  # deferred (import cycle)

    lines = [
        f"{i + 1}. from {e.get('from_name') or e.get('from_email')} — {e.get('subject') or '(no subject)'}"
        + (f" ({e.get('snippet') or ''})" if e.get("snippet") else "")
        for i, e in enumerate(emails[:12])
    ]
    if not lines:
        return "Inbox is empty — nothing to summarize."

    prompt = (
        "Here are the user's current inbox emails (already roughly ordered by "
        "importance, most important first):\n" + "\n".join(lines)
    )
    try:
        brief = llm_manager.generate_reply(
            prompt,
            system=_SUMMARY_SYSTEM,
            max_tokens=300,
        )
        return brief.strip()
    except LLMError:
        logger.exception("[gmail] summary model unavailable; using digest fallback")
        return _digest(emails)


def _digest(emails: list[dict]) -> str:
    top = [e for e in emails if e.get("importance_level") == "high"]
    items = top or emails[:6]
    return "Summary (model unavailable):\n" + "\n".join(
        f"- {e.get('from_name') or e.get('from_email')}: {e.get('subject') or '(no subject)'}"
        for e in items
    )