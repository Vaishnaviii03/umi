"""Phase 6 — Calendar service package (reuses Gmail OAuth token)."""

from app.services.calendar.service import (  # noqa: F401
    CalendarError,
    CalendarNotConnected,
    CalendarService,
    calendar_service,
)