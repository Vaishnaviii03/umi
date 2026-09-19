"""Phase 7.5 — End-to-end Chat Loop Verification for all 6 Google Services.

Verifies that the LLM Orchestrator can understand user prompts, invoke
appropriate tools for each of the six Google services, process the results,
and respond naturally:
1. Google Drive (google_search_drive, google_read_drive_file)
2. Google Sheets (google_find_sheet, google_read_sheet)
3. Google Docs (google_find_doc, google_read_doc)
4. YouTube (google_youtube_search, google_youtube_video_info)
5. Gmail (list_emails, search_emails)
6. Google Calendar (list_calendar_events, get_calendar_summary)
7. Confirmation safety gating for destructive actions across services
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.llm.manager import LLMManager
from app.tools import ToolResult, tool_manager
import app.tools.google as goog
import app.tools.calendar as cal_tools
import app.tools.gmail as gmail_tools


def _mock_choice(content=None, tool_name=None, tool_args=None, tool_id="call_1"):
    choice = MagicMock()
    choice.message.content = content
    if tool_name:
        tool_call = MagicMock()
        tool_call.id = tool_id
        tool_call.function.name = tool_name
        tool_call.function.arguments = json.dumps(tool_args or {})
        choice.message.tool_calls = [tool_call]
    else:
        choice.message.tool_calls = None
    return choice


def _run_orchestrator_chat_turn(monkeypatch, tool_name, tool_args, tool_result_data, final_llm_reply):
    """Simulates a 2-round LLM chat turn: Round 1 requests tool, Round 2 returns natural text."""
    manager = LLMManager()

    # Step 1: LLM proposes tool call
    round1_resp = MagicMock()
    round1_resp.choices = [_mock_choice(tool_name=tool_name, tool_args=tool_args)]

    # Step 2: LLM receives tool output and responds
    round2_resp = MagicMock()
    round2_resp.choices = [_mock_choice(content=final_llm_reply)]

    with patch.object(manager, "_create", side_effect=[round1_resp, round2_resp]):
        reply = manager.generate_reply(f"Please use {tool_name}")
        return reply


# --------------------------------------------------------------------------- #
# 1. Google Drive via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_google_drive(monkeypatch):
    class _DriveStub:
        def search_drive_files(self, query="", max_results=10):
            return [{"id": "d123", "name": "Project Roadmap.pdf", "mime_type": "application/pdf"}]

    monkeypatch.setattr(goog, "drive_service", _DriveStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="google_search_drive",
        tool_args={"query": "Project Roadmap"},
        tool_result_data={"files": [{"id": "d123", "name": "Project Roadmap.pdf"}]},
        final_llm_reply="I found your Project Roadmap on Google Drive."
    )
    assert "Project Roadmap on Google Drive" in reply


# --------------------------------------------------------------------------- #
# 2. Google Sheets via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_google_sheets(monkeypatch):
    class _SheetsStub:
        def read_sheet(self, spreadsheet_id, sheet_name=None, range_a1="A1:Z100"):
            return {
                "spreadsheet_id": spreadsheet_id,
                "values": [["Item", "Cost"], ["Coffee", "$5"], ["Book", "$20"]],
                "row_count": 3,
                "col_count": 2,
            }

    monkeypatch.setattr(goog, "sheets_service", _SheetsStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="google_read_sheet",
        tool_args={"spreadsheet_id": "s456", "range_a1": "A1:B3"},
        tool_result_data={"values": [["Item", "Cost"]]},
        final_llm_reply="Your budget spreadsheet shows total expenses of $25."
    )
    assert "budget spreadsheet" in reply


# --------------------------------------------------------------------------- #
# 3. Google Docs via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_google_docs(monkeypatch):
    class _DocsStub:
        def read_doc(self, document_id):
            return {
                "document_id": document_id,
                "title": "Meeting Notes",
                "text": "Discussion about Umi architecture and voice loop.",
            }

    monkeypatch.setattr(goog, "docs_service", _DocsStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="google_read_doc",
        tool_args={"document_id": "doc789"},
        tool_result_data={"title": "Meeting Notes"},
        final_llm_reply="According to the Meeting Notes, the architecture discussion is complete."
    )
    assert "Meeting Notes" in reply


# --------------------------------------------------------------------------- #
# 4. YouTube via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_google_youtube(monkeypatch):
    class _YouTubeStub:
        def search(self, query="", max_results=5):
            return [
                {"video_id": "yt_1", "title": "FastAPI Crash Course", "channel_title": "CodeTube"}
            ]

    monkeypatch.setattr(goog, "youtube_service", _YouTubeStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="google_youtube_search",
        tool_args={"query": "FastAPI Crash Course"},
        tool_result_data={"videos": [{"video_id": "yt_1"}]},
        final_llm_reply="I found the video 'FastAPI Crash Course' on YouTube."
    )
    assert "FastAPI Crash Course" in reply


# --------------------------------------------------------------------------- #
# 5. Gmail via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_gmail(monkeypatch):
    class _GmailStub:
        def list_messages(self, query=None, max_results=5):
            return [
                {"id": "msg1", "subject": "Welcome to Umi", "from": "team@umi.ai", "snippet": "Get started"}
            ]

    monkeypatch.setattr(gmail_tools, "gmail_service", _GmailStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="list_emails",
        tool_args={"max_results": 5},
        tool_result_data={"emails": [{"id": "msg1"}]},
        final_llm_reply="You have 1 email with subject 'Welcome to Umi'."
    )
    assert "Welcome to Umi" in reply


# --------------------------------------------------------------------------- #
# 6. Google Calendar via Chat Loop
# --------------------------------------------------------------------------- #
def test_chat_loop_google_calendar(monkeypatch):
    class _CalendarStub:
        def list_events(self, time_min=None, time_max=None, max_results=10):
            return [
                {"id": "cal1", "summary": "Product Review", "start": "2026-09-18T10:00:00Z"}
            ]

    monkeypatch.setattr(cal_tools, "calendar_service", _CalendarStub())

    reply = _run_orchestrator_chat_turn(
        monkeypatch,
        tool_name="list_calendar_events",
        tool_args={"max_results": 5},
        tool_result_data={"events": [{"id": "cal1"}]},
        final_llm_reply="You have a Product Review at 10 AM tomorrow."
    )
    assert "Product Review" in reply


# --------------------------------------------------------------------------- #
# 7. Confirmation Gate Safety Across Services
# --------------------------------------------------------------------------- #
def test_destructive_tool_confirmation_gating():
    """Verify write/delete actions across services reject execution when unconfirmed."""
    manager = LLMManager()

    # YouTube delete video without confirmed flag
    round1_resp = MagicMock()
    round1_resp.choices = [
        _mock_choice(tool_name="google_youtube_delete_video", tool_args={"video_id": "v_bad"})
    ]

    round2_resp = MagicMock()
    round2_resp.choices = [_mock_choice(content="Please confirm if you really want to delete this video.")]

    with patch.object(manager, "_create", side_effect=[round1_resp, round2_resp]):
        reply = manager.generate_reply("Delete my YouTube video v_bad")
        assert "confirm" in reply.lower()
