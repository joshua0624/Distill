"""
Discovery service: surfaces content from outside the subscription whitelist
using topic-based search on YouTube and Reddit.

Pipeline:
  1. Extract topics from recent high-scoring items via Ollama
  2. Filter out topics used in the last 7 days
  3. Search YouTube and Reddit for each topic (outside the whitelist)
  4. Score candidates for quality (not topical relevance)
  5. Store up to daily_cap items with is_discovery=1
  6. Record topic usage to avoid repetition

YouTube quota: search.list costs 100 units. With up to 10 topics searched,
max cost is ~1,000 units on top of the regular ~250-unit fetch.
"""
import logging
import os
import time
from datetime import datetime, timezone

import praw
import yaml
from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from backend.db import db
from backend.services.ollama import extract_topics, score_discovery_item
from backend.services.transcripts import fetch_transcript
from backend.services.youtube import _build_youtube, _execute_with_retry, _parse_duration

load_dotenv()

logger = logging.getLogger(__name__)

_SUBREDDITS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "subreddits.yaml",
)
_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "settings.yaml",
)

# Minimum quality score for a discovery item to be stored
QUALITY_THRESHOLD = 60
# How many days before a topic can be reused
TOPIC_COOLDOWN_DAYS = 7


def _load_daily_cap() -> int:
    try:
        with open(_SETTINGS_PATH) as f:
            return yaml.safe_load(f).get("discovery_daily_cap", 5)
    except FileNotFoundError:
        return 5


def _count_todays_discovery() -> int:
    """Count discovery items already stored today (UTC date)."""
    with db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM content_items
               WHERE is_discovery = 1
                 AND DATE(fetched_at) = DATE('now')"""
        ).fetchone()
    return row[0]


def _get_recent_high_score_snippets(days: int = 30, min_score: int = 70) -> list[str]:
    """Return 'title — summary' strings from top-rated recent items."""
    with db() as conn:
        rows = conn.execute(
            """SELECT title, summary FROM content_items
               WHERE relevance_score >= ?
                 AND is_discovery = 0
                 AND fetched_at >= datetime('now', ? || ' days')
               ORDER BY relevance_score DESC
               LIMIT 50""",
            (min_score, f"-{days}"),
        ).fetchall()
    snippets = []
    for row in rows:
        if row["summary"]:
            snippets.append(f"{row['title']} — {row['summary']}")
        else:
            snippets.append(row["title"])
    return snippets


def _get_channel_whitelist() -> set[str]:
    with db() as conn:
        rows = conn.execute("SELECT id FROM channels").fetchall()
    return {row["id"] for row in rows}


def _load_subreddit_whitelist() -> set[str]:
    try:
        with open(_SUBREDDITS_PATH) as f:
            data = yaml.safe_load(f)
        return {s.lower() for s in data.get("subreddits", [])}
    except FileNotFoundError:
        return set()


def _get_used_topics(cooldown_days: int = TOPIC_COOLDOWN_DAYS) -> set[str]:
    with db() as conn:
        rows = conn.execute(
            """SELECT topic FROM discovery_topics
               WHERE last_used_at >= datetime('now', ? || ' days')""",
            (f"-{cooldown_days}",),
        ).fetchall()
    return {row["topic"].lower() for row in rows}


def _record_topic_usage(topic: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        conn.execute(
            """INSERT INTO discovery_topics (topic, last_used_at, use_count)
               VALUES (?, ?, 1)
               ON CONFLICT(topic) DO UPDATE SET
                 last_used_at = excluded.last_used_at,
                 use_count    = use_count + 1""",
            (topic.lower(), now),
        )


def _already_in_db(item_ids: list[str]) -> set[str]:
    if not item_ids:
        return set()
    with db() as conn:
        placeholders = ",".join("?" * len(item_ids))
        rows = conn.execute(
            f"SELECT id FROM content_items WHERE id IN ({placeholders})",
            item_ids,
        ).fetchall()
    return {row["id"] for row in rows}


def search_youtube_for_topic(
    youtube, topic: str, channel_whitelist: set[str], max_results: int = 5
) -> list[dict]:
    """
    Search YouTube for a topic, excluding whitelisted channels.
    Returns candidate video dicts (not yet stored).
    Costs 100 quota units per call.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = []

    try:
        resp = _execute_with_retry(
            youtube.search().list(
                part="snippet",
                q=topic,
                type="video",
                maxResults=max_results + 5,  # fetch extra to account for filtering
                order="relevance",
                videoDuration="medium",  # 4-20 min — filters Shorts and very long videos
                safeSearch="none",
            )
        )
    except HttpError as e:
        logger.error("YouTube search failed for topic %r: %s", topic, e)
        return []

    video_ids = [
        item["id"]["videoId"]
        for item in resp.get("items", [])
        if item["id"].get("videoId")
        and item["snippet"].get("channelId") not in channel_whitelist
    ]

    if not video_ids:
        return []

    # Get full details + duration to filter Shorts
    try:
        details_resp = _execute_with_retry(
            youtube.videos().list(
                part="snippet,contentDetails",
                id=",".join(video_ids[:10]),
                maxResults=10,
            )
        )
    except HttpError as e:
        logger.error("YouTube videos.list failed: %s", e)
        return []

    for item in details_resp.get("items", []):
        snippet = item["snippet"]
        duration = _parse_duration(item["contentDetails"].get("duration", ""))
        if duration < 60:
            continue  # filter Shorts

        candidates.append(
            {
                "id": item["id"],
                "type": "video",
                "title": snippet["title"],
                "source_id": snippet["channelId"],
                "source_name": snippet["channelTitle"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "thumbnail_url": snippet.get("thumbnails", {})
                .get("medium", {})
                .get("url"),
                "description": (snippet.get("description") or "")[:500],
                "duration": duration,
                "reddit_score": None,
                "body": None,
                "published_at": snippet.get("publishedAt", now),
                "fetched_at": now,
                "is_discovery": 1,
                "discovery_topic": topic,
            }
        )
        if len(candidates) >= max_results:
            break

    return candidates


def search_reddit_for_topic(
    reddit, topic: str, subreddit_whitelist: set[str], max_results: int = 10
) -> list[dict]:
    """
    Search r/all for a topic, excluding whitelisted subreddits.
    Returns candidate post dicts.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = []

    try:
        results = reddit.subreddit("all").search(
            topic, limit=max_results + 10, time_filter="month", sort="relevance"
        )
        for post in results:
            if post.stickied:
                continue
            subreddit_name = post.subreddit.display_name.lower()
            if subreddit_name in subreddit_whitelist:
                continue

            published_at = datetime.fromtimestamp(
                post.created_utc, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            thumbnail = (
                post.thumbnail if (post.thumbnail or "").startswith("http") else None
            )

            candidates.append(
                {
                    "id": f"reddit_{post.id}",
                    "type": "post",
                    "title": post.title,
                    "source_id": subreddit_name,
                    "source_name": f"r/{post.subreddit.display_name}",
                    "url": f"https://reddit.com{post.permalink}",
                    "thumbnail_url": thumbnail,
                    "description": None,
                    "duration": None,
                    "reddit_score": post.score,
                    "body": (post.selftext or "")[:500] or None,
                    "published_at": published_at,
                    "fetched_at": now,
                    "is_discovery": 1,
                    "discovery_topic": topic,
                }
            )
            if len(candidates) >= max_results:
                break
    except Exception as e:
        logger.error("Reddit search failed for topic %r: %s", topic, e)

    return candidates


def _score_and_store_candidate(candidate: dict) -> bool:
    """
    Fetch transcript if video, score for quality, store if above threshold.
    Returns True if stored.
    """
    item_id = candidate["id"]
    item_type = candidate["type"]

    transcript = None
    if item_type == "video":
        transcript = fetch_transcript(item_id)

    content = transcript or candidate.get("body")

    try:
        result = score_discovery_item(
            item_id=item_id,
            item_type=item_type,
            title=candidate["title"],
            source_name=candidate["source_name"],
            description=candidate.get("description"),
            transcript_or_body=content,
        )
    except Exception:
        logger.exception("  Quality scoring failed for %s — skipping", item_id)
        return False

    quality_score = result["quality_score"]
    logger.info(
        "  [%s] %s | quality=%d",
        item_type,
        candidate["title"][:70],
        quality_score,
    )

    if quality_score < QUALITY_THRESHOLD:
        logger.debug("  Below quality threshold (%d), skipping", quality_score)
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO content_items
               (id, type, title, source_id, source_name, url, thumbnail_url,
                description, duration, reddit_score, body, published_at, fetched_at,
                relevance_score, summary, is_low_density, scored_at,
                transcript, is_discovery, discovery_topic)
               VALUES
               (:id, :type, :title, :source_id, :source_name, :url, :thumbnail_url,
                :description, :duration, :reddit_score, :body, :published_at, :fetched_at,
                :relevance_score, :summary, :is_low_density, :scored_at,
                :transcript, :is_discovery, :discovery_topic)""",
            {
                **candidate,
                "relevance_score": quality_score,
                "summary": result["summary"],
                "is_low_density": 1 if result["is_low_density"] else 0,
                "scored_at": now,
                "transcript": transcript,
            },
        )
        if cur.rowcount == 0:
            logger.debug("  Already in DB: %s", item_id)
            return False

    return True


def run_discovery() -> int:
    """
    Full discovery pipeline. Returns number of items stored.
    """
    daily_cap = _load_daily_cap()
    already_today = _count_todays_discovery()

    if already_today >= daily_cap:
        logger.info(
            "Discovery cap reached (%d/%d items today). Skipping.",
            already_today,
            daily_cap,
        )
        return 0

    remaining_cap = daily_cap - already_today
    logger.info(
        "Discovery: %d/%d slots used today, looking for %d more",
        already_today,
        daily_cap,
        remaining_cap,
    )

    # Step 1: extract topics from recent high-score content
    snippets = _get_recent_high_score_snippets(days=30, min_score=70)
    if len(snippets) < 3:
        # Fall back to 7-day window with lower score threshold
        snippets = _get_recent_high_score_snippets(days=7, min_score=50)

    if not snippets:
        logger.warning("No scored content to extract topics from — skipping discovery")
        return 0

    logger.info("Extracting topics from %d content snippets...", len(snippets))
    topics = extract_topics(snippets)

    if not topics:
        logger.warning("Topic extraction returned no topics")
        return 0

    logger.info("Extracted %d topics: %s", len(topics), topics)

    # Step 2: filter recently-used topics
    used = _get_used_topics()
    fresh_topics = [t for t in topics if t.lower() not in used]
    if not fresh_topics:
        logger.info("All extracted topics recently used — using oldest topics anyway")
        fresh_topics = topics  # reset if everything is used

    logger.info("%d fresh topics to search: %s", len(fresh_topics), fresh_topics[:5])

    # Build clients
    channel_whitelist = _get_channel_whitelist()
    subreddit_whitelist = _load_subreddit_whitelist()

    try:
        youtube = _build_youtube()
    except Exception as e:
        logger.error("Could not build YouTube client: %s", e)
        youtube = None

    reddit = None
    try:
        if os.getenv("REDDIT_CLIENT_ID"):
            reddit = praw.Reddit(
                client_id=os.getenv("REDDIT_CLIENT_ID"),
                client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
                refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"),
                user_agent="distill/1.0 by distill-app",
            )
    except Exception as e:
        logger.warning("Could not initialize Reddit client: %s", e)

    stored = 0

    for topic in fresh_topics:
        if stored >= remaining_cap:
            break

        logger.info("Searching for topic: %r", topic)
        _record_topic_usage(topic)

        candidates: list[dict] = []

        if youtube:
            yt_candidates = search_youtube_for_topic(
                youtube, topic, channel_whitelist, max_results=3
            )
            candidates.extend(yt_candidates)
            time.sleep(0.5)  # gentle rate limiting

        if reddit:
            reddit_candidates = search_reddit_for_topic(
                reddit, topic, subreddit_whitelist, max_results=5
            )
            candidates.extend(reddit_candidates)

        # Filter candidates already in DB
        candidate_ids = [c["id"] for c in candidates]
        existing = _already_in_db(candidate_ids)
        fresh_candidates = [c for c in candidates if c["id"] not in existing]

        logger.info(
            "  %d candidates (%d new) for topic %r",
            len(candidates),
            len(fresh_candidates),
            topic,
        )

        for candidate in fresh_candidates:
            if stored >= remaining_cap:
                break
            if _score_and_store_candidate(candidate):
                stored += 1
                logger.info(
                    "  Stored discovery item %d/%d: %s",
                    stored,
                    remaining_cap,
                    candidate["title"][:60],
                )

    logger.info("Discovery complete: stored %d new items", stored)
    return stored
