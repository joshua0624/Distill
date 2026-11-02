from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from distill import db
from distill.api import app
from distill.config import settings


def ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    # (channel, days-ago of each watch, watches_180d, reviewed)
    channels = [
        ("UColdfave", [300] * 8, 0, 0),              # old favourite: rediscover, ranked first
        ("UColdish", [400] * 4 + [30], 1, 0),        # mostly old, one recent watch: still in
        ("UCrecent", [300] * 6 + [10] * 5, 5, 0),    # watched a lot recently: normal queue only
        ("UCancient", [1500] * 9, 0, 0),             # outside the 2-year window
        ("UCdone", [300] * 9, 0, 1),                 # already triaged
        ("UConce", [300] * 2, 0, 0),                 # too few watches
    ]
    with db.session() as conn:
        for cid, watches, recent, reviewed in channels:
            conn.execute("INSERT INTO channels (id, title, source, watch_count, watches_180d, reviewed) "
                         "VALUES (?, ?, 'takeout_history', ?, ?, ?)", (cid, cid, len(watches), recent, reviewed))
            conn.executemany("INSERT INTO takeout_history (video_id, title, channel_id, watched_at) VALUES (?, ?, ?, ?)",
                             [(f"{cid}-{i}", f"t{i}", cid, ago(d)) for i, d in enumerate(watches)])
    return TestClient(app)


def test_rediscover(client):
    got = client.get("/api/triage/next?mode=rediscover&months=24").json()
    assert [(c["id"], c["window_watches"]) for c in got] == [("UColdfave", 8), ("UColdish", 4)]
    assert client.get("/api/triage/stats?months=24").json()["rediscover"] == 2
    wide = client.get("/api/triage/next?mode=rediscover&months=60").json()
    assert [c["id"] for c in wide] == ["UCancient", "UColdfave", "UColdish"]


def test_top_mode_unchanged(client):
    assert client.get("/api/triage/next").json()[0]["id"] == "UCrecent"
