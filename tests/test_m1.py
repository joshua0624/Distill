import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from distill import db
from distill.config import Settings
from distill.ingest import ingest
from distill.rules import decide
from distill.takeout import import_takeout
from distill.youtube import parse_duration, parse_rss

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
A = "UC" + "a" * 22
B = "UC" + "b" * 22
C = "UC" + "c" * 22


def watch(vid, channel, when, title="Some video", **extra):
    return {
        "header": "YouTube",
        "title": f"Watched {title}",
        "titleUrl": f"https://www.youtube.com/watch?v={vid}",
        "subtitles": [{"name": f"Chan {channel[-1]}", "url": f"https://www.youtube.com/channel/{channel}"}],
        "time": when,
        **extra,
    }


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture
def takeout(tmp_path):
    root = tmp_path / "Takeout" / "YouTube and YouTube Music"
    (root / "history").mkdir(parents=True)
    (root / "subscriptions").mkdir()
    recent, old = "2026-10-20T10:00:00.000Z", "2024-01-01T10:00:00.000Z"
    entries = [
        watch("aaaaaaaaaa1", A, recent, "Rockets vs Lakers"),
        watch("aaaaaaaaaa2", A, recent),
        watch("aaaaaaaaaa1", A, "2026-10-21T10:00:00.000Z", "Rockets vs Lakers"),  # rewatch
        *[watch(f"bbbbbbbbb{i:02d}", B, old) for i in range(5)],
        watch("ccccccccccc", C, recent, details=[{"name": "From Google Ads"}]),
        {"header": "YouTube", "title": "Watched a video that has been removed", "time": recent},
        {**watch("mmmmmmmmmmm", C, recent), "header": "YouTube Music"},
    ]
    (root / "history" / "watch-history.json").write_text(json.dumps(entries))
    (root / "subscriptions" / "subscriptions.csv").write_text(
        f"Channel Id,Channel Url,Channel Title\n{C},https://www.youtube.com/channel/{C},Chan C\n"
    )
    return tmp_path / "Takeout"


def test_import_takeout(conn, takeout):
    r = import_takeout(conn, takeout, now=NOW)
    assert (r.watches, r.skipped, r.subscriptions, r.channels) == (8, 3, 1, 3)
    rows = {row["id"]: row for row in conn.execute("SELECT * FROM channels")}
    assert rows[A]["watch_count"] == 3 and rows[A]["watches_180d"] == 3
    assert rows[B]["watch_count"] == 5 and rows[B]["watches_180d"] == 0
    assert rows[C]["is_subscribed"] == 1 and rows[C]["watch_count"] == 0
    assert all(row["tier"] == "candidate" and not row["reviewed"] for row in rows.values())

    # Re-import doesn't double count.
    import_takeout(conn, takeout, now=NOW)
    assert conn.execute("SELECT watch_count FROM channels WHERE id = ?", (A,)).fetchone()[0] == 3


def html_cell(body, caption="<b>Products:</b><br>&emsp;YouTube<br>"):
    return (
        '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid">'
        '<div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">YouTube<br></p></div>'
        f'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">{body}</div>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div>'
        f'<div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">{caption}</div></div></div>'
    )


def test_import_takeout_html_export(tmp_path):
    cells = [
        html_cell(f'Watched\xa0<a href="https://www.youtube.com/watch?v=aaaaaaaaaa1">Rockets &amp; Lakers</a><br>'
                  f'<a href="https://www.youtube.com/channel/{A}">Chan A</a><br>Oct 20, 2026, 1:48:14 PM EST<br>'),
        html_cell(f'Watched\xa0<a href="https://www.youtube.com/watch?v=ccccccccccc">Ad</a><br>'
                  f'<a href="https://www.youtube.com/channel/{C}">Chan C</a><br>Oct 20, 2026, 1:00:00 PM EST<br>',
                  caption="<b>Details:</b><br>&emsp;From Google Ads<br>"),
        html_cell('Watched\xa0<a href="https://www.youtube.com/watch?v=rrrrrrrrrrr">https://www.youtube.com/watch?v=rrrrrrrrrrr</a>'
                  '<br>Jan 1, 2020, 9:00:00 AM EST<br>'),  # removed video: no channel link
    ]
    (tmp_path / "watch-history.html").write_text("<html><body>" + "".join(cells) + "</body></html>")
    conn = db.connect(tmp_path / "t.db")
    r = import_takeout(conn, tmp_path, now=NOW)
    assert (r.watches, r.skipped, r.channels) == (1, 2, 1)
    row = conn.execute("SELECT * FROM takeout_history").fetchone()
    assert row["title"] == "Rockets & Lakers" and row["watched_at"] == "2026-10-20T13:48:14.000Z"
    assert conn.execute("SELECT watches_180d FROM channels").fetchone()[0] == 1


def test_import_takeout_requires_history_or_subscriptions(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_takeout(db.connect(tmp_path / "t.db"), tmp_path)


def test_parse_duration():
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("PT45S") == 45
    assert parse_duration("P1DT1M") == 86460
    assert parse_duration("P0D") == 0


def test_parse_rss_flags_shorts():
    entries = parse_rss((FIXTURES / "feed.xml").read_text())
    assert len(entries) == 15
    shorts = {e["id"] for e in entries if e["is_short"]}
    assert "cv8tEbKtEvk" in shorts and "rsOiZE19RVo" not in shorts
    assert all(e["channel_id"] and e["published_at"] and e["title"] for e in entries)


S = Settings(min_duration_s=240, blocked_title_keywords=["reacts"])


@pytest.mark.parametrize("video,tier,rules,expected", [
    ({"title": "x", "duration_s": 600}, "trusted", [], (True, "trusted")),
    ({"title": "x", "duration_s": 600}, "mixed", [], (False, "pending_llm")),
    ({"title": "x", "duration_s": 600, "is_short": 1}, "trusted", [], (False, "short")),
    ({"title": "x", "duration_s": 100}, "trusted", [], (False, "too_short")),
    ({"title": "x", "duration_s": 0, "live_status": "upcoming"}, "trusted", [], (False, "upcoming")),
    ({"title": "Streamer REACTS to", "duration_s": 600}, "trusted", [], (False, "blocked_keyword")),
    ({"title": "Rockets vs Lakers Full Game Highlights", "duration_s": 200}, "trusted",
     [{"title_pattern": r"rockets.*full game highlights", "min_duration_s": 120}], (True, "sport_rule")),
    ({"title": "Celtics vs Knicks Full Game Highlights", "duration_s": 600}, "trusted",
     [{"title_pattern": r"rockets.*full game highlights", "min_duration_s": 120}], (False, "sport_rule_miss")),
])
def test_decide(video, tier, rules, expected):
    d = decide(video, tier, rules, S)
    assert (d.visible, d.reason) == expected


class FakeYouTube:
    def __init__(self, uploads, details, shorts=()):
        self.uploads, self.details, self.shorts = uploads, details, set(shorts)
        self.short_checks = []

    def channel_uploads(self, channel_id):
        return self.uploads.get(channel_id, [])

    def video_details(self, ids):
        return {i: self.details[i] for i in ids if i in self.details}

    def is_short(self, vid):
        self.short_checks.append(vid)
        return vid in self.shorts


def upload(vid, channel, days_ago=1, is_short=False):
    return {"id": vid, "channel_id": channel, "title": f"title {vid}", "description": "",
            "published_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
            "thumb_url": None, "is_short": is_short}


def detail(duration, live="none"):
    return {"duration_s": duration, "live_status": live, "description": "d", "tags": [],
            "views": 10, "likes": 1, "thumb_url": None}


def test_ingest(conn):
    conn.executemany("INSERT INTO channels (id, title, source, tier, reviewed) VALUES (?, ?, 'x', ?, 1)",
                     [(A, "A", "trusted"), (B, "B", "mixed"), (C, "C", "candidate")])
    yt = FakeYouTube(
        uploads={
            A: [upload("long0000001", A), upload("rssshort001", A, is_short=True),
                upload("hidshort001", A), upload("old00000001", A, days_ago=60)],
            B: [upload("mixed000001", B)],
            C: [upload("cand0000001", C)],
        },
        details={"long0000001": detail(900), "rssshort001": detail(30),
                 "hidshort001": detail(50), "mixed000001": detail(900)},
        shorts={"hidshort001"},
    )
    r = ingest(conn, yt, S)
    assert (r.channels, r.new_videos, r.visible) == (2, 4, 1)
    assert yt.short_checks == ["hidshort001"]  # RSS-flagged Short needs no request
    reasons = dict(conn.execute("SELECT video_id, reason FROM decisions"))
    assert reasons == {"long0000001": "trusted", "rssshort001": "short",
                       "hidshort001": "short", "mixed000001": "pending_llm"}

    # Tier changes are picked up on the next run; overrides are left alone.
    conn.execute("UPDATE channels SET tier = 'trusted' WHERE id = ?", (B,))
    conn.execute("UPDATE decisions SET visible = 0, reason = 'manual', overridden = 1 "
                 "WHERE video_id = 'long0000001'")
    r = ingest(conn, yt, S)
    assert r.new_videos == 0
    reasons = dict(conn.execute("SELECT video_id, reason FROM decisions"))
    assert reasons["mixed000001"] == "trusted" and reasons["long0000001"] == "manual"


def test_uploads_fall_back_to_api_when_rss_fails():
    import httpx
    from distill.youtube import YouTube
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if "feeds/videos.xml" in str(request.url):
            return httpx.Response(404)
        assert request.url.params["playlistId"] == "UU" + "a" * 22
        return httpx.Response(200, json={"items": [{
            "snippet": {"title": "From the API", "description": "d", "thumbnails": {}},
            "contentDetails": {"videoId": "apivideo001", "videoPublishedAt": "2026-11-01T00:00:00Z"}}]})

    yt = YouTube(client=httpx.Client(transport=httpx.MockTransport(handler)), api_key="k")
    for _ in range(4):
        uploads = yt.channel_uploads("UC" + "a" * 22)
    assert uploads[0]["id"] == "apivideo001" and uploads[0]["is_short"] is None
    # Three RSS 404s in a row, then straight to the API for the rest of the run.
    assert seen.count("/feeds/videos.xml") == 3 and seen.count("/youtube/v3/playlistItems") == 4
