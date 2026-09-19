"""Phase 7.5 — Google integration status API.

Lives beside the Gmail/Calendar routers. The auth flow itself stays in the
Gmail router; this router only reports coverage so the frontend can render
the single-connection UI and the reconnect prompt.
"""

from fastapi import APIRouter

from app.services.google_status import google_status

router = APIRouter(prefix="/google", tags=["google"])


@router.get("/status")
def status() -> dict:
    return google_status()


__all__ = ["router"]