"""Phase 7.5 — Sheets service tests (no real Google calls)."""

import pytest

from app.services.drive.service import DriveService
from app.services.gmail.token_store import TokenStore
from app.services.sheets import SheetsService
from app.services.sheets.api import _guard_values, normalize_sheet
from app.services.google_http import GoogleNotFound


class _FakeSheetsAPI:
    def __init__(self, spreadsheet=None, values=None):
        self.spreadsheet = spreadsheet or {
            "spreadsheetId": "s1",
            "spreadsheetUrl": "https://sheets.example/s1",
            "properties": {"title": "Founder OS"},
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        self.values = values or [["A", "B"], ["1", "2"]]
        self.calls = []

    def get_spreadsheet(self, spreadsheet_id: str):
        self.calls.append(("get", spreadsheet_id))
        if spreadsheet_id != "s1":
            raise GoogleNotFound("nope")
        return self.spreadsheet

    def read_values(self, spreadsheet_id, range_):
        self.calls.append(("read", spreadsheet_id, range_))
        if spreadsheet_id != "s1":
            raise GoogleNotFound("nope")
        return self.values

    def write_values(self, spreadsheet_id, range_, values):
        self.calls.append(("write", spreadsheet_id, range_, values))
        return {"updatedRange": f"'{range_}'", "updatedCells": sum(len(r) for r in values)}

    def create_spreadsheet(self, title):
        self.calls.append(("create", title))
        return {
            "spreadsheetId": "s-new",
            "spreadsheetUrl": "https://sheets.example/s-new",
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }


def _service(fake=None, tmp_path=""):
    return SheetsService(store=TokenStore(str(tmp_path / "s.json")), api=fake or _FakeSheetsAPI())


def test_normalize_sheet():
    raw = {
        "spreadsheetId": "s1",
        "spreadsheetUrl": "https://sheets.example/s1",
        "properties": {"title": "Founder OS"},
        "sheets": [{"properties": {"title": "Sheet1"}}],
    }
    out = normalize_sheet(raw)
    assert out["id"] == "s1"
    assert out["name"] == "Founder OS"
    assert out["tabs"] == ["Sheet1"]


def test_guard_values_ok():
    assert _guard_values([["a", "b"], ["c"]]) == [["a", "b"], ["c"]]
    assert _guard_values([[1, None]]) == [["1", "None"]]


def test_guard_values_rejects_too_many_cells():
    values = [["x"] * 500 for _ in range(21)]  # 10500 cells
    with pytest.raises(ValueError):
        _guard_values(values)


def test_guard_values_rejects_bad_shape():
    with pytest.raises(ValueError):
        _guard_values(["not-a-list"])


def test_read_sheet_bundle(tmp_path):
    fake = _FakeSheetsAPI(values=[["A", "B"], ["1", "2"]])
    svc = _service(fake, tmp_path)
    out = svc.read_sheet("s1", "A1:B2")
    assert out["range"] == "A1:B2"
    assert out["values"] == [["A", "B"], ["1", "2"]]
    assert out["name"] == "Founder OS"


def test_write_sheet(tmp_path):
    fake = _FakeSheetsAPI()
    svc = _service(fake, tmp_path)
    out = svc.write_sheet("s1", "A1", [["hello", "world"]])
    assert out["updated"] is True
    assert out["updated_cells"] == 2
    assert fake.calls[-1] == ("write", "s1", "A1", [["hello", "world"]])


def test_create_spreadsheet(tmp_path):
    fake = _FakeSheetsAPI()
    svc = _service(fake, tmp_path)
    out = svc.create_spreadsheet("Q2 Plan")
    assert out["id"] == "s-new"
    assert out["name"] == "Q2 Plan"


def test_get_spreadsheet_not_found(tmp_path):
    svc = _service(_FakeSheetsAPI(), tmp_path)
    with pytest.raises(GoogleNotFound):
        svc.get_spreadsheet("missing")


def test_find_spreadsheet_via_drive(tmp_path):
    fake_sheets = _FakeSheetsAPI()

    class _FakeDriveAPI:
        def list_files(self, *, query="", page_size=25):
            return [
                {"id": "x1", "name": "Q2 Revenue", "mimeType": "application/vnd.google-apps.spreadsheet"},
                {"id": "x2", "name": "Q2 Revenue", "mimeType": "application/vnd.google-apps.document"},
            ]

    fake_drive = DriveService(store=TokenStore(str(tmp_path / "d.json")), api=_FakeDriveAPI())
    svc = SheetsService(store=TokenStore(str(tmp_path / "s.json")), api=fake_sheets)
    out = svc.find_spreadsheet("Q2 Revenue", drive=fake_drive)
    assert [f["id"] for f in out] == ["x1"]


def test_status_no_token(tmp_path):
    svc = SheetsService(store=TokenStore(str(tmp_path / "s.json")))
    assert svc.status()["connected"] is False


def test_status_with_token_probe(tmp_path):
    store = TokenStore(str(tmp_path / "s.json"))
    store.save({"token": "x"})
    svc = SheetsService(store=store, api=_FakeSheetsAPI())
    assert svc.status()["connected"] is True


def test_http_error_mapping_403_link_shared(tmp_path):
    """Sheets reuses the shared mapper → maps 403 to permission wording."""
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    from app.services.google_http import GooglePermissionDenied

    exc = HttpError(Response({"status": 403}), b'{"error":{}}', uri="https://sheets.example")
    with pytest.raises(GooglePermissionDenied):
        _service(fake=_FakeSheetsAPI(), tmp_path=tmp_path)._run(lambda: (_ for _ in ()).throw(exc))