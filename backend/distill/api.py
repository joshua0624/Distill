"""HTTP API for the frontend. Run with `distill serve`."""
import logging
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from distill import db
from distill.config import ROOT
from distill.takeout import RANK_SQL
from distill.youtube import YouTube

log = logging.getLogger(__name__)
app = FastAPI(title="Distill")
yt = YouTube()


def get_conn():
    with db.session() as conn:
        yield conn


Conn = Depends(get_conn)


@app.get("/api/triage/stats")
def triage_stats(conn: sqlite3.Connection = Conn):
    by_tier = {r["tier"]: r["n"] for r in conn.execute(
        "SELECT tier, COUNT(*) n FROM channels WHERE reviewed = 1 GROUP BY tier")}
    unreviewed = conn.execute("SELECT COUNT(*) FROM channels WHERE reviewed = 0").fetchone()[0]
    return {"reviewed": by_tier, "unreviewed": unreviewed}


@app.get("/api/triage/next")
def triage_next(limit: int = 20, conn: sqlite3.Connection = Conn):
    """Unreviewed channels, most-watched first, with a few titles I actually watched."""
    rows = conn.execute(
        f"SELECT *, {RANK_SQL} AS rank FROM channels WHERE reviewed = 0 "
        "ORDER BY rank DESC, title LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        watched = conn.execute(
            "SELECT title FROM takeout_history WHERE channel_id = ? "
            "GROUP BY video_id ORDER BY MAX(watched_at) DESC LIMIT 3", (r["id"],)
        ).fetchall()
        out.append({**dict(r), "watched_titles": [w["title"] for w in watched]})
    return out


@app.get("/api/channels/{channel_id}/preview")
def channel_preview(channel_id: str, conn: sqlite3.Connection = Conn):
    """Latest uploads (free, via RSS) and avatar (1 quota unit, cached)."""
    ch = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not ch:
        raise HTTPException(404)
    thumb = ch["thumb_url"]
    if not thumb and yt.api_key:
        try:
            info = yt.channel_info([channel_id]).get(channel_id)
            if info:
                thumb = info["thumb_url"]
                conn.execute("UPDATE channels SET thumb_url = ?, handle = ? WHERE id = ?",
                             (thumb, info["handle"], channel_id))
        except Exception as e:
            log.warning("channels.list failed for %s: %s", channel_id, e)
    try:
        uploads = yt.channel_uploads(channel_id)
    except Exception as e:
        log.warning("RSS failed for %s: %s", channel_id, e)
        uploads = []
    latest = [
        {"id": u["id"], "title": u["title"], "published_at": u["published_at"],
         "thumb_url": u["thumb_url"], "is_short": u["is_short"]}
        for u in uploads if not u["is_short"]
    ][:5]
    return {"thumb_url": thumb, "latest": latest,
            "shorts_share": sum(u["is_short"] for u in uploads) / len(uploads) if uploads else 0}


class TierUpdate(BaseModel):
    tier: Literal["trusted", "mixed", "blocked", "candidate"]
    reviewed: bool = True


@app.post("/api/channels/{channel_id}/tier")
def set_tier(channel_id: str, body: TierUpdate, conn: sqlite3.Connection = Conn):
    cur = conn.execute(
        "UPDATE channels SET tier = ?, reviewed = ?, tier_changed_at = datetime('now') WHERE id = ?",
        (body.tier, int(body.reviewed), channel_id),
    )
    if not cur.rowcount:
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/channels")
def list_channels(tier: str | None = None, conn: sqlite3.Connection = Conn):
    sql = f"SELECT *, {RANK_SQL} AS rank FROM channels WHERE reviewed = 1"
    params: tuple = ()
    if tier:
        sql += " AND tier = ?"
        params = (tier,)
    return [dict(r) for r in conn.execute(sql + " ORDER BY rank DESC, title", params)]


# Everything a video card needs, including watch progress and queue state.
CARD_SQL = """
    SELECT v.id, v.title, v.published_at, v.duration_s, v.views, v.thumb_url,
           c.id AS channel_id, c.title AS channel_title, c.thumb_url AS channel_thumb,
           p.position_s, p.watched_pct, p.last_watched_at, q.video_id IS NOT NULL AS in_queue
    FROM videos v
    JOIN channels c ON c.id = v.channel_id
    LEFT JOIN progress p ON p.video_id = v.id
    LEFT JOIN queue q ON q.video_id = v.id
"""


@app.get("/api/feed")
def feed(limit: int = 60, offset: int = 0, conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        CARD_SQL + " JOIN decisions d ON d.video_id = v.id "
        "WHERE d.visible = 1 ORDER BY v.published_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/videos/{video_id}")
def video(video_id: str, conn: sqlite3.Connection = Conn):
    row = conn.execute(
        CARD_SQL.replace("SELECT ", "SELECT v.description, ", 1) + " WHERE v.id = ?", (video_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404)
    return dict(row)


class Progress(BaseModel):
    position_s: float
    duration_s: float


@app.put("/api/progress/{video_id}")
def save_progress(video_id: str, body: Progress, conn: sqlite3.Connection = Conn):
    if not conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone():
        raise HTTPException(404)
    pct = min(100.0, 100 * body.position_s / body.duration_s) if body.duration_s > 0 else 0
    conn.execute(
        "INSERT INTO progress (video_id, position_s, watched_pct) VALUES (?, ?, ?) "
        "ON CONFLICT(video_id) DO UPDATE SET position_s = excluded.position_s, "
        "watched_pct = MAX(progress.watched_pct, excluded.watched_pct), "
        "last_watched_at = datetime('now')",
        (video_id, body.position_s, pct),
    )
    return {"ok": True}


@app.get("/api/history")
def history(limit: int = 100, conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        CARD_SQL + " WHERE p.video_id IS NOT NULL ORDER BY p.last_watched_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/queue")
def get_queue(conn: sqlite3.Connection = Conn):
    return [dict(r) for r in conn.execute(CARD_SQL + " WHERE q.video_id IS NOT NULL ORDER BY q.position")]


@app.post("/api/queue/{video_id}")
def add_to_queue(video_id: str, conn: sqlite3.Connection = Conn):
    if not conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone():
        raise HTTPException(404)
    conn.execute(
        "INSERT OR IGNORE INTO queue (video_id, position) "
        "VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM queue))",
        (video_id,),
    )
    return {"ok": True}


@app.delete("/api/queue/{video_id}")
def remove_from_queue(video_id: str, conn: sqlite3.Connection = Conn):
    conn.execute("DELETE FROM queue WHERE video_id = ?", (video_id,))
    return {"ok": True}


class QueueOrder(BaseModel):
    ids: list[str]


@app.put("/api/queue")
def reorder_queue(body: QueueOrder, conn: sqlite3.Connection = Conn):
    """Set the order; ids not listed keep their relative order after the listed ones."""
    current = [r[0] for r in conn.execute("SELECT video_id FROM queue ORDER BY position")]
    listed = [i for i in body.ids if i in current]
    order = listed + [i for i in current if i not in listed]
    conn.executemany("UPDATE queue SET position = ? WHERE video_id = ?",
                     [(n, vid) for n, vid in enumerate(order, 1)])
    return {"ok": True}


@app.get("/api/hidden")
def hidden(limit: int = 100, conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        "SELECT v.id, v.title, v.duration_s, c.title AS channel_title, d.reason "
        "FROM videos v JOIN decisions d ON d.video_id = v.id JOIN channels c ON c.id = v.channel_id "
        "WHERE d.visible = 0 ORDER BY v.published_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Serve built files, and index.html for client-side routes like /triage."""
        file = (dist / path).resolve()
        if path.startswith("api/"):
            raise HTTPException(404)
        if file.is_file() and file.is_relative_to(dist.resolve()):
            return FileResponse(file)
        return FileResponse(dist / "index.html")
