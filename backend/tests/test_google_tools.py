"""Phase 7.5 — Google tool tests (execution with stubbed services).

Stubs the four module-level singletons the tools call, so no Google API or
token store is touched. Also pins the permission/confirmation layout that keeps
reads cheap and publish/destructive actions gated.
"""

import pytest

from app.config import settings
from app.tools import (
    ConfirmationRequired,
    ToolContext,
    ToolExecutionError,
    tool_manager,
)
import app.tools.google as goog

OWNER = str(settings.owner_id)


def ctx(**extra):
    extra.setdefault("confirmed", True)
    return ToolContext(user_id=OWNER, extra=extra)


def _monkeypatch_services(monkeypatch, *, drive=None, sheets=None, docs=None, youtube=None):
    if drive is not None:
        monkeypatch.setattr(goog, "drive_service", drive)
    if sheets is not None:
        monkeypatch.setattr(goog, "sheets_service", sheets)
    if docs is not None:
        monkeypatch.setattr(goog, "docs_service", docs)
    if youtube is not None:
        monkeypatch.setattr(goog, "youtube_service", youtube)


# --------------------------------------------------------------------------- #
# Reading / discovery tools
# --------------------------------------------------------------------------- #
def test_google_search_drive_wire(monkeypatch):
    class _Stub:
        def search_drive_files(self, query="", max_results=10):
            assert "name contains" in query
            return [{"id": "f1", "name": "Plans", "mime_type": "text/plain", "link": None, "modified_time": None}]

    _monkeypatch_services(monkeypatch, drive=_Stub())
    result = tool_manager.execute_tool("google_search_drive", {"query": "Plans"}, ctx())
    assert result.status == "success"
    assert result.data["files"][0]["id"] == "f1"


def test_google_read_drive_file_wire(monkeypatch):
    class _Stub:
        def read_drive_file(self, file_id):
            return {"id": file_id, "name": "Plans", "mime_type": "text/plain", "link": None,
                    "content": "hello", "content_is_text": True, "truncated": False}

    _monkeypatch_services(monkeypatch, drive=_Stub())
    result = tool_manager.execute_tool("google_read_drive_file", {"file_id": "f1"}, ctx())
    assert result.data["content"] == "hello"
    assert result.data["truncated"] is False


def test_google_find_spreadsheet_wire(monkeypatch):
    class _Stub:
        def find_spreadsheet(self, name, max_results=10):
            return [{"id": "s1", "name": name, "mime_type": "application/vnd.google-apps.spreadsheet", "link": None, "modified_time": None}]

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    result = tool_manager.execute_tool("google_find_spreadsheet", {"name": "Q2"}, ctx())
    assert result.data["count"] == 1


def test_google_read_sheet_wire(monkeypatch):
    class _Stub:
        def read_sheet(self, spreadsheet_id, range_="A1:F30"):
            return {"spreadsheet_id": spreadsheet_id, "name": "Sheet", "range": range_, "values": [["a"], ["b"]]}

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    result = tool_manager.execute_tool("google_read_sheet", {"spreadsheet_id": "s1", "range": "A1:B2"}, ctx())
    assert result.data["values"] == [["a"], ["b"]]
    assert result.data["range"] == "A1:B2"


def test_google_find_document_wire(monkeypatch):
    class _Stub:
        def find_document(self, name, max_results=10):
            return [{"id": "d1", "name": name, "mime_type": "application/vnd.google-apps.document", "link": None, "modified_time": None}]

    _monkeypatch_services(monkeypatch, docs=_Stub())
    result = tool_manager.execute_tool("google_find_document", {"name": "Roadmap"}, ctx())
    assert result.data["documents"][0]["id"] == "d1"


def test_google_read_document_wire(monkeypatch):
    class _Stub:
        def read_document(self, document_id):
            return {"id": document_id, "title": "Roadmap", "text": "quarterly goals", "truncated": False}

    _monkeypatch_services(monkeypatch, docs=_Stub())
    result = tool_manager.execute_tool("google_read_document", {"document_id": "d1"}, ctx())
    assert "quarterly goals" in result.data["text"]


def test_google_search_youtube_wire(monkeypatch):
    class _Stub:
        def search_youtube(self, query, max_results=10):
            return [{"id": "v1", "title": "Clip", "channel": "Me", "published_at": "2026-01-01", "url": "https://youtu.be/v1"}]

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    result = tool_manager.execute_tool("google_search_youtube", {"query": "clip"}, ctx())
    assert result.data["videos"][0]["id"] == "v1"


def test_google_youtube_video_info_wire(monkeypatch):
    class _Stub:
        def get_video(self, video_id):
            return {"id": video_id, "title": "Clip", "description": "d", "channel_title": "Me",
                    "published_at": None, "duration": "PT1M", "view_count": "5", "like_count": "1", "url": "https://youtu.be/v1"}

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    result = tool_manager.execute_tool("google_youtube_video_info", {"video_id": "v1"}, ctx())
    assert result.data["duration"] == "PT1M"


def test_google_youtube_list_uploads_wire(monkeypatch):
    class _Stub:
        def list_uploads(self, max_results=25):
            return [{"id": "up1", "title": "Latest", "channel": "Me", "published_at": None, "url": "https://youtu.be/up1"}]

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    result = tool_manager.execute_tool("google_youtube_list_uploads", {"max_results": 5}, ctx())
    assert result.data["count"] == 1


# --------------------------------------------------------------------------- #
# Writes: confirmation-gated
# --------------------------------------------------------------------------- #
def test_google_write_sheet_requires_confirmation(monkeypatch):
    class _Stub:
        def write_sheet(self, **kw):
            raise AssertionError("should not run without confirmation")

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("google_write_sheet", {"spreadsheet_id": "s1", "range": "A1", "values": [["x"]]}, ToolContext(user_id=OWNER))


def test_google_write_sheet_confirmed(monkeypatch):
    class _Stub:
        def write_sheet(self, spreadsheet_id, range_, values):
            return {"spreadsheet_id": spreadsheet_id, "range": range_, "updated_cells": len(values[0]), "updated": True}

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    result = tool_manager.execute_tool("google_write_sheet", {"spreadsheet_id": "s1", "range": "A1", "values": [["x", "y"]]}, ctx())
    assert result.data["updated"] is True
    assert result.data["updated_cells"] == 2


def test_google_create_spreadsheet_wire(monkeypatch):
    class _Stub:
        def create_spreadsheet(self, title):
            return {"id": "s-new", "name": title, "url": None, "tabs": ["Sheet1"]}

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    result = tool_manager.execute_tool("google_create_spreadsheet", {"title": "Plan"}, ctx())
    assert result.data["id"] == "s-new"


def test_google_create_document_wire(monkeypatch):
    class _Stub:
        def create_document(self, title):
            return {"id": "d-new", "title": title}

    _monkeypatch_services(monkeypatch, docs=_Stub())
    result = tool_manager.execute_tool("google_create_document", {"title": "Notes"}, ctx())
    assert result.data["id"] == "d-new"


def test_google_update_document_requires_confirmation(monkeypatch):
    class _Stub:
        def update_document(self, **kw):
            raise AssertionError("should not run without confirmation")

    _monkeypatch_services(monkeypatch, docs=_Stub())
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("google_update_document", {"document_id": "d1", "text": "hi"}, ToolContext(user_id=OWNER))


def test_google_update_document_confirmed(monkeypatch):
    class _Stub:
        def update_document(self, document_id, text, append=False):
            return {"id": document_id, "mode": "append" if append else "replace", "characters_written": len(text)}

    _monkeypatch_services(monkeypatch, docs=_Stub())
    result = tool_manager.execute_tool("google_update_document", {"document_id": "d1", "text": "hi", "append": True}, ctx())
    assert result.data["mode"] == "append"


def test_google_youtube_upload_requires_confirmation(monkeypatch):
    class _Stub:
        def upload_video(self, **kw):
            raise AssertionError("should not run without confirmation")

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("google_youtube_upload_video", {"file_path": "/tmp/x.mp4", "title": "T"}, ToolContext(user_id=OWNER))


def test_google_youtube_upload_confirmed(monkeypatch):
    class _Stub:
        def upload_video(self, file_path, title, description="", privacy="private"):
            return {"id": "new-vid", "title": title, "privacy": privacy, "url": "https://youtu.be/new-vid"}

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    result = tool_manager.execute_tool("google_youtube_upload_video", {"file_path": "/tmp/x.mp4", "title": "T"}, ctx())
    assert result.data["privacy"] == "private"


def test_google_youtube_update_video_requires_confirmation(monkeypatch):
    class _Stub:
        def update_video(self, **kw):
            raise AssertionError("should not run without confirmation")

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("google_youtube_update_video", {"video_id": "v1", "title": "New"}, ToolContext(user_id=OWNER))


def test_google_youtube_delete_video_requires_confirmation(monkeypatch):
    class _Stub:
        def delete_video(self, **kw):
            raise AssertionError("should not run without confirmation")

    _monkeypatch_services(monkeypatch, youtube=_Stub())
    with pytest.raises(ConfirmationRequired):
        tool_manager.execute_tool("google_youtube_delete_video", {"video_id": "v1"}, ToolContext(user_id=OWNER))


# --------------------------------------------------------------------------- #
# Errors map to safe messages
# --------------------------------------------------------------------------- #
def test_read_drive_file_not_connected_message(monkeypatch):
    from app.services.google_http import GoogleNotConnected

    class _Stub:
        def read_drive_file(self, file_id):
            raise GoogleNotConnected("no Google account connected yet")

    _monkeypatch_services(monkeypatch, drive=_Stub())
    with pytest.raises(ToolExecutionError) as excinfo:
        tool_manager.execute_tool("google_read_drive_file", {"file_id": "f1"}, ctx())
    assert "Gmail panel" in str(excinfo.value)


def test_read_sheet_api_disabled_message(monkeypatch):
    from app.services.google_http import GoogleApiDisabled

    class _Stub:
        def read_sheet(self, spreadsheet_id, range_="A1:F30"):
            raise GoogleApiDisabled("enable the Google Sheets API in Cloud Console")

    _monkeypatch_services(monkeypatch, sheets=_Stub())
    with pytest.raises(ToolExecutionError) as excinfo:
        tool_manager.execute_tool("google_read_sheet", {"spreadsheet_id": "s1"}, ctx())
    assert "Cloud Console" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Permission layout pinned
# --------------------------------------------------------------------------- #
def test_google_tool_permissions_pinned():
    catalog = {t["name"]: t for t in tool_manager.catalog()}
    reads = {
        "google_search_drive", "google_read_drive_file", "google_find_spreadsheet",
        "google_read_sheet", "google_find_document", "google_read_document",
        "google_search_youtube", "google_youtube_video_info", "google_youtube_list_uploads",
    }
    confirmed = {
        "google_write_sheet", "google_update_document",
        "google_youtube_update_video", "google_youtube_upload_video", "google_youtube_delete_video",
    }
    for name in reads:
        assert catalog[name]["permission_level"] == 1, name
        assert catalog[name]["requires_confirmation"] is False, name
    for name in confirmed:
        assert catalog[name]["permission_level"] == 2, name
        assert catalog[name]["requires_confirmation"] is True, name
    for name in ("google_create_spreadsheet", "google_create_document"):
        assert catalog[name]["permission_level"] == 2, name
        assert catalog[name]["requires_confirmation"] is False, name
    for name in catalog:
        if name.startswith("google_"):
            assert catalog[name]["owner_only"] is True, name