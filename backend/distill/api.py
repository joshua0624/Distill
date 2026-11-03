"""HTTP API for the frontend. Run with `distill serve`."""
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from distill import db
from distill.classify import classify, month_spend
from distill.config import ROOT, settings
from distill.ingest import apply_rules, ingest
from distill.takeout import RANK_SQL
from distill.youtube import YouTube, looks_like_link

log = logging.getLogger(__name__)
app = FastAPI(title="Distill")
yt = YouTube()


@app.middleware("http")
async def no_store_api(request, call_next):
    """API responses are live data: never let the browser (or the installed app) reuse one."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_conn():
    with db.session() as conn:
        yield conn


Conn = Depends(get_conn)


# A channel with this many recent watches is already near the top of the normal queue.
REDISCOVER_MAX_RECENT = 3
REDISCOVER_MIN_WATCHES = 3


def _rediscover_sql(months: int) -> tuple[str, tuple]:
    """Unreviewed channels I watched a lot between `months` and 6 months ago, but rarely since.
    The default ranking favours the last 6 months, so these sit deep in the normal queue."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=months * 30.4)).strftime("%Y-%m-%dT%H:%M:%S")
    end = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S")
    sql = (
        "SELECT c.*, h.n AS window_watches FROM channels c JOIN ("
        "  SELECT channel_id, COUNT(*) AS n FROM takeout_history"
        "  WHERE watched_at >= ? AND watched_at < ? GROUP BY channel_id) h ON h.channel_id = c.id "
        f"WHERE c.reviewed = 0 AND c.watches_180d < {REDISCOVER_MAX_RECENT} AND h.n >= {REDISCOVER_MIN_WATCHES}"
    )
    return sql, (start, end)


@app.get("/api/triage/stats")
def triage_stats(months: int = 24, conn: sqlite3.Connection = Conn):
    by_tier = {r["tier"]: r["n"] for r in conn.execute(
        "SELECT tier, COUNT(*) n FROM channels WHERE reviewed = 1 GROUP BY tier")}
    unreviewed = conn.execute("SELECT COUNT(*) FROM channels WHERE reviewed = 0").fetchone()[0]
    sql, params = _rediscover_sql(months)
    rediscover = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    return {"reviewed": by_tier, "unreviewed": unreviewed, "rediscover": rediscover}


@app.get("/api/triage/next")
def triage_next(limit: int = 20, mode: Literal["top", "rediscover"] = "top", months: int = 24,
                conn: sqlite3.Connection = Conn):
    """Unreviewed channels with a few titles I actually watched: most-watched first ("top"),
    or older favourites I've stopped watching ("rediscover")."""
    if mode == "rediscover":
        sql, params = _rediscover_sql(months)
        rows = conn.execute(sql + " ORDER BY h.n DESC, c.title LIMIT ?", (*params, limit)).fetchall()
    else:
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
    apply_rules(conn)  # e.g. a discovered channel promoted from the watch page shows up in Home now
    return {"ok": True}


class AddChannel(BaseModel):
    query: str
    tier: Literal["trusted", "mixed", "blocked"]


@app.post("/api/channels/add")
def add_channel(body: AddChannel, background: BackgroundTasks, conn: sqlite3.Connection = Conn):
    """Add a channel by link, @handle or id, and pull its recent uploads straight away.
    A plain name returns {"choices": [...]} instead: the top search result is often wrong."""
    try:
        ch = yt.resolve_channel(body.query)
        if not ch and not looks_like_link(body.query):
            choices = yt.search_channels(body.query)
            if choices:
                return {"choices": choices}
    except Exception as e:
        log.warning("resolve %r failed: %s", body.query, e)
        raise HTTPException(502, "Couldn't reach YouTube")
    if not ch:
        raise HTTPException(404, "No channel found")
    existing = conn.execute("SELECT tier, reviewed FROM channels WHERE id = ?", (ch["id"],)).fetchone()
    conn.execute(
        "INSERT INTO channels (id, title, handle, thumb_url, tier, reviewed, source, tier_changed_at) "
        "VALUES (?, ?, ?, ?, ?, 1, 'manual', datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET tier = excluded.tier, reviewed = 1, title = excluded.title, "
        "handle = COALESCE(excluded.handle, handle), thumb_url = COALESCE(excluded.thumb_url, thumb_url), "
        "tier_changed_at = datetime('now')",
        (ch["id"], ch["title"], ch["handle"], ch["thumb_url"], body.tier))
    conn.commit()
    if body.tier != "blocked":
        ingest(conn, yt, channel_ids=[ch["id"]])
    apply_rules(conn)
    counts = conn.execute(
        "SELECT COALESCE(SUM(d.visible), 0), COALESCE(SUM(d.reason = 'pending_llm'), 0) FROM decisions d "
        "JOIN videos v ON v.id = d.video_id WHERE v.channel_id = ?", (ch["id"],)).fetchone()
    if counts[1] and os.getenv("ANTHROPIC_API_KEY"):
        background.add_task(_classify_soon)
    # Commit now: the request's own commit only runs after background tasks finish, and the
    # classifier needs to write.
    conn.commit()
    return {**ch, "tier": body.tier, "visible": counts[0], "pending": counts[1],
            "previous_tier": existing["tier"] if existing and existing["reviewed"] else None}


def _classify_soon() -> None:
    """Classify a newly added mixed channel's videos without making the request wait for it."""
    with db.session() as conn:
        classify(conn, wait_s=0)


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
           p.position_s, p.watched_pct, p.last_watched_at, q.video_id IS NOT NULL AS in_queue,
           d.visible, d.reason, d.overridden, cl.category, cl.one_line,
           c.tier, v.source, v.discovered_via,
           (SELECT CASE WHEN f.value = 'clear' THEN NULL ELSE f.signal END FROM feedback f
            WHERE f.video_id = v.id AND f.signal IN ('up', 'down') ORDER BY f.id DESC LIMIT 1) AS rating
    FROM videos v
    JOIN channels c ON c.id = v.channel_id
    LEFT JOIN progress p ON p.video_id = v.id
    LEFT JOIN queue q ON q.video_id = v.id
    LEFT JOIN decisions d ON d.video_id = v.id
    LEFT JOIN classifications cl ON cl.video_id = v.id
"""


@app.get("/api/feed")
def feed(limit: int = 60, offset: int = 0, conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        CARD_SQL + " WHERE d.visible = 1 AND c.tier != 'candidate' "
        "ORDER BY v.published_at DESC LIMIT ? OFFSET ?",
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


# Reasons that are noise in the Hidden view: you never want to scroll past these.
HIDDEN_EXCLUDE = ("blocked_channel", "short", "upcoming", "live")


@app.get("/api/hidden")
def hidden(reason: str | None = None, limit: int = 100, offset: int = 0,
           conn: sqlite3.Connection = Conn):
    """Videos hidden by the rules, newest first, optionally for one reason."""
    sql = CARD_SQL + " WHERE d.visible = 0"
    params: list = []
    if reason:
        sql += " AND d.reason = ?"
        params.append(reason)
    else:
        sql += f" AND d.reason NOT IN ({','.join('?' * len(HIDDEN_EXCLUDE))})"
        params += HIDDEN_EXCLUDE
    rows = conn.execute(sql + " ORDER BY v.published_at DESC LIMIT ? OFFSET ?",
                        (*params, limit, offset)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/hidden/reasons")
def hidden_reasons(conn: sqlite3.Connection = Conn):
    rows = conn.execute(
        "SELECT reason, COUNT(*) AS count FROM decisions WHERE visible = 0 "
        "GROUP BY reason ORDER BY count DESC").fetchall()
    return [dict(r) for r in rows]


class Override(BaseModel):
    visible: bool | None  # None clears the override and lets the rules decide again


@app.post("/api/videos/{video_id}/override")
def override(video_id: str, body: Override, conn: sqlite3.Connection = Conn):
    """Show anyway / Hide this. Each one is kept as a label for the prompt and `distill eval`."""
    if not conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone():
        raise HTTPException(404)
    value = "clear" if body.visible is None else ("show" if body.visible else "hide")
    conn.execute("INSERT INTO feedback (video_id, signal, value) VALUES (?, 'override', ?)",
                 (video_id, value))
    if body.visible is None:
        conn.execute("UPDATE decisions SET overridden = 0 WHERE video_id = ?", (video_id,))
        apply_rules(conn)
    else:
        conn.execute(
            "INSERT INTO decisions (video_id, visible, reason, overridden) VALUES (?, ?, 'override', 1) "
            "ON CONFLICT(video_id) DO UPDATE SET visible = excluded.visible, reason = 'override', "
            "overridden = 1, decided_at = datetime('now')",
            (video_id, int(body.visible)))
    row = conn.execute("SELECT visible, reason, overridden FROM decisions WHERE video_id = ?",
                       (video_id,)).fetchone()
    return dict(row) if row else {"visible": None, "reason": None, "overridden": 0}


@app.get("/api/discovery")
def discovery(conn: sqlite3.Connection = Conn):
    """The Discovery row: passing videos from channels I don't follow, capped and unwatched.
    Takes the best of each category in turn, so lectures don't crowd out sports and gaming."""
    rows = conn.execute(
        CARD_SQL + " WHERE d.visible = 1 AND c.tier = 'candidate' AND p.video_id IS NULL "
        "AND v.fetched_at >= datetime('now', ?) "
        "ORDER BY cl.interest_match = 'strong' DESC, cl.substance = 'high' DESC, v.views DESC",
        (f"-{settings.discovery_max_age_days} days",)).fetchall()
    by_category: dict[str, list] = {}
    for r in rows:
        by_category.setdefault(r["category"] or "other", []).append(dict(r))
    out: list[dict] = []
    while len(out) < settings.discovery_daily_cap and any(by_category.values()):
        for videos in by_category.values():
            if videos and len(out) < settings.discovery_daily_cap:
                out.append(videos.pop(0))
    return out


class Rating(BaseModel):
    rating: Literal["up", "down"] | None


@app.post("/api/videos/{video_id}/rating")
def rate(video_id: str, body: Rating, conn: sqlite3.Connection = Conn):
    """👍 / 👎. Feeds the prompt's examples, adjacent discovery and channel suggestions."""
    if not conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone():
        raise HTTPException(404)
    conn.execute("INSERT INTO feedback (video_id, signal, value) VALUES (?, ?, ?)",
                 (video_id, body.rating or "up", "1" if body.rating else "clear"))
    return {"rating": body.rating}


SUGGEST_WINDOW = "-60 days"


@app.get("/api/suggestions")
def suggestions(conn: sqlite3.Connection = Conn):
    """Promote a channel I keep liking or finishing; demote a trusted one I keep disliking."""
    rows = conn.execute("""
        WITH rating AS (
            SELECT f.video_id, f.signal FROM feedback f
            WHERE f.signal IN ('up', 'down') AND f.value != 'clear' AND f.created_at >= datetime('now', :w)
              AND f.id = (SELECT MAX(id) FROM feedback WHERE video_id = f.video_id AND signal IN ('up', 'down'))
        ), finished AS (
            SELECT video_id FROM progress
            WHERE watched_pct >= 50 AND last_watched_at >= datetime('now', :w)
        ), per AS (
            SELECT c.id, c.title, c.tier, c.thumb_url,
                SUM(r.signal = 'up') AS ups, SUM(r.signal = 'down') AS downs,
                SUM(fi.video_id IS NOT NULL) AS finished
            FROM channels c JOIN videos v ON v.channel_id = c.id
            LEFT JOIN rating r ON r.video_id = v.id
            LEFT JOIN finished fi ON fi.video_id = v.id
            WHERE c.tier != 'blocked' AND (r.video_id IS NOT NULL OR fi.video_id IS NOT NULL)
            GROUP BY c.id
        )
        SELECT per.*, CASE WHEN tier = 'trusted' THEN 'demote' ELSE 'promote' END AS kind
        FROM per
        WHERE ((tier IN ('candidate', 'mixed') AND (ups >= 3 OR finished >= 3))
               OR (tier = 'trusted' AND downs >= 2))
          AND NOT EXISTS (SELECT 1 FROM suggestion_dismissals sd WHERE sd.channel_id = per.id
                          AND sd.kind = CASE WHEN per.tier = 'trusted' THEN 'demote' ELSE 'promote' END)
        ORDER BY ups + finished DESC
    """, {"w": SUGGEST_WINDOW}).fetchall()
    return [dict(r) for r in rows]


class Dismiss(BaseModel):
    kind: Literal["promote", "demote"]


@app.post("/api/suggestions/{channel_id}/dismiss")
def dismiss_suggestion(channel_id: str, body: Dismiss, conn: sqlite3.Connection = Conn):
    conn.execute("INSERT OR REPLACE INTO suggestion_dismissals (channel_id, kind) VALUES (?, ?)",
                 (channel_id, body.kind))
    return {"ok": True}


@app.get("/api/llm/usage")
def llm_usage(conn: sqlite3.Connection = Conn):
    pending = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE reason = 'pending_llm' AND overridden = 0").fetchone()[0]
    return {"month_usd": month_spend(conn), "budget_usd": settings.llm_monthly_budget_usd,
            "model": settings.llm_model, "pending": pending}


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
