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


@app.get("/api/feed")
def feed(limit: int = 60, offset: int = 0, conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        "SELECT v.id, v.title, v.published_at, v.duration_s, v.views, v.thumb_url, "
        "c.id AS channel_id, c.title AS channel_title, c.thumb_url AS channel_thumb, d.reason "
        "FROM videos v JOIN decisions d ON d.video_id = v.id JOIN channels c ON c.id = v.channel_id "
        "WHERE d.visible = 1 ORDER BY v.published_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


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
