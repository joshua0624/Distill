import pytest
from fastapi.testclient import TestClient

from distill import api, db
from distill.config import settings
from distill.youtube import YouTube

CH = "UC" + "x" * 22


class StubYouTube(YouTube):
    """Real resolve_channel parsing; every API call answers with the same channel."""
    def __init__(self):
        super().__init__(api_key="test")
        self.calls = []

    def _api(self, endpoint, **params):
        self.calls.append(endpoint)
        if endpoint == "search":
            return {"items": [{"id": {"channelId": CH}}]}
        return {"items": [{"id": CH}]}

    def channel_by_handle(self, handle):
        self.calls.append(f"handle:{handle}")
        return {"id": CH, "title": "Handle Chan", "handle": f"@{handle}", "thumb_url": None}

    def channel_info(self, ids):
        self.calls.append("channel_info")
        return {CH: {"title": "Chan", "handle": "@chan", "thumb_url": None}}

    def video_details(self, ids):
        self.calls.append("video_details")
        return {i: {"channel_id": CH} for i in ids}


@pytest.mark.parametrize("text, first_call", [
    (f"https://www.youtube.com/channel/{CH}", "channel_info"),
    (CH, "channel_info"),
    ("https://www.youtube.com/@CoachJoe/videos", "handle:CoachJoe"),
    ("@CoachJoe", "handle:CoachJoe"),
    ("https://youtu.be/dQw4w9WgXcQ?t=10", "video_details"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x", "video_details"),
    ("https://www.youtube.com/user/oldname", "channels"),
])
def test_resolve_channel(text, first_call):
    yt = StubYouTube()
    assert yt.resolve_channel(text)["id"] == CH
    assert yt.calls[0] == first_call


class FakeFeedYouTube(StubYouTube):
    def channel_uploads(self, channel_id):
        return [{"id": "newvid00001", "title": "Fresh", "description": "", "is_short": False,
                 "published_at": "2099-01-01T00:00:00+00:00", "thumb_url": None}]

    def video_details(self, ids):
        return {i: {"channel_id": CH, "duration_s": 900, "live_status": "none", "description": "",
                    "tags": [], "views": 10, "likes": 1, "thumb_url": None} for i in ids}

    def is_short(self, vid):
        return False


def test_add_channel_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    monkeypatch.setattr(api, "yt", FakeFeedYouTube())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with db.session() as conn:  # already known from Takeout, but never triaged
        conn.execute("INSERT INTO channels (id, title, source) VALUES (?, 'Old', 'takeout_history')", (CH,))
    client = TestClient(api.app)
    r = client.post("/api/channels/add", json={"query": "@chan", "tier": "trusted"}).json()
    assert (r["id"], r["tier"], r["visible"], r["pending"], r["previous_tier"]) == (CH, "trusted", 1, 0, None)
    assert [v["id"] for v in client.get("/api/feed").json()] == ["newvid00001"]
    assert [c["id"] for c in client.get("/api/channels?tier=trusted").json()] == [CH]

    r = client.post("/api/channels/add", json={"query": CH, "tier": "mixed"}).json()
    assert (r["previous_tier"], r["visible"], r["pending"]) == ("trusted", 0, 1)
    assert client.get("/api/feed").json() == []  # mixed: waits for the classifier


def test_names_return_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))

    class Search(StubYouTube):
        def _api(self, endpoint, **params):
            assert endpoint == "search" and params["type"] == "channel"
            return {"items": [{"id": {"channelId": CH}, "snippet": {"title": "Coach Joe", "description": "VALORANT"}}]}
    monkeypatch.setattr(api, "yt", Search())
    r = TestClient(api.app).post("/api/channels/add", json={"query": "Coach Joe", "tier": "trusted"}).json()
    assert r == {"choices": [{"id": CH, "title": "Coach Joe", "description": "VALORANT", "thumb_url": None}]}
    with db.session() as conn:  # nothing added until a choice is picked
        assert conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 0


def test_add_channel_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))

    class Nothing(StubYouTube):
        def channel_by_handle(self, handle):
            return None
    monkeypatch.setattr(api, "yt", Nothing())
    r = TestClient(api.app).post("/api/channels/add", json={"query": "@ghost", "tier": "trusted"})
    assert r.status_code == 404 and r.json()["detail"] == "No channel found"
