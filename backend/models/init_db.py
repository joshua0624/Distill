"""
Initialize the SQLite database schema.
Run once before starting the server:
    uv run python -m backend.models.init_db
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.db import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    thumbnail_url       TEXT,
    uploads_playlist_id TEXT,
    synced_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_items (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL CHECK(type IN ('video', 'post')),
    title           TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    url             TEXT NOT NULL,
    thumbnail_url   TEXT,
    description     TEXT,
    duration        INTEGER,
    reddit_score    INTEGER,
    body            TEXT,
    published_at    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_read         INTEGER NOT NULL DEFAULT 0,
    -- Phase 2: LLM scoring fields (nullable until batch runs)
    relevance_score INTEGER,
    summary         TEXT,
    is_low_density  INTEGER,
    scored_at       TEXT,
    transcript      TEXT,
    -- Phase 3: discovery fields
    is_discovery    INTEGER NOT NULL DEFAULT 0,
    discovery_topic TEXT
);

CREATE TABLE IF NOT EXISTS discovery_topics (
    topic        TEXT PRIMARY KEY,
    last_used_at TEXT NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_items_type        ON content_items(type);
CREATE INDEX IF NOT EXISTS idx_items_is_read     ON content_items(is_read);
CREATE INDEX IF NOT EXISTS idx_items_published   ON content_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_discovery   ON content_items(is_discovery);
"""


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        print("Database initialized successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
