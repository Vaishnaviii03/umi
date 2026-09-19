"""Phase 7.5 — Google Drive API boundary.

Thin wrapper around the Drive REST client (search, metadata, content read).
Reuses the shared Gmail token/credentials like Calendar does. Every method
returns normalized dicts or raw JSON the service layer understands; tests
inject a fake object instead of hitting Google.
"""

from __future__ import annotations

import base64
import logging

from app.services.gmail.api import credentials_from_store
from app.services.google_http import (
    GoogleNotConnected,
    map_http_error,
)

logger = logging.getLogger("umi.drive")

_FIELDS = "id,name,mimeType,parents,webViewLink,size,modifiedTime,createdTime,trashed"
_SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
_EXPORT_TEXT = "text/plain"
_EXPORT_SPREADSHEET = "text/csv"
_TEXT_WRITABLE = {"text/plain", "text/csv", "application/json"}


def _export_mime(mime_type: str) -> str:
    return _EXPORT_SPREADSHEET if mime_type == _SPREADSHEET_MIME else _EXPORT_TEXT


class DriveAPI:
    """Thin wrapper around the Drive REST client (injectable for tests)."""

    def __init__(self, *, credentials=None, service=None) -> None:
        self._creds = credentials
        self._service = service  # injectable for tests

    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise GoogleNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("drive", "v3", credentials=self._creds, cache_discovery=False)

    def list_files(self, *, query: str = "", page_size: int = 25) -> list[dict]:
        response = (
            self._svc()
            .files()
            .list(
                q=query or None,
                pageSize=page_size,
                fields=f"nextPageToken, files({_FIELDS})",
                supportsAllDrives=True,
            )
            .execute()
        )
        return response.get("files", [])

    def get_file(self, file_id: str) -> dict:
        return (
            self._svc()
            .files()
            .get(fileId=file_id, fields=_FIELDS, supportsAllDrives=True)
            .execute()
        )

    def read_file(self, file_id: str) -> dict:
        """Fetch content: Google-native files via export, others via media download."""
        meta = self.get_file(file_id)
        mime = meta.get("mimeType", "")
        service = self._svc()
        if mime == _SPREADSHEET_MIME:
            raw = service.files().export(fileId=file_id, mimeType=_EXPORT_SPREADSHEET).execute()
        elif mime.startswith("application/vnd.google-apps."):
            raw = service.files().export(fileId=file_id, mimeType=_EXPORT_TEXT).execute()
        else:
            raw = service.files().get_media(fileId=file_id).execute()
        return {"media": raw, "meta": meta}


def decode_content(media) -> tuple[str, bool]:
    """Decode media bytes to text when possible; otherwise base64. Returns
    (content, was_valid_text)."""
    if isinstance(media, str):
        return media, True
    try:
        return media.decode("utf-8"), True
    except UnicodeDecodeError:
        return base64.b64encode(media).decode("ascii"), False


def normalize_drive_file(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or "(untitled)",
        "mime_type": raw.get("mimeType"),
        "parents": raw.get("parents") or [],
        "link": raw.get("webViewLink"),
        "size": raw.get("size"),
        "modified_time": raw.get("modifiedTime"),
        "created_time": raw.get("createdTime"),
        "trashed": bool(raw.get("trashed", False)),
    }


__all__ = [
    "DriveAPI",
    "decode_content",
    "map_http_error",
    "normalize_drive_file",
]