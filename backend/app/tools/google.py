"""Phase 7.5 — Google Drive / Sheets / Docs / YouTube tools.

All reads are permission 1. Visible writes (creating a spreadsheet/document,
writing sheet cells) are permission 2. The destructive / publish-style actions
(updating or deleting a YouTube video, uploading, overwriting document or sheet
content) are permission 2 *and* require explicit user confirmation — exactly
like ``delete_event``/``send_email`` the ToolManager gate blocks them until the
user approves.

Every tool is owner-only and shares the single Google OAuth connection; the
services own no secrets here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.docs import DocsError, docs_service
from app.services.drive import DriveError, drive_service
from app.services.google_http import (
    GoogleApiDisabled,
    GoogleBadRequest,
    GoogleNotConnected,
    GoogleNotFound,
    GooglePermissionDenied,
    GoogleRateLimited,
)
from app.services.sheets import SheetsError, sheets_service
from app.services.youtube import YoutubeError, youtube_service
from app.tools.base import Tool, ToolContext, ToolExecutionError, ToolResult


def _check(exc: Exception, service: str) -> None:
    if isinstance(exc, GoogleNotConnected):
        raise ToolExecutionError("no Google account is connected yet — connect via the Gmail panel.")
    if isinstance(exc, GoogleApiDisabled):
        raise ToolExecutionError(str(exc))
    if isinstance(exc, GooglePermissionDenied):
        raise ToolExecutionError(str(exc))
    if isinstance(exc, GoogleNotFound):
        raise ToolExecutionError(str(exc))
    if isinstance(exc, GoogleRateLimited):
        raise ToolExecutionError(str(exc))
    if isinstance(exc, GoogleBadRequest):
        raise ToolExecutionError(str(exc))
    raise ToolExecutionError(f"{service} is unavailable right now.")


def _drive_query(term: str) -> str:
    """Accept plain words ('Q2 plans') or a real Drive query ('name contains..')."""
    term = term.strip()
    lower = term.lower()
    if " contains " in lower or "=" in term or "mime" in lower or "trashed" in lower:
        return term
    return f"name contains '{term.replace(chr(39), '')}'"


# --------------------------------------------------------------------------- #
# Drive
# --------------------------------------------------------------------------- #
class SearchDriveArgs(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=10, ge=1, le=50)


class DriveFileSlim(BaseModel):
    id: str
    name: str
    mime_type: str
    link: str | None = None
    modified_time: str | None = None


class SearchDriveOutput(BaseModel):
    count: int
    files: list[DriveFileSlim]


class GoogleSearchDriveTool(Tool):
    name = "google_search_drive"
    description = (
        "Search the user's Google Drive. `query` can be a plain phrase like "
        "'Q2 plans' or a Drive filter like \"name contains 'plans' and "
        "mimeType='text/plain'\". Use before reading a file to find its id."
    )
    permission_level = 1
    owner_only = True
    args_model = SearchDriveArgs
    output_model = SearchDriveOutput

    def run(self, ctx: ToolContext, query: str, max_results: int = 10, **kwargs) -> ToolResult:
        try:
            files = drive_service.search_drive_files(query=_drive_query(query), max_results=max_results)
        except DriveError as exc:
            _check(exc, "Google Drive")
            raise
        slim = [
            {"id": f["id"], "name": f["name"], "mime_type": f["mime_type"],
             "link": f.get("link"), "modified_time": f.get("modified_time")}
            for f in files
        ]
        return ToolResult.success({"count": len(slim), "files": slim})


class ReadDriveFileArgs(BaseModel):
    file_id: str = Field(min_length=1, max_length=200)
    file_name: str = Field(default="", max_length=300, description="optional label so the result is easier to read")


class ReadDriveFileOutput(BaseModel):
    id: str
    name: str
    mime_type: str
    link: str | None = None
    content: str
    content_is_text: bool
    truncated: bool


class GoogleReadDriveFileTool(Tool):
    name = "google_read_drive_file"
    description = (
        "Read the text content of a Google Drive file by its id. Google Docs/Sheets "
        "come back as plain text or CSV; other files come as text when decodable. "
        "Use after google_search_drive."
    )
    permission_level = 1
    owner_only = True
    args_model = ReadDriveFileArgs
    output_model = ReadDriveFileOutput

    def run(self, ctx: ToolContext, file_id: str, file_name: str = "", **kwargs) -> ToolResult:
        try:
            out = drive_service.read_drive_file(file_id)
        except DriveError as exc:
            _check(exc, "Google Drive")
            raise
        return ToolResult.success(
            {
                "id": out["id"], "name": out["name"], "mime_type": out["mime_type"],
                "link": out.get("link"), "content": out["content"],
                "content_is_text": out["content_is_text"], "truncated": out["truncated"],
            }
        )


# --------------------------------------------------------------------------- #
# Sheets
# --------------------------------------------------------------------------- #
class FindSpreadsheetArgs(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=10, ge=1, le=50)


class FindSpreadsheetOutput(BaseModel):
    count: int
    spreadsheets: list[DriveFileSlim]


class GoogleFindSpreadsheetTool(Tool):
    name = "google_find_spreadsheet"
    description = "Find Google Sheets spreadsheets by name. Use before google_read_sheet to locate the id."
    permission_level = 1
    owner_only = True
    args_model = FindSpreadsheetArgs
    output_model = FindSpreadsheetOutput

    def run(self, ctx: ToolContext, name: str, max_results: int = 10, **kwargs) -> ToolResult:
        try:
            rows = sheets_service.find_spreadsheet(name, max_results=max_results)
        except SheetsError as exc:
            _check(exc, "Google Sheets")
            raise
        slim = [
            {"id": r["id"], "name": r["name"], "mime_type": r["mime_type"],
             "link": r.get("link"), "modified_time": r.get("modified_time")}
            for r in rows
        ]
        return ToolResult.success({"count": len(slim), "spreadsheets": slim})


class ReadSheetArgs(BaseModel):
    spreadsheet_id: str = Field(min_length=1, max_length=200)
    range: str = Field(default="A1:F30", min_length=1, max_length=50)


class ReadSheetOutput(BaseModel):
    spreadsheet_id: str
    name: str | None = None
    range: str
    values: list[list[str]]


class GoogleReadSheetTool(Tool):
    name = "google_read_sheet"
    description = (
        "Read cell values from a Google Sheet, e.g. range 'A1:F30'. Returns rows of "
        "strings like a table. Use after google_find_spreadsheet."
    )
    permission_level = 1
    owner_only = True
    args_model = ReadSheetArgs
    output_model = ReadSheetOutput

    def run(self, ctx: ToolContext, spreadsheet_id: str, range: str = "A1:F30", **kwargs) -> ToolResult:
        try:
            out = sheets_service.read_sheet(spreadsheet_id, range_=range)
        except SheetsError as exc:
            _check(exc, "Google Sheets")
            raise
        return ToolResult.success(
            {"spreadsheet_id": out["spreadsheet_id"], "name": out["name"],
             "range": out["range"], "values": out["values"]}
        )


class WriteSheetArgs(BaseModel):
    spreadsheet_id: str = Field(min_length=1, max_length=200)
    range: str = Field(min_length=1, max_length=50, description="e.g. 'A1' or 'Sheet2!A1:C3'")
    values: list[list[str]] = Field(..., min_length=1, description="rows of cells, e.g. [['Name','Amount'],['Tea',3]]")


class WriteSheetOutput(BaseModel):
    spreadsheet_id: str
    range: str
    updated_cells: int
    updated: bool


class GoogleWriteSheetTool(Tool):
    name = "google_write_sheet"
    description = (
        "Write cell values into a Google Sheet (overwrites cells at that range only). "
        "Requires explicit user confirmation. Use to fill a tracker, log, or table."
    )
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = WriteSheetArgs
    output_model = WriteSheetOutput

    def run(self, ctx: ToolContext, spreadsheet_id: str, range: str, values: list[list[str]], **kwargs) -> ToolResult:
        try:
            out = sheets_service.write_sheet(spreadsheet_id, range_=range, values=values)
        except SheetsError as exc:
            _check(exc, "Google Sheets")
            raise
        return ToolResult.success(
            {"spreadsheet_id": out["spreadsheet_id"], "range": out["range"],
             "updated_cells": out["updated_cells"], "updated": out["updated"]}
        )


class CreateSpreadsheetArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CreateSpreadsheetOutput(BaseModel):
    id: str
    name: str
    url: str | None = None
    tabs: list[str] = []
    created: bool = True


class GoogleCreateSpreadsheetTool(Tool):
    name = "google_create_spreadsheet"
    description = "Create a brand-new Google Sheets spreadsheet with the given title."
    permission_level = 2
    owner_only = True
    args_model = CreateSpreadsheetArgs
    output_model = CreateSpreadsheetOutput

    def run(self, ctx: ToolContext, title: str, **kwargs) -> ToolResult:
        try:
            created = sheets_service.create_spreadsheet(title)
        except SheetsError as exc:
            _check(exc, "Google Sheets")
            raise
        return ToolResult.success(
            {"id": created["id"], "name": created["name"], "url": created.get("url"),
             "tabs": created.get("tabs") or [], "created": True}
        )


# --------------------------------------------------------------------------- #
# Docs
# --------------------------------------------------------------------------- #
class FindDocumentArgs(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=10, ge=1, le=50)


class FindDocumentOutput(BaseModel):
    count: int
    documents: list[DriveFileSlim]


class GoogleFindDocumentTool(Tool):
    name = "google_find_document"
    description = "Find Google Docs documents by name. Use before google_read_document to locate the id."
    permission_level = 1
    owner_only = True
    args_model = FindDocumentArgs
    output_model = FindDocumentOutput

    def run(self, ctx: ToolContext, name: str, max_results: int = 10, **kwargs) -> ToolResult:
        try:
            rows = docs_service.find_document(name, max_results=max_results)
        except DocsError as exc:
            _check(exc, "Google Docs")
            raise
        slim = [
            {"id": r["id"], "name": r["name"], "mime_type": r["mime_type"],
             "link": r.get("link"), "modified_time": r.get("modified_time")}
            for r in rows
        ]
        return ToolResult.success({"count": len(slim), "documents": slim})


class ReadDocumentArgs(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    document_name: str = Field(default="", max_length=300, description="optional label for readability")


class ReadDocumentOutput(BaseModel):
    id: str
    title: str
    text: str
    truncated: bool


class GoogleReadDocumentTool(Tool):
    name = "google_read_document"
    description = "Read the full text of a Google Docs document by id (tables included)."
    permission_level = 1
    owner_only = True
    args_model = ReadDocumentArgs
    output_model = ReadDocumentOutput

    def run(self, ctx: ToolContext, document_id: str, document_name: str = "", **kwargs) -> ToolResult:
        try:
            out = docs_service.read_document(document_id)
        except DocsError as exc:
            _check(exc, "Google Docs")
            raise
        return ToolResult.success(
            {"id": out["id"], "title": out["title"], "text": out["text"], "truncated": out["truncated"]}
        )


class CreateDocumentArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CreateDocumentOutput(BaseModel):
    id: str
    title: str
    created: bool = True


class GoogleCreateDocumentTool(Tool):
    name = "google_create_document"
    description = "Create a brand-new Google Docs document with the given title."
    permission_level = 2
    owner_only = True
    args_model = CreateDocumentArgs
    output_model = CreateDocumentOutput

    def run(self, ctx: ToolContext, title: str, **kwargs) -> ToolResult:
        try:
            created = docs_service.create_document(title)
        except DocsError as exc:
            _check(exc, "Google Docs")
            raise
        return ToolResult.success({"id": created["id"], "title": created["title"], "created": True})


class UpdateDocumentArgs(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)
    append: bool = Field(default=False, description="True to append at the end; False to replace the whole document")


class UpdateDocumentOutput(BaseModel):
    id: str
    mode: str
    characters_written: int


class GoogleUpdateDocumentTool(Tool):
    name = "google_update_document"
    description = (
        "Write text into a Google Docs document. append=False replaces all content; "
        "append=True adds at the end. Requires explicit user confirmation."
    )
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = UpdateDocumentArgs
    output_model = UpdateDocumentOutput

    def run(self, ctx: ToolContext, document_id: str, text: str, append: bool = False, **kwargs) -> ToolResult:
        try:
            out = docs_service.update_document(document_id, text, append=append)
        except DocsError as exc:
            _check(exc, "Google Docs")
            raise
        return ToolResult.success({"id": out["id"], "mode": out["mode"], "characters_written": out["characters_written"]})


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
class SearchYoutubeArgs(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=10, ge=1, le=50)


class YoutubeVideoSlim(BaseModel):
    id: str
    title: str
    channel: str | None = None
    published_at: str | None = None
    url: str


class SearchYoutubeOutput(BaseModel):
    count: int
    videos: list[YoutubeVideoSlim]


class GoogleSearchYoutubeTool(Tool):
    name = "google_search_youtube"
    description = "Search YouTube by keyword and return matching videos (id, title, channel)."
    permission_level = 1
    owner_only = True
    args_model = SearchYoutubeArgs
    output_model = SearchYoutubeOutput

    def run(self, ctx: ToolContext, query: str, max_results: int = 10, **kwargs) -> ToolResult:
        try:
            videos = youtube_service.search_youtube(query, max_results=max_results)
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        slim = [
            {"id": v["id"], "title": v["title"], "channel": v.get("channel"),
             "published_at": v.get("published_at"), "url": v["url"]}
            for v in videos
        ]
        return ToolResult.success({"count": len(slim), "videos": slim})


class YoutubeVideoInfoArgs(BaseModel):
    video_id: str = Field(min_length=1, max_length=100)


class YoutubeVideoInfoOutput(BaseModel):
    id: str
    title: str
    description: str
    channel_title: str | None = None
    published_at: str | None = None
    duration: str | None = None
    view_count: str | None = None
    like_count: str | None = None
    url: str


class GoogleYoutubeVideoInfoTool(Tool):
    name = "google_youtube_video_info"
    description = "Get details about one YouTube video: title, description, duration, views, likes."
    permission_level = 1
    owner_only = True
    args_model = YoutubeVideoInfoArgs
    output_model = YoutubeVideoInfoOutput

    def run(self, ctx: ToolContext, video_id: str, **kwargs) -> ToolResult:
        try:
            v = youtube_service.get_video(video_id)
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        return ToolResult.success(
            {
                "id": v["id"], "title": v["title"], "description": v["description"],
                "channel_title": v.get("channel_title"), "published_at": v.get("published_at"),
                "duration": v.get("duration"), "view_count": v.get("view_count"),
                "like_count": v.get("like_count"), "url": v["url"],
            }
        )


class ListUploadsArgs(BaseModel):
    max_results: int = Field(default=25, ge=1, le=50)


class ListUploadsOutput(BaseModel):
    count: int
    videos: list[YoutubeVideoSlim]


class GoogleYoutubeListUploadsTool(Tool):
    name = "google_youtube_list_uploads"
    description = "List the user's own recently uploaded YouTube videos."
    permission_level = 1
    owner_only = True
    args_model = ListUploadsArgs
    output_model = ListUploadsOutput

    def run(self, ctx: ToolContext, max_results: int = 25, **kwargs) -> ToolResult:
        try:
            videos = youtube_service.list_uploads(max_results=max_results)
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        slim = [
            {"id": v["id"], "title": v["title"], "channel": v.get("channel"),
             "published_at": v.get("published_at"), "url": v["url"]}
            for v in videos
        ]
        return ToolResult.success({"count": len(slim), "videos": slim})


class UpdateVideoArgs(BaseModel):
    video_id: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5_000)


class UpdateVideoOutput(BaseModel):
    id: str
    title: str
    url: str


class GoogleYoutubeUpdateVideoTool(Tool):
    name = "google_youtube_update_video"
    description = "Update the title/description of one of the user's YouTube videos. Requires explicit confirmation."
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = UpdateVideoArgs
    output_model = UpdateVideoOutput

    def run(self, ctx: ToolContext, video_id: str, **kwargs) -> ToolResult:
        try:
            v = youtube_service.update_video(video_id, title=kwargs.get("title"), description=kwargs.get("description"))
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        return ToolResult.success({"id": v["id"], "title": v["title"], "url": v["url"]})


class UploadVideoArgs(BaseModel):
    file_path: str = Field(min_length=1, max_length=500, description="absolute path to a local video file on this machine")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5_000)
    privacy: str = Field(default="private", pattern="^(private|unlisted|public)$")


class UploadVideoOutput(BaseModel):
    id: str
    title: str
    privacy: str
    url: str


class GoogleYoutubeUploadVideoTool(Tool):
    name = "google_youtube_upload_video"
    description = (
        "Upload a local video file to the user's YouTube channel. Defaults to "
        "'private' so nothing is published unintentionally. Requires explicit confirmation."
    )
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = UploadVideoArgs
    output_model = UploadVideoOutput

    def run(self, ctx: ToolContext, file_path: str, title: str, description: str = "", privacy: str = "private", **kwargs) -> ToolResult:
        try:
            out = youtube_service.upload_video(
                file_path, title=title, description=description, privacy=privacy
            )
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        return ToolResult.success(
            {"id": out["id"], "title": out["title"], "privacy": out["privacy"], "url": out["url"]}
        )


class DeleteVideoArgs(BaseModel):
    video_id: str = Field(min_length=1, max_length=100)


class DeleteVideoOutput(BaseModel):
    id: str
    deleted: bool


class GoogleYoutubeDeleteVideoTool(Tool):
    name = "google_youtube_delete_video"
    description = "Permanently delete one of the user's YouTube videos. Requires explicit confirmation."
    permission_level = 2
    owner_only = True
    requires_confirmation = True
    args_model = DeleteVideoArgs
    output_model = DeleteVideoOutput

    def run(self, ctx: ToolContext, video_id: str, **kwargs) -> ToolResult:
        try:
            out = youtube_service.delete_video(video_id)
        except YoutubeError as exc:
            _check(exc, "YouTube")
            raise
        return ToolResult.success({"id": out["id"], "deleted": out["deleted"]})


__all__ = [
    "GoogleCreateDocumentTool",
    "GoogleCreateSpreadsheetTool",
    "GoogleFindDocumentTool",
    "GoogleFindSpreadsheetTool",
    "GoogleReadDocumentTool",
    "GoogleReadDriveFileTool",
    "GoogleReadSheetTool",
    "GoogleSearchDriveTool",
    "GoogleSearchYoutubeTool",
    "GoogleUpdateDocumentTool",
    "GoogleWriteSheetTool",
    "GoogleYoutubeDeleteVideoTool",
    "GoogleYoutubeListUploadsTool",
    "GoogleYoutubeUpdateVideoTool",
    "GoogleYoutubeUploadVideoTool",
    "GoogleYoutubeVideoInfoTool",
]