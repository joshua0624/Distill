"""
Discovery batch job — run daily (after the score job) via cron.

Surfaces up to discovery_daily_cap items from outside the subscription
whitelist using topic-based search. Items are scored for quality, not
topical relevance, and appear in the feed with a "Discover" badge.

Usage:
    uv run python -m backend.jobs.discover
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.services.discovery import run_discovery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    logger.info("=== Distill discovery job starting ===")
    try:
        count = run_discovery()
        logger.info("=== Discovery job complete: %d items stored ===", count)
    except Exception:
        logger.exception("Discovery job failed")


if __name__ == "__main__":
    run()
