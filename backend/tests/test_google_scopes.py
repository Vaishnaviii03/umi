"""Phase 7.5 — Google OAuth scope configuration tests.

The single ``GOOGLE_SCOPES`` list drives the authorization URL and the
granted-vs-required comparison in /google/status. It must contain exactly the
six service scope families (gmail, calendar, drive, sheets, docs, youtube) and
never regress to a narrower set.
"""

from app.services.gmail.api import GOOGLE_SCOPES


def test_google_scopes_covers_all_six_services():
    expected = {
        # Existing (Phase 5/6) — preserved.
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
        # Phase 7.5 — Drive + Sheets + Docs + YouTube.
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/youtube",
    }
    assert set(GOOGLE_SCOPES) == expected


def test_google_scopes_no_duplicates():
    assert len(GOOGLE_SCOPES) == len(set(GOOGLE_SCOPES))


def test_google_scopes_are_exact_google_urls():
    for scope in GOOGLE_SCOPES:
        assert scope.startswith("https://www.googleapis.com/auth/")