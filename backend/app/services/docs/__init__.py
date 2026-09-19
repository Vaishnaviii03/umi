"""Phase 7.5 — Docs service package (reuses shared Gmail OAuth token)."""

from app.services.docs.service import (  # noqa: F401
    DocsError,
    DocsService,
    docs_service,
)

__all__ = ["DocsError", "DocsService", "docs_service"]