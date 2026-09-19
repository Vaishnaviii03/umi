"""Phase 7.5 — YouTube service tests (no real Google calls)."""

import pytest

from app.services.gmail.token_store import TokenStore
from app.services.google_http import GoogleNotFound, GoogleServiceError
from app.services.youtube import YoutubeService
from app.services.youtube.service import normalize_search_item, normalize_video


class _FakeYoutubeAPI:
    def __init__(self, items=None, videos=None, uploads_id="UPLOADS1"):
        self.items = items or [{"id": {"videoId": "v1"}, "snippet": {"title": "Big Ideas"}}]
        self.videos = videos or [{
            "id": "v1",
            "snippet": {"title": "Big Ideas", "description": "desc", "channelTitle": "Me"},
            "contentDetails": {"duration": "PT2M"},
            "statistics": {"viewCount": "10", "likeCount": "2"},
        }]
        self.uploads_id = uploads_id
        self.ops = []

    def search(self, *, query, max_results=10):
        self.ops.append(("search", query, max_results))
        return self.items

    def list_videos(self, video_ids, include_statistics=True):
        self.ops.append(("list_videos", video_ids))
        return [v for v in self.videos if v["id"] in video_ids]

    def channel_mine_id(self):
        self.ops.append(("channel_mine",))
        return self.uploads_id

    def list_playlist_items(self, playlist_id, max_results=25):
        self.ops.append(("playlist", playlist_id, max_results))
        return [
            {"snippet": {"title": f"Upload {i}", "channelTitle": "Me"}, "contentDetails": {"videoId": f"up{i}"}}
            for i in range(max_results)
        ]

    def update_video(self, video_id, snippet):
        self.ops.append(("update", video_id, snippet))
        return {"id": video_id, "snippet": snippet, "contentDetails": {}, "statistics": {}}

    def delete_video(self, video_id):
        self.ops.append(("delete", video_id))
        return None

    def upload_video(self, file_path, *, title, description, privacy):
        self.ops.append(("upload", file_path, title))
        return {"id": "new-vid"}


def _service(fake=None, tmp_path=""):
    return YoutubeService(store=TokenStore(str(tmp_path / "yt.json")), api=fake or _FakeYoutubeAPI())


def test_normalize_search_item():
    out = normalize_search_item({"id": {"videoId": "v1"}, "snippet": {"title": "T", "channelTitle": "C"}})
    assert out["url"] == "https://www.youtube.com/watch?v=v1"


def test_normalize_video():
    out = normalize_video({"id": "v1", "snippet": {"title": "T"}, "contentDetails": {"duration": "PT1M"}, "statistics": {"viewCount": "5"}})
    assert out["duration"] == "PT1M"
    assert out["view_count"] == "5"


def test_search_youtube(tmp_path):
    fake = _FakeYoutubeAPI()
    svc = _service(fake, tmp_path)
    out = svc.search_youtube("founder os", max_results=3)
    assert out[0]["id"] == "v1"
    assert fake.ops[0] == ("search", "founder os", 3)


def test_search_youtube_requires_term(tmp_path):
    svc = _service(_FakeYoutubeAPI(), tmp_path)
    with pytest.raises(GoogleServiceError):
        svc.search_youtube("   ")


def test_get_video(tmp_path):
    svc = _service(_FakeYoutubeAPI(), tmp_path)
    out = svc.get_video("v1")
    assert out["title"] == "Big Ideas"
    with pytest.raises(GoogleNotFound):
        svc.get_video("missing")


def test_list_uploads(tmp_path):
    fake = _FakeYoutubeAPI(uploads_id="UPLOADS1")
    svc = _service(fake, tmp_path)
    out = svc.list_uploads(max_results=2)
    assert len(out) == 2
    assert out[0]["id"] == "up0"


def test_list_uploads_no_channel(tmp_path):
    fake = _FakeYoutubeAPI(uploads_id=None)
    svc = _service(fake, tmp_path)
    assert svc.list_uploads() == []


def test_update_video(tmp_path):
    fake = _FakeYoutubeAPI()
    svc = _service(fake, tmp_path)
    out = svc.update_video("v1", title="Better Title")
    assert out["id"] == "v1"
    assert fake.ops[-1][2]["title"] == "Better Title"


def test_update_video_nothing_to_change(tmp_path):
    svc = _service(_FakeYoutubeAPI(), tmp_path)
    with pytest.raises(GoogleServiceError):
        svc.update_video("v1")


def test_update_video_missing(tmp_path):
    svc = _service(_FakeYoutubeAPI(videos=[]), tmp_path)
    with pytest.raises(GoogleNotFound):
        svc.update_video("missing", title="X")


def test_delete_video(tmp_path):
    fake = _FakeYoutubeAPI()
    svc = _service(fake, tmp_path)
    assert svc.delete_video("v1")["deleted"] is True
    assert fake.ops[-1] == ("delete", "v1")


def test_upload_video_requires_file(tmp_path, tmp_path_factory):
    svc = _service(_FakeYoutubeAPI(), tmp_path)
    with pytest.raises(GoogleServiceError):
        svc.upload_video("/nope/never.mp4", title="T")


def test_upload_video_empty_file(tmp_path, tmp_path_factory):
    empty = tmp_path_factory.mktemp("yt") / "empty.mp4"
    empty.write_bytes(b"")
    svc = _service(_FakeYoutubeAPI(), tmp_path)
    with pytest.raises(GoogleServiceError):
        svc.upload_video(str(empty), title="T")


def test_upload_video_ok_and_private_default(tmp_path, tmp_path_factory):
    fake = _FakeYoutubeAPI()
    video = tmp_path_factory.mktemp("yt") / "clip.mp4"
    video.write_bytes(b"MP4DATA" * 100)
    svc = _service(fake, tmp_path)
    out = svc.upload_video(str(video), title="My Clip")
    assert out["id"] == "new-vid"
    assert out["privacy"] == "private"
    assert fake.ops[-1] == ("upload", str(video), "My Clip")


def test_privacy_sanitized(tmp_path):
    from app.services.youtube.service import _safe_privacy

    assert _safe_privacy("PUBLIC") == "public"
    assert _safe_privacy("weird") == "private"


def test_status(tmp_path):
    store = TokenStore(str(tmp_path / "yt.json"))
    store.save({"token": "x"})
    assert YoutubeService(store=store, api=_FakeYoutubeAPI()).status()["connected"] is True
    assert YoutubeService(store=TokenStore(str(tmp_path / "o.json"))).status()["connected"] is False