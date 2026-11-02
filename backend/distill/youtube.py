"""YouTube access: RSS for new uploads (free), Data API for details (1 unit / 50 videos).

Quota costs (10k/day): videos.list 1, channels.list 1, search.list 100.
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
