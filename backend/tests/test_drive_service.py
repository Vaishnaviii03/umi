"""Phase 7.5 — Drive service tests (no real Google calls)."""

import pytest

from app.services.drive import DriveNotConnected, DriveService
from app.services.drive.api import DriveAPI, decode_content, normalize_drive_file
from app.services.gmail.token_store import TokenStore
from app.services.google_http import GoogleNotFound


class _FakeAPI:
    def __init__(self, files=None):
        self.files = list(files or [])
        self.reads = {}
        self.calls = []

    def list_files(self, *, query="", page_size=25):
        self.calls.append(("list", query, page_size))
        return self.files

    def get_file(self, file_id):
        self.calls.append(("get", file_id))
        for f in self.files:
            if f["id"] == file_id:
                return f
        raise GoogleNotFound("drive not found")

    def read_file(self, file_id):
        self.calls.append(("read", file_id))
        return {"meta": self.get_file(file_id), "media": self.reads.get(file_id, "hello world")}


FILE = {
    "id": "f1",
    "name": "Founder OS",
    "mimeType": "application/vnd.google-apps.document",
    "parents": [],
    "webViewLink": "https://drive.google.com/f1",
    "size": "42",
    "modifiedTime": "2026-09-01T10:00:00+00:00",
    "createdTime": "2026-08-01T10:00:00+00:00",
    "trashed": False,
}


def _service(fake=None, tmp_path=""):
    return DriveService(store=TokenStore(str(tmp_path / "d.json")), api=fake or _FakeAPI())


def test_normalize_drive_file():
    out = normalize_drive_file(FILE)
    assert out["id"] == "f1"
    assert out["name"] == "Founder OS"
    assert out["mime_type"] == "application/vnd.google-apps.document"
    assert out["trashed"] is False


def test_search_drive_files(tmp_path):
    fake = _FakeAPI([FILE])
    svc = _service(fake, tmp_path)
    out = svc.search_drive_files(query="name contains 'Founder'", max_results=5)
    assert out[0]["id"] == "f1"
    assert fake.calls[0] == ("list", "name contains 'Founder'", 5)


def test_get_drive_file(tmp_path):
    fake = _FakeAPI([FILE])
    svc = _service(fake, tmp_path)
    out = svc.get_drive_file("f1")
    assert out["name"] == "Founder OS"
    with pytest.raises(GoogleNotFound):
        svc.get_drive_file("nope")


def test_read_drive_file_bundle(tmp_path):
    fake = _FakeAPI([FILE])
    fake.reads["f1"] = "the full document text"
    svc = _service(fake, tmp_path)
    out = svc.read_drive_file("f1")
    assert out["content"] == "the full document text"
    assert out["content_is_text"] is True
    assert out["truncated"] is False


def test_read_drive_file_binary_base64(tmp_path):
    import base64 as _b64

    payload = b"\x89PNG\x01\x02"
    fake = _FakeAPI([FILE])
    fake.reads["f1"] = payload
    svc = _service(fake, tmp_path)
    out = svc.read_drive_file("f1")
    assert out["content_is_text"] is False
    assert _b64.b64decode(out["content"]) == payload


def test_read_drive_file_truncates(tmp_path):
    big = "x" * 60_000
    fake = _FakeAPI([FILE])
    fake.reads["f1"] = big
    svc = _service(fake, tmp_path)
    out = svc.read_drive_file("f1")
    assert out["truncated"] is True
    assert len(out["content"]) == 50_000


def test_not_connected_without_token(tmp_path):
    svc = DriveService(store=TokenStore(str(tmp_path / "t.json")))
    with pytest.raises(DriveNotConnected):
        svc._get_api()


def test_status_with_api(tmp_path):
    store = TokenStore(str(tmp_path / "t.json"))
    store.save({"token": "x"})
    svc = DriveService(store=store, api=_FakeAPI([FILE]))
    assert svc.status()["connected"] is True


def test_decode_content_helpers():
    assert decode_content(b"hello") == ("hello", True)
    assert decode_content("already text") == ("already text", True)


def test_http_error_mapping_api_disabled():
    """An accessNotConfigured 403 must become a helpful 'enable API' message
    that never leaks the response body."""
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    from app.services.google_http import GoogleApiDisabled, map_http_error

    resp = Response({"status": 403})
    content = b'{"error":{"message":"Drive API has not been used in project 123 before","reason":"accessNotConfigured"}}'
    exc = HttpError(resp, content, uri="https://drive.example")
    with pytest.raises(GoogleApiDisabled) as excinfo:
        map_http_error(exc, "Google Drive")
    assert "Cloud Console" in str(excinfo.value)
    assert "project 123" not in str(excinfo.value)


def test_http_error_mapping_404():
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    from app.services.google_http import GoogleNotFound, map_http_error

    exc = HttpError(Response({"status": 404}), b'{"error":{"message":"File not found: f99"}}', uri="https://drive.example")
    with pytest.raises(GoogleNotFound) as excinfo:
        map_http_error(exc, "Google Drive")
    assert "f99" not in str(excinfo.value)
    assert "couldn't find" in str(excinfo.value)


def test_drive_api_requires_same_token_store_pattern():
    """DriveAPI builds via shared credentials_from_store — ensure the import path lives."""
    import app.services.drive.api as dapi
    assert dapi.credentials_from_store is not None


def test_drive_api_read_file_dispatch(tmp_path):
    """Drive export/download dispatch by mimeType captured at the API layer."""
    from app.services.drive import api as dapi

    captured = {}

    class _Media:
        def export(self, fileId, mimeType):
            captured["op"] = ("export", mimeType)
            return type("_R", (), {"execute": lambda self: "csv!".encode()})()
        def get_media(self, fileId):
            captured["op"] = ("media",)
            return type("_R", (), {"execute": lambda self: b"\x00\x01"})()
        def get(self, fileId, fields, supportsAllDrives):
            return type("_R", (), {"execute": lambda self: FILE})()
        def list(self, q=None, pageSize=1, fields=None, supportsAllDrives=True):
            return type("_R", (), {"execute": lambda self: {"files": []}})()

    class _Files:
        def __init__(self, media): self._m = media
        def export(self, **kw): return self._m.export(**kw)
        def get_media(self, **kw): return self._m.get_media(**kw)
        def get(self, **kw): return self._m.get(**kw)
        def list(self, **kw): return self._m.list(**kw)

    class _Svc:
        def __init__(self): self.media = _Media()
        def files(self): return _Files(self.media)

    api = dapi.DriveAPI(service=_Svc())
    out = api.read_file("f1")
    assert captured["op"] == ("export", "text/plain")