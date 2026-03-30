"""
YouTube Data API v3 service.

Quota costs (10k/day budget):
  - subscriptions.list: 1 unit / page (50 results)
  - channels.list:      1 unit / 50 channels
  - playlistItems.list: 1 unit / page (50 items)
  - videos.list:        1 unit / 50 videos

Typical run across 100 subscriptions fetching 10 videos each:
  ~2 + 2 + 100 + ~20 = ~124 units. Two fetches/day ≈ 250 units.
"""
import logging
import os
import re

from datetime import datetime, timezone
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.db import db

load_dotenv()
logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def _get_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YOUTUBE_CLIENT_ID"),
        client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def _build_youtube():
    return build("youtube", "v3", credentials=_get_credentials())


def _parse_duration(iso_duration: str) -> int:
    """Parse ISO 8601 duration (e.g. PT5M30S) to total seconds."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def sync_subscriptions() -> list[dict]:
    """
    Fetch the authenticated user's subscribed channels and upsert into
    the channels table. Returns the full list of channel dicts.
    """
    youtube = _build_youtube()
    channels: list[dict] = []
    next_page = None

    while True:
        resp = (
            youtube.subscriptions()
            .list(part="snippet", mine=True, maxResults=50, pageToken=next_page)
            .execute()
        )
        for item in resp.get("items", []):
            snippet = item["snippet"]
            channels.append(
                {
                    "id": snippet["resourceId"]["channelId"],
                    "title": snippet["title"],
                    "thumbnail_url": snippet.get("thumbnails", {})
                    .get("default", {})
                    .get("url"),
                }
            )
        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    # Resolve uploads playlist IDs in batches of 50
    channel_ids = [c["id"] for c in channels]
    uploads_map: dict[str, str] = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        resp = (
            youtube.channels()
            .list(part="contentDetails", id=",".join(batch), maxResults=50)
            .execute()
        )
        for item in resp.get("items", []):
            uploads_map[item["id"]] = item["contentDetails"]["relatedPlaylists"][
                "uploads"
            ]

    for c in channels:
        c["uploads_playlist_id"] = uploads_map.get(c["id"])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db() as conn:
        conn.executemany(
            """INSERT INTO channels (id, title, thumbnail_url, uploads_playlist_id, synced_at)
               VALUES (:id, :title, :thumbnail_url, :uploads_playlist_id, :synced_at)
               ON CONFLICT(id) DO UPDATE SET
                 title               = excluded.title,
                 thumbnail_url       = excluded.thumbnail_url,
                 uploads_playlist_id = excluded.uploads_playlist_id,
                 synced_at           = excluded.synced_at""",
            [{**c, "synced_at": now} for c in channels],
        )

    logger.info("Synced %d subscriptions", len(channels))
    return channels


def _fetch_playlist_video_ids(youtube, playlist_id: str, max_results: int) -> list[str]:
    try:
        resp = (
            youtube.playlistItems()
            .list(part="contentDetails", playlistId=playlist_id, maxResults=max_results)
            .execute()
        )
        return [item["contentDetails"]["videoId"] for item in resp.get("items", [])]
    except HttpError as e:
        if e.status_code == 404:
            logger.debug("Playlist not found (private or deleted): %s", playlist_id)
            return []
        raise


def fetch_videos(video_ids: list[str]) -> list[dict]:
    """
    Fetch snippet + contentDetails for the given video IDs, filter Shorts
    (duration < 60 s), and return a list of dicts ready for DB insertion.
    """
    if not video_ids:
        return []

    youtube = _build_youtube()
    videos: list[dict] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = (
            youtube.videos()
            .list(part="snippet,contentDetails", id=",".join(batch), maxResults=50)
            .execute()
        )
        for item in resp.get("items", []):
            snippet = item["snippet"]
            duration = _parse_duration(item["contentDetails"].get("duration", ""))
            if duration < 60:
                logger.debug("Filtered Short: %s (%ds)", item["id"], duration)
                continue

            videos.append(
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
                }
            )

    return videos


def store_videos(videos: list[dict]) -> int:
    """Insert videos; skip duplicates. Returns count of newly inserted rows."""
    if not videos:
        return 0
    inserted = 0
    with db() as conn:
        for video in videos:
            cur = conn.execute(
                """INSERT OR IGNORE INTO content_items
                   (id, type, title, source_id, source_name, url, thumbnail_url,
                    description, duration, reddit_score, body, published_at, fetched_at)
                   VALUES (:id, :type, :title, :source_id, :source_name, :url,
                           :thumbnail_url, :description, :duration, :reddit_score,
                           :body, :published_at, :fetched_at)""",
                video,
            )
            inserted += cur.rowcount
    return inserted


def fetch_all_channels(max_per_channel: int = 10) -> int:
    """
    Fetch recent videos from every channel stored in the DB.
    Call sync_subscriptions() first to populate the channels table.
    Returns total new videos inserted.
    """
    youtube = _build_youtube()

    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, uploads_playlist_id FROM channels"
        ).fetchall()

    if not rows:
        logger.warning("No channels in DB — run sync_subscriptions first")
        return 0

    all_ids: list[str] = []
    for row in rows:
        playlist_id = row["uploads_playlist_id"]
        if not playlist_id:
            continue
        ids = _fetch_playlist_video_ids(youtube, playlist_id, max_per_channel)
        all_ids.extend(ids)
        logger.debug("Channel %s: %d video IDs", row["title"], len(ids))

    unique_ids = list(dict.fromkeys(all_ids))

    # Skip videos already in the DB
    if unique_ids:
        with db() as conn:
            placeholders = ",".join("?" * len(unique_ids))
            existing = {
                r[0]
                for r in conn.execute(
                    f"SELECT id FROM content_items WHERE id IN ({placeholders})",
                    unique_ids,
                ).fetchall()
            }
        new_ids = [vid for vid in unique_ids if vid not in existing]
    else:
        new_ids = []

    logger.info(
        "Fetching details for %d new videos (%d already in DB)",
        len(new_ids),
        len(unique_ids) - len(new_ids),
    )

    videos = fetch_videos(new_ids)
    count = store_videos(videos)
    logger.info("Stored %d new videos", count)
    return count
