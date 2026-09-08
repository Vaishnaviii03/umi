"""Phase 5 — Gmail service package (OAuth, mailbox, importance, summaries)."""

from app.services.gmail.service import (  # noqa: F401
    GmailError,
    GmailNotConfigured,
    GmailNotConnected,
    GmailPermissionMissing,
    GmailReauthRequired,
    GmailService,
    gmail_service,
)