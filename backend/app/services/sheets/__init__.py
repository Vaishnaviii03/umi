"""Phase 7.5 — Sheets service package (reuses shared Gmail OAuth token)."""

from app.services.sheets.service import (  # noqa: F401
    SheetsError,
    SheetsService,
    sheets_service,
)

__all__ = ["SheetsError", "SheetsService", "sheets_service"]