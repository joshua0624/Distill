"""
Phase 3 DB migration — adds discovery columns and table.
Run once on any existing database:
    uv run python -m backend.models.migrate
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.db import get_connection


def _try(conn, sql: str) -> None:
    try:
        conn.execute(sql)
        conn.commit()
        print(f"  OK: {sql[:80]}")
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            print(f"  skip (already exists): {sql[:80]}")
        else:
            raise


def run() -> None:
    conn = get_connection()
    try:
        # Phase 2 column that was missing from the original init_db schema
        _try(conn, "ALTER TABLE content_items ADD COLUMN scored_at TEXT")

        # Phase 3 columns
        _try(conn, "ALTER TABLE content_items ADD COLUMN is_discovery INTEGER NOT NULL DEFAULT 0")
        _try(conn, "ALTER TABLE content_items ADD COLUMN discovery_topic TEXT")

        # Phase 3 table — tracks which topics have been used to avoid repetition
        _try(conn, """CREATE TABLE IF NOT EXISTS discovery_topics (
            topic        TEXT PRIMARY KEY,
            last_used_at TEXT NOT NULL,
            use_count    INTEGER NOT NULL DEFAULT 0
        )""")

        _try(conn, "CREATE INDEX IF NOT EXISTS idx_items_discovery ON content_items(is_discovery)")

        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
