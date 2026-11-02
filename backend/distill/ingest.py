"""Fetch new uploads from trusted and mixed channels, fill in details, apply hard rules."""
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from distill.config import Settings, settings as default_settings
from distill.rules import decide
from distill.youtube import YouTube

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    channels: int = 0
    new_videos: int = 0
    detailed: int = 0
    short_checks: int = 0
    visible: int = 0
    errors: int = 0


def ingest(conn: sqlite3.Connection, yt: YouTube, s: Settings = default_settings) -> IngestResult:
    res = IngestResult()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=s.max_video_age_days)).isoformat()

    channels = conn.execute(
        "SELECT id FROM channels WHERE tier IN ('trusted', 'mixed')"
    ).fetchall()
    for (channel_id,) in channels:
        try:
            uploads = yt.channel_uploads(channel_id)
        except Exception as e:  # one bad feed shouldn't stop the run
            log.warning("RSS failed for %s: %s", channel_id, e)
            res.errors += 1
            continue
        res.channels += 1
        for v in uploads:
            if v["published_at"] < cutoff:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO videos (id, channel_id, title, description, published_at, "
                "thumb_url, is_short, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'rss')",
                (v["id"], channel_id, v["title"], v["description"], v["published_at"],
                 v["thumb_url"], 1 if v["is_short"] else None),
            )
            res.new_videos += cur.rowcount
        conn.execute("UPDATE channels SET last_fetched_at = datetime('now') WHERE id = ?",
                     (channel_id,))
    conn.commit()

    _fill_details(conn, yt, s, res)
    _apply_rules(conn, s, res)
    conn.commit()
    return res


def _fill_details(conn, yt: YouTube, s: Settings, res: IngestResult) -> None:
    # New videos, plus live/upcoming ones whose status may have changed.
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM videos WHERE details_at IS NULL OR live_status IN ('upcoming', 'live')"
    )]
    if not ids:
        return
    details = yt.video_details(ids)
    for vid, d in details.items():
        conn.execute(
            "UPDATE videos SET duration_s = ?, live_status = ?, description = ?, tags_json = ?, "
            "views = ?, likes = ?, thumb_url = COALESCE(?, thumb_url), details_at = datetime('now') "
            "WHERE id = ?",
            (d["duration_s"], d["live_status"], d["description"], json.dumps(d["tags"]),
             d["views"], d["likes"], d["thumb_url"], vid),
        )
        res.detailed += 1

    # RSS flags most Shorts; confirm the remaining short-enough ones directly.
    for (vid,) in conn.execute(
        "SELECT id FROM videos WHERE is_short IS NULL AND duration_s > 0 AND duration_s <= ?",
        (s.shorts_max_s,),
    ).fetchall():
        res.short_checks += 1
        try:
            is_short = yt.is_short(vid)
        except Exception as e:
            log.warning("Shorts check failed for %s: %s", vid, e)
            continue
        conn.execute("UPDATE videos SET is_short = ? WHERE id = ?", (int(is_short), vid))
    conn.execute("UPDATE videos SET is_short = 0 WHERE is_short IS NULL AND duration_s > ?",
                 (s.shorts_max_s,))


def _apply_rules(conn, s: Settings, res: IngestResult) -> None:
    """Re-decide every video that hasn't been manually overridden (cheap, and picks up tier changes)."""
    sport_rules: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT * FROM sport_rules WHERE enabled = 1"):
        sport_rules.setdefault(r["channel_id"], []).append(dict(r))

    rows = conn.execute(
        "SELECT v.*, c.tier FROM videos v JOIN channels c ON c.id = v.channel_id "
        "LEFT JOIN decisions d ON d.video_id = v.id "
        "WHERE v.details_at IS NOT NULL AND COALESCE(d.overridden, 0) = 0"
    ).fetchall()
    for row in rows:
        d = decide(dict(row), row["tier"], sport_rules.get(row["channel_id"], []), s)
        conn.execute(
            "INSERT INTO decisions (video_id, visible, reason) VALUES (?, ?, ?) "
            "ON CONFLICT(video_id) DO UPDATE SET visible = excluded.visible, "
            "reason = excluded.reason, decided_at = datetime('now') "
            "WHERE decisions.reason != excluded.reason OR decisions.visible != excluded.visible",
            (row["id"], int(d.visible), d.reason),
        )
        res.visible += d.visible
