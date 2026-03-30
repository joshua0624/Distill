"""
Content fetch job — runs twice daily via cron.

Usage:
    uv run python -m backend.jobs.fetch

Fetches YouTube videos from all subscribed channels and Reddit posts
from configured subreddits, stores new items in SQLite.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.services.youtube import sync_subscriptions, fetch_all_channels
from backend.services.reddit import fetch_all_subreddits

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    logger.info("=== Distill fetch job starting ===")

    # --- YouTube ---
    try:
        logger.info("Syncing YouTube subscriptions...")
        channels = sync_subscriptions()
        logger.info("Subscriptions synced: %d channels", len(channels))

        logger.info("Fetching videos from subscribed channels...")
        video_count = fetch_all_channels(max_per_channel=10)
        logger.info("YouTube fetch complete: %d new videos", video_count)
    except Exception:
        logger.exception("YouTube fetch failed")

    # --- Reddit ---
    try:
        logger.info("Fetching Reddit posts...")
        post_count = fetch_all_subreddits(limit_per=25)
        logger.info("Reddit fetch complete: %d new posts", post_count)
    except Exception:
        logger.exception("Reddit fetch failed")

    logger.info("=== Distill fetch job complete ===")


if __name__ == "__main__":
    run()
