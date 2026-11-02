"""Import a Google Takeout export: watch history (JSON) and subscriptions (CSV).

Builds the candidate channel list so I triage a ranked list instead of
assembling subscriptions from memory.
"""
import csv
import html
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

VIDEO_ID_RE = re.compile(r"[?&]v=([\w-]{11})")
CHANNEL_ID_RE = re.compile(r"/channel/(UC[\w-]{22})")


@dataclass
class Watch:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    watched_at: str


@dataclass
class ImportResult:
    watches: int
    skipped: int
    channels: int
    subscriptions: int


HTML_ENTRY_RE = re.compile(
    r'mdl-typography--title">(?P<header>[^<]*)<br>.*?'
    r'mdl-typography--body-1">(?P<body>.*?)</div>.*?'
    r'mdl-typography--caption">(?P<caption>.*?)</div>',
    re.S,
)
HTML_LINK_RE = re.compile(r'<a href="([^"]*)">(.*?)</a>', re.S)
HTML_DATE_RE = re.compile(r"<br>([A-Z][a-z]{2} \d{1,2}, \d{4}, [\d:]+\s?[AP]M)")


def _html_entries(text: str) -> list[dict]:
    """Turn the HTML export into the same entry shape as the JSON export."""
    entries = []
    for cell in text.split('<div class="outer-cell')[1:]:
        m = HTML_ENTRY_RE.search(cell)
        if not m:
            continue
        body = m["body"].replace(" ", " ").replace("\xa0", " ")
        links = HTML_LINK_RE.findall(body)
        date = HTML_DATE_RE.search(body)
        if not date:
            continue
        # Takeout writes local time with a zone abbreviation; hour precision doesn't matter here.
        when = datetime.strptime(date.group(1), "%b %d, %Y, %I:%M:%S %p")
        entry = {
            "header": html.unescape(m["header"]).strip(),
            "title": "Watched " + html.unescape(links[0][1]) if links else "",
            "titleUrl": links[0][0] if links else "",
            "time": when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        if len(links) > 1:
            entry["subtitles"] = [{"name": html.unescape(links[1][1]), "url": links[1][0]}]
        if "From Google Ads" in m["caption"]:
            entry["details"] = [{"name": "From Google Ads"}]
        entries.append(entry)
    return entries


def parse_watch_history(path: Path) -> tuple[list[Watch], int]:
    """Return (watches, skipped). Skips ads, YouTube Music, and removed videos."""
    text = path.read_text(encoding="utf-8")
    entries = _html_entries(text) if path.suffix == ".html" else json.loads(text)
    watches, skipped = [], 0
    for e in entries:
        if e.get("header") == "YouTube Music" or any(
            d.get("name") == "From Google Ads" for d in e.get("details", [])
        ):
            skipped += 1
            continue
        vid = VIDEO_ID_RE.search(e.get("titleUrl", ""))
        subs = e.get("subtitles") or []
        chan = CHANNEL_ID_RE.search(subs[0].get("url", "")) if subs else None
        if not vid or not chan:
            skipped += 1
            continue
        title = e.get("title", "")
        watches.append(Watch(
            video_id=vid.group(1),
            title=title.removeprefix("Watched "),
            channel_id=chan.group(1),
            channel_title=subs[0].get("name", ""),
            watched_at=e["time"],
        ))
    return watches, skipped


def parse_subscriptions(path: Path) -> list[tuple[str, str]]:
    """Return [(channel_id, title)]."""
    with path.open(newline="", encoding="utf-8") as f:
        return [
            (row["Channel Id"], row["Channel Title"])
            for row in csv.DictReader(f)
            if row.get("Channel Id", "").startswith("UC")
        ]


def find_file(root: Path, name: str) -> Path | None:
    if root.is_file():
        return root if root.name == name else None
    return next(iter(sorted(root.rglob(name))), None)


def import_takeout(conn: sqlite3.Connection, root: Path, now: datetime | None = None) -> ImportResult:
    """Import from a Takeout folder (or the files directly). Safe to re-run."""
    now = now or datetime.now(timezone.utc)
    history = find_file(root, "watch-history.json") or find_file(root, "watch-history.html")
    subs_csv = find_file(root, "subscriptions.csv")
    if not history and not subs_csv:
        raise FileNotFoundError(f"No watch-history.json/.html or subscriptions.csv under {root}.")

    watches, skipped = parse_watch_history(history) if history else ([], 0)
    subs = parse_subscriptions(subs_csv) if subs_csv else []

    for w in watches:
        conn.execute(
            "INSERT OR IGNORE INTO channels (id, title, source) VALUES (?, ?, 'takeout_history')",
            (w.channel_id, w.channel_title),
        )
        conn.execute(
            "INSERT OR IGNORE INTO takeout_history (video_id, title, channel_id, watched_at) "
            "VALUES (?, ?, ?, ?)",
            (w.video_id, w.title, w.channel_id, w.watched_at),
        )
    for channel_id, title in subs:
        conn.execute(
            "INSERT INTO channels (id, title, source, is_subscribed) "
            "VALUES (?, ?, 'takeout_subscription', 1) "
            "ON CONFLICT(id) DO UPDATE SET is_subscribed = 1",
            (channel_id, title),
        )

    cutoff = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        """
        UPDATE channels SET
            watch_count = (SELECT COUNT(*) FROM takeout_history h WHERE h.channel_id = channels.id),
            watches_180d = (SELECT COUNT(*) FROM takeout_history h
                            WHERE h.channel_id = channels.id AND h.watched_at >= ?),
            last_watched_at = (SELECT MAX(watched_at) FROM takeout_history h
                               WHERE h.channel_id = channels.id)
        """,
        (cutoff,),
    )
    channels = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    return ImportResult(len(watches), skipped, channels, len(subs))


# Recent watching counts most; a subscription is a mild signal on its own.
RANK_SQL = "(watches_180d * 3 + MIN(watch_count, 100) + is_subscribed * 5)"
