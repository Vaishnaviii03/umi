"""Phase 7.5 — Google Docs service facade.

Text extraction walks the structural element tree (paragraphs inside tables and
list blocks included) and flattens it to plain text with blank lines preserved.
All writes go through a single read-then-batchUpdate path for both append and
replace modes.
"""

from __future__ import annotations

import logging
from typing import Callable

from googleapiclient.errors import HttpError

from app.services.docs.api import DocsAPI
from app.services.drive.service import DriveService, drive_service
from app.services.gmail.api import credentials_from_store
from app.services.gmail.token_store import TokenStore, token_store
from app.services.google_http import (
    GoogleNotFound,
    GoogleNotConnected,
    GoogleServiceError,
    map_http_error,
)

logger = logging.getLogger("umi.docs")

DocsError = GoogleServiceError
MAX_TEXT_CHARS = 50_000


def extract_text(body: dict) -> str:
    """Flatten a Docs ``body.content`` list into plain text."""
    lines: list[str] = []

    def walk(elements: list[dict]) -> None:
        for el in elements or []:
            if "paragraph" in el:
                parts = [run.get("textRun", {}).get("content", "") for run in el["paragraph"].get("elements", [])]
                lines.append("".join(parts).rstrip("\n"))
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk(cell.get("content", []))
            elif "tableOfContents" in el:
                walk(el["tableOfContents"].get("content", []))
            elif "sectionBreak" not in el:
                lines.append("")

    walk(body.get("content", []))
    return "\n".join(lines).strip("\n")


class DocsService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: DocsAPI | None = None,
        api_factory: Callable[[dict], DocsAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> DocsAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise GoogleNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return DocsAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            logger.warning("[docs] stored token is invalid; reconnect required")
            raise GoogleNotConnected("no valid Google credentials stored — reconnect")

    def _run(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            map_http_error(exc, "Google Docs")

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            self._get_api().get_document("__status_probe__")
        except GoogleNotFound:
            return {"connected": True, "email": None}  # token valid; probe didn't exist
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            return {"connected": False, "email": None}
        return {"connected": True, "email": None}

    # -- documents ----------------------------------------------------------- #
    def find_document(self, name: str, max_results: int = 10, drive: DriveService | None = None) -> list[dict]:
        safe_name = name.replace("'", "")
        q = f"name contains '{safe_name}' and mimeType='application/vnd.google-apps.document' and trashed=false"
        files = (drive or drive_service).search_drive_files(query=q, max_results=max_results)
        return [f for f in files if f.get("mime_type") == "application/vnd.google-apps.document"]

    def get_document(self, document_id: str) -> dict:
        raw = self._run(self._get_api().get_document, document_id)
        return {
            "id": raw.get("documentId"),
            "title": raw.get("title") or "(untitled)",
            "text": extract_text(raw.get("body") or {}),
        }

    def read_document(self, document_id: str) -> dict:
        out = self.get_document(document_id)
        truncated = len(out["text"]) > MAX_TEXT_CHARS
        if truncated:
            out["text"] = out["text"][:MAX_TEXT_CHARS]
            out["truncated"] = True
        else:
            out["truncated"] = False
        logger.info("[docs][audit] doc read id=%s title=%r", document_id, out.get("title"))
        return out

    def create_document(self, title: str) -> dict:
        created = self._run(self._get_api().create_document, title)
        out = {"id": created.get("documentId"), "title": created.get("title") or title}
        logger.info("[docs][audit] doc created title=%r id=%s", title, out["id"])
        return out

    def _insert_requests(self, doc: dict, text: str, *, append: bool) -> list[dict]:
        body = doc.get("body") or {}
        content = body.get("content") or []
        if not content:
            end = 1
        else:
            end = content[-1].get("endIndex", 1)
        text = text or ""
        if append:
            return [
                {"insertText": {"text": _ensure_end(text), "endOfSegmentLocation": {}}}
            ]
        return [
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": max(1, end - 1)}}},
            {"insertText": {"text": _ensure_end(text), "location": {"index": 1}}},
        ]

    def update_document(self, document_id: str, text: str, *, append: bool = False) -> dict:
        if not text.strip():
            raise GoogleServiceError("nothing to write — text is empty.")
        doc = self._run(self._get_api().get_document, document_id)
        requests = self._insert_requests(doc, text, append=append)
        self._run(self._get_api().batch_update, document_id, requests)
        mode = "append" if append else "replace"
        logger.info("[docs][audit] doc updated id=%s mode=%s chars=%d", document_id, mode, len(text))
        return {"id": document_id, "mode": mode, "characters_written": len(text)}


def _ensure_end(text: str) -> str:
    text = text.rstrip("\n")
    return f"\n{text}\n" if text else text


docs_service = DocsService()

__all__ = ["DocsError", "DocsService", "docs_service", "extract_text"]