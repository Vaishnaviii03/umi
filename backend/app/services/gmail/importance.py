"""Phase 5 — email importance detection (heuristic layer).

Deterministic, testable pre-filter used for every inbox read and to order the
LLM summary. ``score_importance`` returns a 0..1 score plus a bucket and the
reasons the score was bumped, so the browser and the model can explain *why*
something is flagged.
"""

from __future__ import annotations

URGENT_KEYWORDS = (
    "urgent",
    "asap",
    "deadline",
    "today",
    "tonight",
    "invoice",
    "payment",
    "overdue",
    "meeting",
    "review",
    "confirm",
    "required",
    "action",
    "contract",
    "final",
    "late",
)

_WEIGHT_UNREAD = 0.30
_WEIGHT_THREAD = 0.20
_WEIGHT_ATTACHMENT = 0.15
_WEIGHT_KEYWORD = 0.20
_WEIGHT_ALL_CAPS = 0.10


def scale_email(message: dict) -> dict:
    """Return ``{score, level, reasons}`` for a normalized email dict.

    Reads: unread, thread_length, has_attachment, subject. A higher score means
    the user probably wants to act on this email soon; level buckets are
    ``high`` (>=0.7), ``medium`` (>=0.4) or ``low``.
    """
    score = 0.0
    reasons: list[str] = []
    subject = (message.get("subject") or "").strip()

    if message.get("unread"):
        score += _WEIGHT_UNREAD
        reasons.append("unread")
    if (message.get("thread_length") or 1) > 5:
        score += _WEIGHT_THREAD
        reasons.append("long thread")
    if message.get("has_attachment"):
        score += _WEIGHT_ATTACHMENT
        reasons.append("attachment")
    if subject.upper() == subject and len(subject) >= 6:
        score += _WEIGHT_ALL_CAPS
        reasons.append("all-caps subject")

    lowered = subject.lower()
    hits = [k for k in URGENT_KEYWORDS if k in lowered]
    if hits:
        score += min(len(hits), 2) * _WEIGHT_KEYWORD
        reasons.append("urgent keyword") 

    score = round(min(score, 1.0), 2)
    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    return {"score": score, "level": level, "reasons": reasons}