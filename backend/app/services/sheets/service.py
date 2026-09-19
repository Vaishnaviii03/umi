"""Phase 7.5 — Google Sheets service facade.

Reuses the shared ``~/.umi/gmail_token.json`` + Gmail credentials exactly like
Calendar/Drive. Spreadsheet discovery leans on the Drive search so "find a
sheet by name" works without a separate index.
"""

from __future__ import annotations

import logging
from typing import Callable

from googleapiclient.errors import HttpError

from app.services.drive.service import DriveService, drive_service
from app.services.gmail.api import credentials_from_store
from app.services.gmail.token_store import TokenStore, token_store
from app.services.google_http import (
    GoogleNotFound,
    GoogleNotConnected,
    GoogleServiceError,
    map_http_error,
)
from app.services.sheets.api import (
    MAX_CELL_LEN,
    MAX_CELLS,
    MAX_ROWS,
    SheetsAPI,
    _guard_values,
    normalize_sheet,
)

logger = logging.getLogger("umi.sheets")

SheetsError = GoogleServiceError


class SheetsService:
    def __init__(
        self,
        store: TokenStore | None = None,
        api: SheetsAPI | None = None,
        api_factory: Callable[[dict], SheetsAPI] | None = None,
    ) -> None:
        self.store = store or token_store
        self._api = api
        self._api_factory = api_factory

    # -- plumbing ------------------------------------------------------------ #
    def _get_api(self) -> SheetsAPI:
        if self._api is not None:
            return self._api
        token = self.store.load()
        if token is None:
            raise GoogleNotConnected("no Google account connected yet")
        if self._api_factory is not None:
            return self._api_factory(token)
        try:
            return SheetsAPI(credentials=credentials_from_store(token))
        except (ValueError, TypeError):
            logger.warning("[sheets] stored token is invalid; reconnect required")
            raise GoogleNotConnected("no valid Google credentials stored — reconnect")

    def _run(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            map_http_error(exc, "Google Sheets")

    # -- lifecycle ----------------------------------------------------------- #
    def status(self) -> dict:
        if not self.store.exists:
            return {"connected": False, "email": None}
        try:
            self._get_api().read_values("__status_probe__", "A1:A1")
        except GoogleNotFound:
            return {"connected": True, "email": None}  # token valid; probe just didn't exist
        except Exception:  # noqa: BLE001 — status is a safe no-op; never 500
            return {"connected": False, "email": None}
        return {"connected": True, "email": None}

    # -- spreadsheets -------------------------------------------------------- #
    def find_spreadsheet(self, name: str, max_results: int = 10, drive: DriveService | None = None) -> list[dict]:
        safe_name = name.replace("'", "")
        q = f"name contains '{safe_name}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        files = (drive or drive_service).search_drive_files(query=q, max_results=max_results)
        return [f for f in files if f.get("mime_type") == "application/vnd.google-apps.spreadsheet"]

    def get_spreadsheet(self, spreadsheet_id: str) -> dict:
        raw = self._run(self._get_api().get_spreadsheet, spreadsheet_id)
        return normalize_sheet(raw)

    def read_sheet(self, spreadsheet_id: str, range_: str = "A1:F30") -> dict:
        values = self._run(self._get_api().read_values, spreadsheet_id, range_)
        metadata = self.get_spreadsheet(spreadsheet_id)
        logger.info("[sheets][audit] sheet read id=%s range=%s", spreadsheet_id, range_)
        return {"spreadsheet_id": spreadsheet_id, "name": metadata.get("name"), "range": range_, "values": values}

    def write_sheet(self, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict:
        safe = _guard_values(values)
        result = self._run(self._get_api().write_values, spreadsheet_id, range_, safe)
        logger.info("[sheets][audit] sheet written id=%s range=%s cells=%d", spreadsheet_id, range_, sum(len(r) for r in safe))
        return {
            "spreadsheet_id": spreadsheet_id,
            "range": result.get("updatedRange") or range_,
            "updated_cells": result.get("updatedCells", 0),
            "updated": True,
        }

    def create_spreadsheet(self, title: str) -> dict:
        created = self._run(self._get_api().create_spreadsheet, title)
        logger.info("[sheets][audit] spreadsheet created title=%r id=%s", title, created.get("spreadsheetId"))
        return normalize_sheet(created)


sheets_service = SheetsService()

__all__ = [
    "MAX_CELL_LEN",
    "MAX_CELLS",
    "MAX_ROWS",
    "SheetsError",
    "SheetsService",
    "sheets_service",
]