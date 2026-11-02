import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from distill import db
from distill.api import app
from distill.config import Settings, settings
from distill.discovery import discover
from distill.ingest import apply_rules
from distill.rules import decide_llm, load_llm_rules

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
TRUSTED, BLOCKED, NEW, LINKED, FEATURED, IDEA = (f"UC{c * 22}" for c in "tbnlfi")


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeYouTube:
    def __init__(self):
        self.searches, self.details_calls = [], []
        # video id -> (channel, days old)
        self.videos = {
            "srchTrust01": (TRUSTED, 1), "srchBlock01": (BLOCKED, 1), "srchNew0001": (NEW, 1),
            "srchOld0001": (NEW, 90), "hnOldTalk01": (NEW, 400),
            "linked00001": (LINKED, 2), "featured001": (FEATURED, 2), "idea0000001": (IDEA, 3),
        }

    def search(self, q, after):
        self.searches.append(q)
        return [{"id": v} for v in ("srchTrust01", "srchBlock01", "srchNew0001", "srchOld0001")]

    def video_details(self, ids):
        self.details_calls.append(list(ids))
        return {i: {"channel_id": self.videos[i][0], "channel_title": f"Chan {self.videos[i][0][2]}",
                    "title": f"Video {i}", "published_at": iso(self.videos[i][1])}
                for i in ids if i in self.videos}

    def channel_uploads(self, channel_id):
        return [{"id": v, "is_short": False, "published_at": iso(age)}
                for v, (ch, age) in self.videos.items() if ch == channel_id]

    def channel_by_handle(self, handle):
        handle = handle.lstrip("@")
        ids = {"linkedguy": LINKED, "realidea": IDEA}
        return {"id": ids[handle], "title": handle, "handle": f"@{handle}", "thumb_url": None} if handle in ids else None

    def featured_channels(self, channel_id):
        return [FEATURED, TRUSTED]


class FakeHTTP:
    def get(self, url, params):
        hits = [{"url": "https://youtu.be/hnOldTalk01", "title": "A great talk"},
                {"url": "https://example.com/not-a-video", "title": "x"}] if params["query"] == "youtu.be" else []
        return NS(raise_for_status=lambda: None, json=lambda: {"hits": hits})


class FakeLLM:
    def __init__(self):
        self.messages = NS(create=self._create)

    def _create(self, **params):
        ideas = {"channels": [{"handle": "@realidea", "why": "VALORANT coaching"},
                              {"handle": "@madeup", "why": "doesn't exist"}]}
        return NS(content=[NS(type="text", text=json.dumps(ideas))],
                  usage=NS(input_tokens=500, output_tokens=200, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    c = db.connect()
    for cid, tier in [(TRUSTED, "trusted"), (BLOCKED, "blocked")]:
        c.execute("INSERT INTO channels (id, title, source, tier, reviewed) VALUES (?, ?, 'x', ?, 1)",
                  (cid, f"Chan {cid[2]}", tier))
    # A video I watched past halfway, linking another channel: seeds adjacent discovery.
    c.execute("INSERT INTO videos (id, channel_id, title, description, published_at, source) VALUES "
              "('seed0000001', ?, 'Seed', 'Guest: https://youtube.com/@linkedguy and https://youtube.com/@nobody', ?, 'rss')",
              (TRUSTED, iso(5)))
    c.execute("INSERT INTO progress (video_id, position_s, watched_pct) VALUES ('seed0000001', 500, 80)")
    yield c
    c.close()


def run(conn, yt, **kw):
    return discover(conn, yt, Settings(), http=FakeHTTP(), now=NOW, **kw)


def test_discover_sources(conn):
    yt = FakeYouTube()
    r = run(conn, yt, llm=FakeLLM())
    videos = {row["id"]: dict(row) for row in conn.execute("SELECT id, channel_id, source, discovered_via FROM videos")}
    assert "srchBlock01" not in videos and "srchOld0001" not in videos  # blocked channel, too old
    assert videos["srchNew0001"]["source"] == "search" and videos["srchTrust01"]["channel_id"] == TRUSTED
    assert videos["hnOldTalk01"]["discovered_via"] == "Hacker News: A great talk"  # HN keeps older videos
    assert videos["linked00001"]["discovered_via"] == "linked from Chan t"
    assert videos["featured001"]["source"] == "adjacent"
    assert videos["idea0000001"]["discovered_via"] == "suggested: VALORANT coaching"
    assert (r.seeds, r.llm_channels, r.errors) == (1, 1, 0)
    new = conn.execute("SELECT tier, reviewed, source FROM channels WHERE id = ?", (NEW,)).fetchone()
    assert tuple(new) == ("candidate", 0, "discovery")
    assert conn.execute("SELECT requests FROM llm_usage").fetchone()[0] == 1

    # Every source is on a schedule: running again right away does nothing.
    r = run(conn, yt, llm=FakeLLM())
    assert len(yt.searches) == 10 and r.new_videos == 0 and r.seeds == 0


def test_search_rotation(conn):
    yt = FakeYouTube()
    discover(conn, yt, Settings(discovery_searches_per_run=4), http=FakeHTTP(), now=NOW)
    discover(conn, yt, Settings(discovery_searches_per_run=4), http=FakeHTTP(), now=NOW + timedelta(hours=9))
    assert len(set(yt.searches)) == 8  # the second run picks the ones that haven't run yet


@pytest.mark.parametrize("tier, interest, substance, visible", [
    ("candidate", "strong", "medium", True),
    ("candidate", "some", "high", False),
    ("candidate", "strong", "low", False),
    ("mixed", "some", "low", True),
])
def test_discovery_rules(tier, interest, substance, visible):
    cls = {"tier": tier, "format": "analysis", "slop_signals": [], "clickbait": False, "english": True,
           "interest_match": interest, "substance": substance}
    assert decide_llm(cls, load_llm_rules()).visible == visible
    # Only discovered channels are held to English.
    assert decide_llm({**cls, "english": False}, load_llm_rules()).visible == (visible and tier != "candidate")


def test_discovery_row_rating_and_suggestions(conn):
    run(conn, FakeYouTube())
    conn.execute("UPDATE videos SET details_at = datetime('now'), duration_s = 900, is_short = 0, "
                 "fetched_at = datetime('now'), views = 5000")
    conn.execute("UPDATE videos SET views = 40 WHERE id = 'featured001'")
    for vid, interest in [("srchNew0001", "strong"), ("linked00001", "some")]:
        conn.execute("INSERT INTO classifications (video_id, category, format, clickbait, substance, slop_signals_json, "
                     "interest_match, model, prompt_version) VALUES (?, 'gaming', 'analysis', 0, 'high', '[]', ?, 'm', 'v')",
                     (vid, interest))
    apply_rules(conn)
    conn.commit()
    assert conn.execute("SELECT reason FROM decisions WHERE video_id = 'featured001'").fetchone()[0] == "too_few_views"
    client = TestClient(app)
    disc = client.get("/api/discovery").json()
    assert [v["id"] for v in disc] == ["srchNew0001"] and disc[0]["discovered_via"] == "Houston Rockets"
    assert "srchNew0001" not in [v["id"] for v in client.get("/api/feed").json()]

    # Three 👍 on a discovered channel's videos -> suggest promoting it.
    for vid in ["srchNew0001", "srchNew0001", "hnOldTalk01"]:
        client.post(f"/api/videos/{vid}/rating", json={"rating": "up"})
    assert client.get("/api/suggestions").json() == []  # same video twice counts once
    conn.execute("INSERT INTO videos (id, channel_id, title, published_at, source) VALUES ('extra000001', ?, 'x', ?, 'search')", (NEW, iso(1)))
    conn.commit()
    client.post("/api/videos/extra000001/rating", json={"rating": "up"})
    sug = client.get("/api/suggestions").json()
    assert [(s["id"], s["kind"], s["ups"]) for s in sug] == [(NEW, "promote", 3)]
    assert client.get("/api/videos/srchNew0001").json()["rating"] == "up"
    client.post("/api/videos/srchNew0001/rating", json={"rating": None})
    assert client.get("/api/videos/srchNew0001").json()["rating"] is None

    client.post(f"/api/suggestions/{NEW}/dismiss", json={"kind": "promote"})
    assert client.get("/api/suggestions").json() == []
    # Promoting the channel moves its videos from the Discovery row into the feed.
    client.post(f"/api/channels/{NEW}/tier", json={"tier": "trusted"})
    assert "srchNew0001" in [v["id"] for v in client.get("/api/feed").json()]
    assert client.get("/api/discovery").json() == []
