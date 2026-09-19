"""Phase 7.5 — YouTube service package (reuses shared Gmail OAuth token)."""

from app.services.youtube.service import (  # noqa: F401
    YoutubeError,
    YoutubeService,
    youtube_service,
)

__all__ = ["YoutubeError", "YoutubeService", "youtube_service"]