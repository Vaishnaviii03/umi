"""Phase 7.5 — Google YouTube API boundary.

Thin wrapper around the YouTube Data API v3 client. Uploads use a plain
``MediaFileUpload`` (non-resumable, big single chunk) — good enough for Umi's
use, and the service layer checks the file exists before building it.
"""

from __future__ import annotations

import logging

from app.services.google_http import GoogleNotConnected, map_http_error

logger = logging.getLogger("umi.youtube")


class YoutubeAPI:
    def __init__(self, *, credentials=None, service=None) -> None:
        self._creds = credentials
        self._service = service

    def _svc(self):
        if self._service is not None:
            return self._service
        if self._creds is None:
            raise GoogleNotConnected("no Google account connected yet")
        from googleapiclient.discovery import build

        return build("youtube", "v3", credentials=self._creds, cache_discovery=False)

    def search(self, *, query: str, max_results: int = 10) -> list[dict]:
        response = (
            self._svc()
            .search()
            .list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                safeSearch="none",
            )
            .execute()
        )
        return response.get("items", [])

    def list_videos(self, video_ids: list[str], *, include_statistics: bool = True) -> list[dict]:
        parts = "snippet,contentDetails" + (",statistics" if include_statistics else "")
        response = self._svc().videos().list(part=parts, id=",".join(video_ids)).execute()
        return response.get("items", [])

    def channel_mine_id(self) -> str | None:
        response = self._svc().channels().list(part="contentDetails", mine=True).execute()
        items = response.get("items") or []
        if not items:
            return None
        return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

    def list_playlist_items(self, playlist_id: str, max_results: int = 25) -> list[dict]:
        response = (
            self._svc()
            .playlistItems()
            .list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=max_results)
            .execute()
        )
        return response.get("items", [])

    def update_video(self, video_id: str, snippet: dict) -> dict:
        body = {"id": video_id, "snippet": snippet}
        response = self._svc().videos().update(part="snippet", body=body).execute()
        return response

    def delete_video(self, video_id: str) -> None:
        self._svc().videos().delete(id=video_id).execute()

    def upload_video(self, file_path: str, *, title: str, description: str, privacy: str) -> dict:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(file_path, chunksize=-1, resumable=False)
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy},
        }
        response = self._svc().videos().insert(part="snippet,status", body=body, media_body=media).execute()
        return response


__all__ = ["YoutubeAPI", "map_http_error"]