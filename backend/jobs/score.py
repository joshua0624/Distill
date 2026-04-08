"""
Scoring batch job — run nightly at 4am via cron.

Fetches all unscored content items, gets transcripts for videos,
scores each item via Ollama, and writes results back to SQLite.

Usage:
    uv run python -m backend.jobs.score
"""
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.db import db
from backend.services.ollama import score_item
from backend.services.transcripts import fetch_transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    logger.info("=== Distill scoring job starting ===")

    with db() as conn:
        rows = conn.execute(
            """SELECT id, type, title, source_name, description, body
               FROM content_items
               WHERE scored_at IS NULL
               ORDER BY published_at DESC"""
        ).fetchall()

    if not rows:
        logger.info("No unscored items. Exiting.")
        return

    logger.info("Scoring %d items...", len(rows))
    succeeded = 0
    failed = 0

    for row in rows:
        item_id = row["id"]
        item_type = row["type"]
        title = row["title"]

        logger.info("[%s] %s", item_type, title[:80])
        t0 = time.perf_counter()

        # Fetch transcript for videos
        transcript = None
        if item_type == "video":
            transcript = fetch_transcript(item_id)
            if transcript:
                logger.debug("  Transcript: %d words", len(transcript.split()))
                time.sleep(1.5)  # avoid YouTube transcript throttling
            else:
                logger.debug("  No transcript available")

        content = transcript or row["body"]

        try:
            result = score_item(
                item_id=item_id,
                item_type=item_type,
                title=title,
                source_name=row["source_name"],
                description=row["description"],
                transcript_or_body=content,
            )
        except Exception:
            logger.exception("  Scoring failed for %s — skipping", item_id)
            failed += 1
            continue

        elapsed = time.perf_counter() - t0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with db() as conn:
            conn.execute(
                """UPDATE content_items
                   SET relevance_score = ?,
                       summary         = ?,
                       is_low_density  = ?,
                       scored_at       = ?,
                       transcript      = ?
                   WHERE id = ?""",
                (
                    result["relevance_score"],
                    result["summary"],
                    1 if result["is_low_density"] else 0,
                    now,
                    transcript,
                    item_id,
                ),
            )

        logger.info(
            "  score=%d low_density=%s  (%.1fs)",
            result["relevance_score"],
            result["is_low_density"],
            elapsed,
        )
        succeeded += 1

    logger.info(
        "=== Scoring complete: %d scored, %d failed ===", succeeded, failed
    )


if __name__ == "__main__":
    run()
