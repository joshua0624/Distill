"""
Phase 3 migration: add is_saved column to content_items.

Safe to run multiple times.

Usage:
    uv run python -m backend.models.migrate_phase3
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.db import get_connection

NEW_COLUMNS = [
    ("is_saved", "INTEGER NOT NULL DEFAULT 0"),
]


def migrate():
    conn = get_connection()
    try:
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(content_items)").fetchall()
        }
        added = []
        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE content_items ADD COLUMN {col_name} {col_type}"
                )
                added.append(col_name)
                print(f"  Added column: {col_name} {col_type}")
            else:
                print(f"  Already exists: {col_name}")
        conn.commit()
        if added:
            print(f"Migration complete. Added: {', '.join(added)}")
        else:
            print("Migration complete. No changes needed.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
