"""Phase 7.5 — Docs service tests (no real Google calls)."""

import pytest

from app.services.docs import DocsService
from app.services.docs.service import extract_text
from app.services.drive.service import DriveService
from app.services.gmail.token_store import TokenStore
from app.services.google_http import GoogleNotFound, GoogleServiceError


_BODY = {
    "content": [
        {
            "paragraph": {
                "elements": [
                    {"textRun": {"content": "Hello\n"}},
                    {"textRun": {"content": "World\n"}},
                ]
            }
        },
        {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "content": [{"paragraph": {"elements": [{"textRun": {"content": "Cell A\n"}}]}}]
                            },
                            {
                                "content": [{"paragraph": {"elements": [{"textRun": {"content": "Cell B\n"}}]}}]
                            },
                        ]
                    }
                ]
            }
        },
    ]
}


class _FakeDocsAPI:
    def __init__(self, doc=None):
        self.doc = doc or {"documentId": "d1", "title": "Founder Notes", "body": _BODY}
        self.ops = []

    def get_document(self, document_id):
        self.ops.append(("get", document_id))
        if document_id != "d1":
            raise GoogleNotFound("nope")
        return self.doc

    def create_document(self, title):
        self.ops.append(("create", title))
        return {"documentId": "d-new", "title": title}

    def batch_update(self, document_id, requests):
        self.ops.append(("batch", document_id, requests))
        return {"replies": []}


def _doc_body(start, end, instr=""):
    return {
        "content": [
            {"startIndex": 0, "endIndex": 1},
            {"startIndex": 1, "endIndex": end, "paragraph": {"elements": [{"textRun": {"content": instr}}]}},
        ]
    }


def _service(fake=None, tmp_path=""):
    return DocsService(store=TokenStore(str(tmp_path / "doc.json")), api=fake or _FakeDocsAPI())


def test_extract_text_paragraphs_and_tables():
    text = extract_text(_BODY)
    assert "Hello" in text and "World" in text
    assert "Cell A" in text and "Cell B" in text


def test_get_document_bundle(tmp_path):
    svc = _service(_FakeDocsAPI(), tmp_path)
    out = svc.get_document("d1")
    assert out["id"] == "d1"
    assert out["title"] == "Founder Notes"
    assert "Hello" in out["text"]


def test_read_document_missing(tmp_path):
    svc = _service(_FakeDocsAPI(doc={"documentId": "d1", "title": "x", "body": {"content": []}}), tmp_path)
    with pytest.raises(GoogleNotFound):
        svc.get_document("missing")


def test_create_document(tmp_path):
    svc = _service(_FakeDocsAPI(), tmp_path)
    out = svc.create_document("Q3 Goals")
    assert out["id"] == "d-new"
    assert out["title"] == "Q3 Goals"


def test_update_document_append(tmp_path):
    fake = _FakeDocsAPI()
    fake.doc = {"documentId": "d1", "title": "x", "body": _doc_body(1, 5)}
    svc = _service(fake, tmp_path)
    out = svc.update_document("d1", "New line", append=True)
    assert out["mode"] == "append"
    req_type, _, requests = fake.ops[-1]
    assert req_type == "batch"
    assert "insertText" in requests[0]
    assert requests[0]["insertText"]["endOfSegmentLocation"] == {}


def test_update_document_replace(tmp_path):
    fake = _FakeDocsAPI()
    fake.doc = {"documentId": "d1", "title": "x", "body": _doc_body(1, 5)}
    svc = _service(fake, tmp_path)
    out = svc.update_document("d1", "Rewritten", append=False)
    assert out["mode"] == "replace"
    _, _, requests = fake.ops[-1]
    assert requests[0]["deleteContentRange"]["range"]["startIndex"] == 1


def test_update_document_rejects_empty(tmp_path):
    svc = _service(_FakeDocsAPI(), tmp_path)
    with pytest.raises(GoogleServiceError):
        svc.update_document("d1", "   ", append=True)


def test_find_document_via_drive(tmp_path):
    class _FakeDriveAPI:
        def list_files(self, *, query="", page_size=25):
            return [
                {"id": "x1", "name": "Roadmap", "mimeType": "application/vnd.google-apps.document"},
                {"id": "x2", "name": "Roadmap", "mimeType": "application/vnd.google-apps.spreadsheet"},
            ]

    fake_drive = DriveService(store=TokenStore(str(tmp_path / "d.json")), api=_FakeDriveAPI())
    svc = DocsService(store=TokenStore(str(tmp_path / "doc.json")), api=_FakeDocsAPI())
    out = svc.find_document("Roadmap", drive=fake_drive)
    assert [f["id"] for f in out] == ["x1"]


def test_status_no_token(tmp_path):
    svc = DocsService(store=TokenStore(str(tmp_path / "doc.json")))
    assert svc.status()["connected"] is False


def test_status_with_token_probe(tmp_path):
    store = TokenStore(str(tmp_path / "doc.json"))
    store.save({"token": "x"})
    svc = DocsService(store=store, api=_FakeDocsAPI())
    assert svc.status()["connected"] is True


def test_read_document_truncates(tmp_path):
    big = "x" * 60_000
    fake = _FakeDocsAPI(doc={"documentId": "d1", "title": "Big", "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": big}}]}}] }})
    svc = _service(fake, tmp_path)
    out = svc.read_document("d1")
    assert out["truncated"] is True
    assert len(out["text"]) == 50_000