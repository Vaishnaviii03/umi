"""Phase 7.5 — Google YouTube service facade.

Search/read are read-scoped (side-effect free); upload/update/delete are the
visible-write operations the tools layer guards behind permission 2 +
confirmation. Privacy defaults to ``private`` so an upload can never publish
something unintended.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from googleapiclient.errors import HttpError

from app.services.gmail.api import credentials_from_store
from app.services.gmail.token_store import TokenStore, token_store
from app.services.google_http import (
    GoogleNotFound,
    GoogleNotConnected,
    GoogleServiceError,
    map_http_error,
)
from app.services.youtube.api import YoutubeAPI

logger = logging.getLogger("umi.youtube")

YoutubeError = GoogleServiceError
MAX_QUERY_CHARS = 500
ALLOWED_PRIVACY = {"private", "unlisted", "public"}


def normalize_search_item(item: dict) -> dict:
    vid = item.get("id") or {}
    snip = item.get("snippet") or {}
    return {
        "id": vid.get("videoId"),
        "title": snip.get("title") or "(untitled)",
        "channel": snip.get("channelTitle"),
        "published_at": snip.get("publishedAt"),
        "description": snip.get("description") or "",
        "url": f"https://www.youtube.com/watch?v={vid.get('videoId')}",
    }


def normalize_video(video: dict) -> dict:
    snip = video.get("snippet") or {}
    stats = video.get("statistics") or {}
    return {
        "id": video.get("id"),
        "url": f"https://www.youtube.com/watch?v={video.get('id')}",
        "title": snip.get("title") or "(untitled)",
        "description": snip.get("description") or "",
        "channel_title": snip.get("channelTitle"),
        "published_at": snip.get("publishedAt"),
        "duration": (video.get("contentDetails") or {}).get("duration"),
        "view_count": stats.get("viewCount"),
        "like_count": stats.get("likeCount"),
    }


def _safe_query(query: str) -> str:
    return query[:MAX_QUERY_CHARS] if len(query) > MAX_QUERY_CHARS else query


def _safe_privacy(value: str) -> str:
    value = (value or "private").lower()
    return value if value in ALLOWED_PRIVACY else "private"


class YoutubeService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: YoutubeAPI | None = None,
        api_factory: Callable[[dict], YoutubeAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> YoutubeAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise GoogleNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return YoutubeAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            logger.warning("[youtube] stored token is invalid; reconnect required")
            raise GoogleNotConnected("no valid Google credentials stored — reconnect")

    def _run(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            map_http_error(exc, "YouTube")

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            self._get_api().channel_mine_id()
            return {"connected": True, "email": None}
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            return {"connected": False, "email": None}

    # -- read ---------------------------------------------------------------- #
    def search_youtube(self, query: str, max_results: int = 10) -> list[dict]:
        if not query.strip():
            raise GoogleServiceError("a search term is required for YouTube search.")
        items = self._run(self._get_api().search, query=_safe_query(query), max_results=max_results)
        return [normalize_search_item(i) for i in items]

    def get_video(self, video_id: str) -> dict:
        items = self._run(self._get_api().list_videos, [video_id])
        if not items:
            raise GoogleNotFound(f"YouTube couldn't find video {video_id!r}.")
        return normalize_video(items[0])

    def list_uploads(self, max_results: int = 25) -> list[dict]:
        uploads_id = self._run(self._get_api().channel_mine_id)
        if not uploads_id:
            return []
        items = self._run(self._get_api().list_playlist_items, uploads_id, max_results)
        out = []
        for item in items:
            vid = (item.get("contentDetails") or {}).get("videoId")
            if not vid:
                continue
            snip = item.get("snippet") or {}
            out.append(
                {
                    "id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": snip.get("title") or "(untitled)",
                    "channel": snip.get("channelTitle"),
                    "published_at": snip.get("publishedAt"),
                    "description": snip.get("description") or "",
                }
            )
        return out

    # -- write (guarded by tools layer) -------------------------------------- #
    def update_video(self, video_id: str, *, title: str | None = None, description: str | None = None) -> dict:
        current = self._run(self._get_api().list_videos, [video_id])
        if not current:
            raise GoogleNotFound(f"YouTube couldn't find video {video_id!r}.")
        snippet = dict(current[0].get("snippet") or {})
        if title is not None:
            snippet["title"] = title.strip() or snippet.get("title")
        if description is not None:
            snippet["description"] = description
        if not (title or description):
            raise GoogleServiceError("nothing to update — provide a title and/or description.")
        updated = self._run(self._get_api().update_video, video_id, snippet)
        logger.info("[youtube][audit] video updated id=%s title=%r", video_id, snippet.get("title"))
        return normalize_video(updated)

    def delete_video(self, video_id: str) -> dict:
        self._run(self._get_api().delete_video, video_id)
        logger.warning("[youtube][audit] video deleted id=%s", video_id)
        return {"id": video_id, "deleted": True}

    def upload_video(
        self,
        file_path: str,
        *,
        title: str,
        description: str = "",
        privacy: str = "private",
    ) -> dict:
        if not title.strip():
            raise GoogleServiceError("a title is required to upload a video.")
        if not os.path.isfile(file_path):
            raise GoogleServiceError(f"the video file doesn't exist: {file_path!r}")
        size = os.path.getsize(file_path)
        if size == 0:
            raise GoogleServiceError("the video file is empty (0 bytes) — nothing to upload.")
        privacy = _safe_privacy(privacy)
        created = self._run(
            self._get_api().upload_video,
            file_path,
            title=title.strip(),
            description=description or "",
            privacy=privacy,
        )
        vid = created.get("id")
        logger.info("[youtube][audit] video uploaded id=%s title=%r privacy=%s bytes=%d", vid, title, privacy, size)
        return {"id": vid, "title": title.strip(), "url": f"https://www.youtube.com/watch?v={vid}", "privacy": privacy}


youtube_service = YoutubeService()

__all__ = [
    "YoutubeError",
    "YoutubeService",
    "normalize_search_item",
    "normalize_video",
    "youtube_service",
]