"""Phase 7.5 — Google Docs API boundary.

Thin wrapper around the Docs REST client (get, create, batchUpdate). All
text extraction / indexing lives in the service layer; tests inject a fake.
"""

from __future__ import annotations

import logging

from app.services.google_http import GoogleNotConnected, map_http_error

logger = logging.getLogger("umi.docs")


class DocsAPI:
    def __init__(self, *, credentials=None, service=None) -> None:
        self._creds = credentials
        self._service = service

    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise GoogleNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("docs", "v1", credentials=self._creds, cache_discovery=False)

    def get_document(self, document_id: str) -> dict:
        return self._svc().documents().get(documentId=document_id).execute()

    def create_document(self, title: str) -> dict:
        return self._svc().documents().create(body={"title": title}).execute()

    def batch_update(self, document_id: str, requests: list[dict]) -> dict:
        return (
            self._svc()
            .documents()
            .batchUpdate(documentId=document_id, body={"requests": requests})
            .execute()
        )


__all__ = ["DocsAPI", "map_http_error"]