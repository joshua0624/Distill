import pytest
from fastapi.testclient import TestClient

from distill import db
from distill.api import app
from distill.config import settings

CH = "UC" + "a" * 22


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    with db.session() as conn:
        conn.execute("INSERT INTO channels (id, title, source, tier, reviewed) VALUES (?, 'A', 'x', 'trusted', 1)", (CH,))
        for i, vid in enumerate(["vid00000001", "vid00000002", "vid00000003"]):
            conn.execute(
                "INSERT INTO videos (id, channel_id, title, description, published_at, duration_s, source) "
                "VALUES (?, ?, ?, 'desc', ?, 600, 'rss')", (vid, CH, f"Video {i}", f"2026-11-0{i + 1}T00:00:00Z"))
            conn.execute("INSERT INTO decisions (video_id, visible, reason) VALUES (?, 1, 'trusted')", (vid,))
    return TestClient(app)


def test_feed_and_video(client):
    assert client.get("/api/feed").headers["cache-control"] == "no-store"
    feed = client.get("/api/feed").json()
    assert [v["id"] for v in feed] == ["vid00000003", "vid00000002", "vid00000001"]
    assert feed[0]["in_queue"] == 0 and feed[0]["watched_pct"] is None
    v = client.get("/api/videos/vid00000001").json()
    assert v["description"] == "desc" and v["channel_title"] == "A"
    assert client.get("/api/videos/nope0000000").status_code == 404


def test_progress_keeps_furthest_point(client):
    client.put("/api/progress/vid00000001", json={"position_s": 300, "duration_s": 600})
    client.put("/api/progress/vid00000001", json={"position_s": 60, "duration_s": 600})  # rewound
    v = client.get("/api/videos/vid00000001").json()
    assert v["position_s"] == 60 and v["watched_pct"] == 50
    assert [h["id"] for h in client.get("/api/history").json()] == ["vid00000001"]
    assert client.put("/api/progress/nope0000000", json={"position_s": 1, "duration_s": 2}).status_code == 404


def test_queue_add_remove_reorder(client):
    for vid in ["vid00000001", "vid00000002", "vid00000003"]:
        client.post(f"/api/queue/{vid}")
    client.post("/api/queue/vid00000001")  # duplicate add is a no-op
    ids = lambda: [v["id"] for v in client.get("/api/queue").json()]
    assert ids() == ["vid00000001", "vid00000002", "vid00000003"]

    client.put("/api/queue", json={"ids": ["vid00000003", "vid00000001"]})
    assert ids() == ["vid00000003", "vid00000001", "vid00000002"]

    client.delete("/api/queue/vid00000001")
    assert ids() == ["vid00000003", "vid00000002"]
    client.post("/api/queue/vid00000001")
    assert ids()[-1] == "vid00000001"
    assert client.get("/api/feed").json()[-1]["in_queue"] == 1
