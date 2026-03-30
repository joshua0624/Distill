"""
Reddit API service via PRAW.

NOTE: Reddit API approval may still be pending. This module is built but
      fetch_all_subreddits() will fail gracefully if credentials are absent.
"""
import logging
import os
from datetime import datetime, timezone

import praw
import yaml
from dotenv import load_dotenv

from backend.db import db

load_dotenv()
logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "subreddits.yaml",
)


def _get_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"),
        user_agent="distill/1.0 by distill-app",
    )


def load_subreddits() -> list[str]:
    with open(_CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("subreddits", [])


def fetch_subreddit_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = 25) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    posts: list[dict] = []

    for post in reddit.subreddit(subreddit_name).hot(limit=limit):
        if post.stickied:
            continue

        published_at = datetime.fromtimestamp(
            post.created_utc, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        thumbnail = post.thumbnail if (post.thumbnail or "").startswith("http") else None

        posts.append(
            {
                "id": f"reddit_{post.id}",
                "type": "post",
                "title": post.title,
                "source_id": subreddit_name.lower(),
                "source_name": f"r/{subreddit_name}",
                "url": f"https://reddit.com{post.permalink}",
                "thumbnail_url": thumbnail,
                "description": None,
                "duration": None,
                "reddit_score": post.score,
                "body": (post.selftext or "")[:500] or None,
                "published_at": published_at,
                "fetched_at": now,
            }
        )

    return posts


def store_posts(posts: list[dict]) -> int:
    """Insert posts; skip duplicates. Returns count of newly inserted rows."""
    if not posts:
        return 0
    inserted = 0
    with db() as conn:
        for post in posts:
            cur = conn.execute(
                """INSERT OR IGNORE INTO content_items
                   (id, type, title, source_id, source_name, url, thumbnail_url,
                    description, duration, reddit_score, body, published_at, fetched_at)
                   VALUES (:id, :type, :title, :source_id, :source_name, :url,
                           :thumbnail_url, :description, :duration, :reddit_score,
                           :body, :published_at, :fetched_at)""",
                post,
            )
            inserted += cur.rowcount
    return inserted


def fetch_all_subreddits(limit_per: int = 25) -> int:
    """
    Fetch hot posts from all configured subreddits.
    Returns total new posts inserted.
    """
    client_id = os.getenv("REDDIT_CLIENT_ID")
    if not client_id:
        logger.warning("REDDIT_CLIENT_ID not set — skipping Reddit fetch")
        return 0

    subreddits = load_subreddits()
    if not subreddits:
        logger.warning("No subreddits configured in config/subreddits.yaml")
        return 0

    reddit = _get_reddit()
    total = 0

    for sub in subreddits:
        try:
            posts = fetch_subreddit_posts(reddit, sub, limit=limit_per)
            count = store_posts(posts)
            total += count
            logger.info("r/%s: stored %d new posts", sub, count)
        except Exception:
            logger.exception("Failed to fetch r/%s", sub)

    return total
