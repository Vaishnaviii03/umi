"""Phase 11 — Proactive Notification API Endpoints.

Provides SSE streaming for client notification banners and toasts,
as well as listing and dismissing active proactive reminders.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.proactive_scheduler import proactive_scheduler

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[dict[str, Any]])
async def list_notifications() -> list[dict[str, Any]]:
    """List all stored proactive notifications."""
    return [n.to_dict() for n in proactive_scheduler.list_notifications()]


@router.post("/{notif_id}/dismiss")
async def dismiss_notification(notif_id: str) -> dict[str, Any]:
    """Dismiss an active proactive notification."""
    success = proactive_scheduler.dismiss_notification(notif_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "id": notif_id, "dismissed": True}


@router.get("/stream")
async def stream_notifications() -> StreamingResponse:
    """Server-Sent Events (SSE) stream for real-time proactive alerts."""
    return StreamingResponse(
        proactive_scheduler.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/trigger-check")
async def trigger_proactive_check() -> dict[str, Any]:
    """Manually trigger a proactive scan cycle (useful for tests or immediate refresh)."""
    emitted = await proactive_scheduler.scan_all()
    return {
        "status": "success",
        "alerts_emitted": len(emitted),
        "alerts": [n.to_dict() for n in emitted],
    }
