"""Phase 7.5 — Drive service facade.

Owns no separate token: reuses the shared ``~/.umi/gmail_token.json`` and the
Gmail API's `credentials_from_store`, exactly like Calendar. Tests inject a
fake ``api``/``api_factory``.
"""

from __future__ import annotations

import logging
from typing import Callable

from googleapiclient.errors import HttpError

from app.services.drive.api import (
    DriveAPI,
    decode_content,
    normalize_drive_file,
)
from app.services.gmail.api import credentials_from_store
from app.services.gmail.token_store import TokenStore, token_store
from app.services.google_http import (
    GoogleNotConnected,
    GoogleNotFound,
    GoogleServiceError,
    map_http_error,
)

logger = logging.getLogger("umi.drive")

DriveError = GoogleServiceError
DriveNotConnected = GoogleNotConnected

MAX_QUERY_CHARS = 500


class DriveService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: DriveAPI | None = None,
        api_factory: Callable[[dict], DriveAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> DriveAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise DriveNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return DriveAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            logger.warning("[drive] stored token is invalid; reconnect required")
            raise DriveNotConnected("no valid Google credentials stored — reconnect")

    def _run(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            map_http_error(exc, "Google Drive")

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            self._run(self._get_api().list_files, query="", page_size=1)
            return {"connected": True, "email": None}
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            return {"connected": False, "email": None}

    # -- files --------------------------------------------------------------- #
    def search_drive_files(self, query: str = "", max_results: int = 25) -> list[dict]:
        if len(query) > MAX_QUERY_CHARS:
            query = query[:MAX_QUERY_CHARS]
        raw = self._run(self._get_api().list_files, query=query, page_size=max_results)
        return [normalize_drive_file(item) for item in raw]

    def get_drive_file(self, file_id: str) -> dict:
        raw = self._run(self._get_api().get_file, file_id)
        return normalize_drive_file(raw)

    def read_drive_file(self, file_id: str) -> dict:
        payload = self._run(self._get_api().read_file, file_id)
        if not isinstance(payload, dict) or "meta" not in payload:
            raise GoogleNotFound(f"Google Drive couldn't find file {file_id!r}.")
        meta = payload["meta"]
        content, is_text = decode_content(payload.get("media", b""))
        out = normalize_drive_file(meta)
        out["content"] = content
        out["content_is_text"] = is_text
        out["truncated"] = len(content) > 50_000
        if out["truncated"]:
            out["content"] = content[:50_000]
        logger.info("[drive][audit] file read id=%s name=%r", file_id, out.get("name"))
        return out


drive_service = DriveService()

__all__ = ["DriveError", "DriveNotConnected", "DriveService", "drive_service"]