"""Phase 7.5 — Google API error mapping.

A single mapper turns ``googleapiclient.errors.HttpError`` into a family of
safe, user-facing exceptions shared by the Drive/Sheets/Docs/YouTube services.
Messages never leak status codes, response bodies, or token material — callers
only ever see the human wording produced here.

The ``api`` argument is a display name like ``"Google Drive"`` so each service
gets scoped wording ("enable the Google Drive API in Cloud Console") without
duplicating the mapping logic.
"""

from __future__ import annotations

import json

from googleapiclient.errors import HttpError

_GOOGLE_NATIVE = "application/vnd.google-apps."


class GoogleServiceError(Exception):
    """Base class — message is always safe to show the user."""


class GoogleNotConnected(GoogleServiceError):
    """Token present but Google denied access / nothing stored."""


class GoogleApiDisabled(GoogleServiceError):
    """The API is not enabled for the OAuth client's GCP project."""


class GooglePermissionDenied(GoogleServiceError):
    """403 from Google that is not about scope coverage (e.g. sharing rules)."""


class GoogleNotFound(GoogleServiceError):
    """404 — the requested resource doesn't exist / can't be seen."""


class GoogleRateLimited(GoogleServiceError):
    """429 — quota / rate limit."""


class GoogleBadRequest(GoogleServiceError):
    """400 — the request itself was rejected."""


def _error_reason(exc: HttpError) -> tuple[str, str]:
    reason = ""
    message = ""
    try:
        info = json.loads(exc.content.decode("utf-8", errors="replace"))
    except (ValueError, AttributeError):
        info = None
    if isinstance(info, dict) and isinstance(info.get("error"), dict):
        err = info["error"]
        message = err.get("message") or ""
        reason = err.get("reason") or ""
        for item in err.get("errors") or []:
            if isinstance(item, dict):
                reason = item.get("reason") or reason
                message = item.get("message") or message
        for item in err.get("details") or []:
            if isinstance(item, dict):
                reason = item.get("reason") or reason
                message = item.get("message") or message
    if not message:
        details = getattr(exc, "error_details", None)
        if isinstance(details, str):
            message = details
        elif isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    reason = item.get("reason") or reason
                    message = item.get("message") or message
    return (reason or "").lower(), message or ""


def map_http_error(exc: HttpError, api: str) -> None:
    """Raise the right per-status GoogleServiceError for ``exc`` (never returns)."""
    status = getattr(exc, "status_code", None) or 0
    reason, message = _error_reason(exc)

    if status in (401, 403):
        if (
            reason in ("accessnotconfigured", "access not configured", "notEnabled")
            or "has not been used" in message.lower()
            or "has not been enabled" in message.lower()
        ):
            raise GoogleApiDisabled(
                f"{api} is not enabled for the Google project — enable the {api} API "
                "in Cloud Console (APIs & Services → Library), then reconnect."
            )
        if status == 403:
            raise GooglePermissionDenied(
                f"Google denied {api} access — the file may be restricted or the "
                "permission changed. You can reconnect in the Gmail panel."
            )
        raise GoogleNotConnected(
            f"Google denied {api} access — reconnect your Google account in the Gmail panel."
        )
    if status == 404:
        raise GoogleNotFound(f"{api} couldn't find that item — check the id or name.")
    if status == 429:
        raise GoogleRateLimited(f"{api} is rate-limited right now — try again in a few seconds.")
    if status == 400:
        raise GoogleBadRequest(f"{api} rejected the request — check the details and try again.")
    raise GoogleServiceError(f"{api} is unavailable right now.")


def is_google_native(mime_type: str) -> bool:
    """True for Sheets('spreadsheet')/Docs('document')/etc. Google workspace types."""
    return mime_type.startswith(_GOOGLE_NATIVE)


__all__ = [
    "GoogleApiDisabled",
    "GoogleBadRequest",
    "GoogleNotConnected",
    "GoogleNotFound",
    "GooglePermissionDenied",
    "GoogleRateLimited",
    "GoogleServiceError",
    "is_google_native",
    "map_http_error",
]