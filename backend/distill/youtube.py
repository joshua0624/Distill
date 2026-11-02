"""YouTube access: RSS for new uploads (free), Data API for details (1 unit / 50 videos).

Quota costs (10k/day): videos.list 1, channels.list 1, channelSections.list 1, search.list 100.
"""
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator

import httpx

from distill.config import settings

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
DURATION_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
CHANNEL_ID_RE = re.compile(r"\b(UC[A-Za-z0-9_-]{22})\b")
HANDLE_RE = re.compile(r"(?:^|youtube\.com/)@([A-Za-z0-9._-]{3,30})")
USER_RE = re.compile(r"youtube\.com/user/([A-Za-z0-9._-]+)")
VIDEO_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:\S*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def looks_like_link(text: str) -> bool:
    """A link, @handle or channel id, as opposed to a channel name to search for."""
    text = text.strip()
    return bool(re.match(r"(https?://|www\.|youtube\.com|youtu\.be|@)", text) or CHANNEL_ID_RE.fullmatch(text))


class MissingApiKey(RuntimeError):
    pass


def parse_duration(iso: str) -> int:
    """ISO 8601 duration (PT1H2M3S) to seconds. 'P0D' (live/upcoming) is 0."""
    m = DURATION_RE.fullmatch(iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def parse_rss(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for entry in root.findall("a:entry", NS):
        group = entry.find("media:group", NS)
        thumb = group.find("media:thumbnail", NS) if group is not None else None
        desc = group.find("media:description", NS) if group is not None else None
        link = entry.find("a:link[@rel='alternate']", NS)
        out.append({
            # The feed links Shorts as /shorts/<id>, so most are caught without any request.
            "is_short": link is not None and "/shorts/" in link.get("href", ""),
            "id": entry.findtext("yt:videoId", namespaces=NS),
            "channel_id": entry.findtext("yt:channelId", namespaces=NS),
            "title": entry.findtext("a:title", namespaces=NS),
            "published_at": entry.findtext("a:published", namespaces=NS),
            "thumb_url": thumb.get("url") if thumb is not None else None,
            "description": desc.text if desc is not None else None,
        })
    return out


def _chunks(items: list[str], n: int) -> Iterator[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


class YouTube:
    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None):
        self.http = client or httpx.Client(timeout=20, follow_redirects=False)
        self.api_key = api_key or settings.youtube_api_key

    def _api(self, endpoint: str, **params) -> dict:
        if not self.api_key:
            raise MissingApiKey("Set YOUTUBE_API_KEY in .env")
        r = self.http.get(f"{API}/{endpoint}", params={**params, "key": self.api_key})
        r.raise_for_status()
        return r.json()

    def channel_uploads(self, channel_id: str) -> list[dict]:
        r = self.http.get(RSS.format(channel_id))
        r.raise_for_status()
        return parse_rss(r.text)

    def video_details(self, ids: Iterable[str]) -> dict[str, dict]:
        out = {}
        for batch in _chunks(list(ids), 50):
            data = self._api("videos", part="snippet,contentDetails,statistics",
                             id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                sn, cd, st = item["snippet"], item["contentDetails"], item.get("statistics", {})
                out[item["id"]] = {
                    "channel_id": sn.get("channelId"),
                    "channel_title": sn.get("channelTitle"),
                    "title": sn.get("title"),
                    "published_at": sn.get("publishedAt"),
                    "duration_s": parse_duration(cd.get("duration", "")),
                    "live_status": sn.get("liveBroadcastContent", "none"),
                    "description": sn.get("description"),
                    "tags": sn.get("tags", []),
                    "views": int(st["viewCount"]) if "viewCount" in st else None,
                    "likes": int(st["likeCount"]) if "likeCount" in st else None,
                    "thumb_url": (sn.get("thumbnails", {}).get("high") or {}).get("url"),
                }
        return out

    def channel_info(self, ids: Iterable[str]) -> dict[str, dict]:
        out = {}
        for batch in _chunks(list(ids), 50):
            data = self._api("channels", part="snippet", id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                sn = item["snippet"]
                out[item["id"]] = {
                    "title": sn["title"],
                    "handle": sn.get("customUrl"),
                    "thumb_url": (sn.get("thumbnails", {}).get("default") or {}).get("url"),
                }
        return out

    def is_short(self, video_id: str) -> bool:
        """/shorts/<id> serves a Short directly and redirects regular videos to /watch."""
        r = self.http.head(f"https://www.youtube.com/shorts/{video_id}")
        return r.status_code == 200

    def search(self, query: str, published_after: str, max_results: int = 25) -> list[dict]:
        """Most-viewed matching videos since `published_after` (100 quota units). Newest-first
        surfaced minutes-old uploads from tiny channels; duration is filtered later by the hard rules."""
        data = self._api("search", part="snippet", q=query, type="video", order="viewCount",
                         publishedAfter=published_after, maxResults=max_results,
                         relevanceLanguage="en", safeSearch="none")
        return [{
            "id": item["id"]["videoId"],
            "channel_id": item["snippet"]["channelId"],
            "channel_title": item["snippet"]["channelTitle"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
        } for item in data.get("items", []) if item["id"].get("videoId")]

    def channel_by_handle(self, handle: str) -> dict | None:
        data = self._api("channels", part="snippet", forHandle=handle.lstrip("@"))
        items = data.get("items") or []
        if not items:
            return None
        sn = items[0]["snippet"]
        return {"id": items[0]["id"], "title": sn["title"], "handle": sn.get("customUrl"),
                "thumb_url": (sn.get("thumbnails", {}).get("default") or {}).get("url")}

    def featured_channels(self, channel_id: str) -> list[str]:
        """Channels a creator lists on their channel page (channelSections, 1 unit)."""
        data = self._api("channelSections", part="contentDetails", channelId=channel_id)
        out = []
        for sec in data.get("items", []):
            out += (sec.get("contentDetails") or {}).get("channels", [])
        return out

    def resolve_channel(self, text: str) -> dict | None:
        """A channel from a link (channel, video, /user/), an @handle or a channel id, for
        1-2 quota units. Returns None for anything else: names go through search_channels."""
        text = text.strip()
        if m := CHANNEL_ID_RE.search(text):
            channel_id = m.group(1)
        elif m := HANDLE_RE.search(text):
            return self.channel_by_handle(m.group(1))
        elif m := VIDEO_RE.search(text):
            video = self.video_details([m.group(1)]).get(m.group(1))
            if not video:
                return None
            channel_id = video["channel_id"]
        elif m := USER_RE.search(text):
            items = self._api("channels", part="id", forUsername=m.group(1)).get("items") or []
            if not items:
                return None
            channel_id = items[0]["id"]
        else:
            return None
        info = self.channel_info([channel_id]).get(channel_id)
        return {"id": channel_id, **info} if info else None

    def search_channels(self, name: str, n: int = 5) -> list[dict]:
        """Channels matching a name (100 quota units), so I can pick the right one."""
        # Old /c/ custom URLs have no lookup; search their name like any other text.
        name = re.sub(r"^https?://(www\.)?youtube\.com/c/", "", name.strip())
        items = self._api("search", part="snippet", q=name, type="channel", maxResults=n).get("items") or []
        return [{
            "id": item["id"]["channelId"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "thumb_url": (item["snippet"].get("thumbnails", {}).get("default") or {}).get("url"),
        } for item in items]
