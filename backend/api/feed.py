import os

import yaml
from fastapi import APIRouter, Query

from backend.db import db

router = APIRouter()

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "settings.yaml",
)


def _load_min_score() -> int:
    try:
        with open(_SETTINGS_PATH) as f:
            return yaml.safe_load(f).get("min_relevance_score", 50)
    except FileNotFoundError:
        return 50


@router.get("/feed")
def get_feed(limit: int = Query(default=200, le=500)):
    """
    Return all unread items:
    - Scored items above min_relevance_score, sorted by score descending
    - Unscored items (NULL) appended after, sorted by published_at descending
    """
    threshold = _load_min_score()

    with db() as conn:
        rows = conn.execute(
            """SELECT id, type, title, source_id, source_name, url, thumbnail_url,
                      description, duration, reddit_score, body,
                      published_at, fetched_at, is_read,
                      relevance_score, summary, is_low_density, scored_at,
                      is_discovery, discovery_topic
               FROM content_items
               WHERE is_read = 0
                 AND (
                   (is_discovery = 0 AND (relevance_score IS NULL OR relevance_score >= ?))
                   OR is_discovery = 1
                 )
               ORDER BY
                 relevance_score DESC,   -- NULLs sort last in SQLite DESC
                 published_at DESC
               LIMIT ?""",
            (threshold, limit),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/stats")
def get_stats():
    threshold = _load_min_score()
    with db() as conn:
        unread = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE is_read = 0"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0]
        videos = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE type = 'video'"
        ).fetchone()[0]
        posts = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE type = 'post'"
        ).fetchone()[0]
        scored = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE scored_at IS NOT NULL"
        ).fetchone()[0]
        filtered = conn.execute(
            "SELECT COUNT(*) FROM content_items WHERE relevance_score IS NOT NULL AND relevance_score < ?",
            (threshold,),
        ).fetchone()[0]
    return {
        "unread": unread,
        "total": total,
        "videos": videos,
        "posts": posts,
        "scored": scored,
        "filtered_below_threshold": filtered,
    }
