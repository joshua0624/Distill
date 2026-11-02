"""SQLite storage. One file, created on first connect."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from distill.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    handle           TEXT,
    thumb_url        TEXT,
    tier             TEXT NOT NULL DEFAULT 'candidate'
                     CHECK (tier IN ('trusted', 'mixed', 'blocked', 'candidate')),
    reviewed         INTEGER NOT NULL DEFAULT 0,
    source           TEXT NOT NULL,           -- takeout_history | takeout_subscription | discovery
    is_subscribed    INTEGER NOT NULL DEFAULT 0,
    watch_count      INTEGER NOT NULL DEFAULT 0,
    watches_180d     INTEGER NOT NULL DEFAULT 0,
    last_watched_at  TEXT,
    added_at         TEXT NOT NULL DEFAULT (datetime('now')),
    tier_changed_at  TEXT,
    last_fetched_at  TEXT
);

CREATE TABLE IF NOT EXISTS sport_rules (
    id              INTEGER PRIMARY KEY,
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    title_pattern   TEXT NOT NULL,            -- case-insensitive regex
    min_duration_s  INTEGER,
    enabled         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS videos (
    id              TEXT PRIMARY KEY,
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    title           TEXT NOT NULL,
    description     TEXT,
    published_at    TEXT NOT NULL,
    thumb_url       TEXT,
    duration_s      INTEGER,
    is_short        INTEGER,
    live_status     TEXT,                     -- none | live | upcoming
    views           INTEGER,
    likes           INTEGER,
    tags_json       TEXT,
    source          TEXT NOT NULL,            -- rss | search | hn | adjacent
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    details_at      TEXT                      -- when videos.list details were filled in
);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id, published_at);

CREATE TABLE IF NOT EXISTS decisions (
    video_id    TEXT PRIMARY KEY REFERENCES videos(id),
    visible     INTEGER NOT NULL,
    reason      TEXT NOT NULL,                -- rule that decided, e.g. 'short', 'trusted'
    overridden  INTEGER NOT NULL DEFAULT 0,
    decided_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS takeout_history (
    video_id    TEXT NOT NULL,
    title       TEXT,
    channel_id  TEXT NOT NULL,
    watched_at  TEXT NOT NULL,
    PRIMARY KEY (video_id, watched_at)
);
CREATE INDEX IF NOT EXISTS idx_history_channel ON takeout_history(channel_id, watched_at);

CREATE TABLE IF NOT EXISTS progress (
    video_id         TEXT PRIMARY KEY REFERENCES videos(id),
    position_s       REAL NOT NULL,
    watched_pct      REAL NOT NULL,           -- furthest point reached, 0-100
    last_watched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queue (
    video_id    TEXT PRIMARY KEY REFERENCES videos(id),
    position    REAL NOT NULL,                -- sort key; reorder rewrites 1..n
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS classifications (
    video_id           TEXT PRIMARY KEY REFERENCES videos(id),
    category           TEXT,                  -- NULL when error is set
    topic              TEXT,
    format             TEXT,
    clickbait          INTEGER,
    substance          TEXT,
    slop_signals_json  TEXT,
    interest_match     TEXT,
    one_line           TEXT,
    error              TEXT,                  -- refusal | max_tokens | bad_json | api error message
    model              TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY,
    video_id    TEXT NOT NULL REFERENCES videos(id),
    signal      TEXT NOT NULL,                -- override (M3); up/down/hide later
    value       TEXT NOT NULL,                -- show | hide | clear
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_usage (
    date                TEXT PRIMARY KEY,     -- YYYY-MM-DD, UTC
    requests            INTEGER NOT NULL DEFAULT 0,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_batches (
    id          TEXT PRIMARY KEY,             -- Anthropic batch id
    status      TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | ended
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_batch_videos (
    batch_id    TEXT NOT NULL REFERENCES llm_batches(id),
    video_id    TEXT NOT NULL REFERENCES videos(id),
    PRIMARY KEY (batch_id, video_id)
);
"""


def db_path() -> Path:
    return Path(settings.db_path)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may open and use a request's connection on different threads; each
    # request still gets its own connection, so this is safe.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def session(path: Path | str | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
