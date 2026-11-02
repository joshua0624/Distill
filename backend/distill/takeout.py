"""Import a Google Takeout export: watch history (JSON) and subscriptions (CSV).

Builds the candidate channel list so I triage a ranked list instead of
assembling subscriptions from memory.
"""
import csv
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


def parse_watch_history(path: Path) -> tuple[list[Watch], int]:
    """Return (watches, skipped). Skips ads, YouTube Music, and removed videos."""
    entries = json.loads(path.read_text(encoding="utf-8"))
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
    history = find_file(root, "watch-history.json")
    subs_csv = find_file(root, "subscriptions.csv")
    if not history and not subs_csv:
        raise FileNotFoundError(
            f"No watch-history.json or subscriptions.csv under {root}. "
            "Export history as JSON, not HTML."
        )

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
