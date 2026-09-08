"""Integrations (Discord/Telegram) status API.

The frontend GmailPanel renders connectivity chips from this endpoint. It only
reports enabled/status/label - never tokens - so it is safe to expose as-is.
"""

from fastapi import APIRouter

from app.integrations.supervisor import integration_supervisor

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def status() -> dict:
    return integration_supervisor.status()


__all__ = ["router"]