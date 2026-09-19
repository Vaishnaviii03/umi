"""Phase 7.5 — Google integration status.

Reads the shared OAuth token store and reports which of the six service
capabilities (Gmail, Calendar, Drive, Sheets, Docs, YouTube) the stored token
actually covers. ``needs_reauthorization`` flips to True when a token predates
the newly added scopes — the frontend then prompts the user to reconnect
through the existing (unchanged) OAuth flow.

No token material is ever returned; callers only see scope strings.
"""

from __future__ import annotations

import logging

from app.services.gmail.api import GOOGLE_SCOPES
from app.services.gmail.service import gmail_service
from app.services.gmail.token_store import token_store

logger = logging.getLogger("umi.google")

REQUIRED_SCOPES: list[str] = GOOGLE_SCOPES


def google_status() -> dict:
    token = token_store.load()
    granted = list(token.get("scopes") or []) if token else []
    missing = [s for s in REQUIRED_SCOPES if s not in granted]

    if token is None:
        return {
            "connected": False,
            "email": None,
            "granted_scopes": [],
            "required_scopes": list(REQUIRED_SCOPES),
            "needs_reauthorization": False,
        }

    try:
        state = gmail_service.status()
    except Exception:  # noqa: BLE001 — status is a safe no-op, never a 500
        logger.warning("[google] status probe failed")
        state = {"connected": False, "email": None}

    return {
        "connected": state.get("connected", False),
        "email": state.get("email"),
        "granted_scopes": granted,
        "required_scopes": list(REQUIRED_SCOPES),
        "needs_reauthorization": bool(missing),
    }


__all__ = ["REQUIRED_SCOPES", "google_status"]