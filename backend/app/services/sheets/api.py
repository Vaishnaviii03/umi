"""Phase 7.5 — Google Sheets API boundary.

Thin wrapper around the Sheets REST client (metadata, values read/write,
spreadsheet create). Reuses the shared Gmail credentials via the Drive-style
injectable pattern; tests inject a fake object instead of hitting Google.
"""

from __future__ import annotations

import logging

from app.services.google_http import GoogleNotConnected, map_http_error

logger = logging.getLogger("umi.sheets")

_SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
MAX_ROWS = 1000
MAX_CELLS = 10_000
MAX_CELL_LEN = 500


class SheetsAPI:
    def __init__(self, *, credentials=None, service=None) -> None:
        self._creds = credentials
        self._service = service

    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise GoogleNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("sheets", "v4", credentials=self._creds, cache_discovery=False)

    def get_spreadsheet(self, spreadsheet_id: str) -> dict:
        response = (
            self._svc()
            .spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="properties.title,sheets.properties.sheetId,sheets.properties.title")
            .execute()
        )
        return response

    def read_values(self, spreadsheet_id: str, range_: str) -> list[list[str]]:
        response = (
            self._svc()
            .spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_)
            .execute()
        )
        return response.get("values", [])

    def write_values(self, spreadsheet_id: str, range_: str, values: list[list[str]]) -> dict:
        response = (
            self._svc()
            .spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_,
                body={"values": values},
                valueInputOption="USER_ENTERED",
            )
            .execute()
        )
        return response

    def create_spreadsheet(self, title: str) -> dict:
        response = self._svc().spreadsheets().create(body={"properties": {"title": title}}).execute()
        return response


def _guard_values(values: list[list[str]]) -> list[list[str]]:
    """Reject anything that would flatten the sheet or blow up quota."""
    if not isinstance(values, list) or not all(isinstance(row, list) for row in values):
        raise ValueError("values must be a list of rows (each a list of strings)")
    flat = [cell for row in values for cell in row]
    if len(flat) > MAX_CELLS:
        raise ValueError(f"too many cells for one write — limit is {MAX_CELLS}")
    if len(values) > MAX_ROWS:
        raise ValueError(f"too many rows for one write — limit is {MAX_ROWS}")
    for cell in flat:
        if len(str(cell)) > MAX_CELL_LEN:
            raise ValueError(f"one cell is over {MAX_CELL_LEN} characters — split it up")
    return [[str(cell) for cell in row] for row in values]


def normalize_sheet(raw: dict) -> dict:
    return {
        "id": raw.get("spreadsheetId"),
        "url": raw.get("spreadsheetUrl"),
        "name": raw.get("properties", {}).get("title"),
        "tabs": [s.get("properties", {}).get("title") for s in raw.get("sheets", [])],
    }


__all__ = [
    "SheetsAPI",
    "_guard_values",
    "map_http_error",
    "normalize_sheet",
]