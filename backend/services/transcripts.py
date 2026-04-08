"""
YouTube transcript fetcher.

Primary: youtube-transcript-api (fast, no download)
Fallback: yt-dlp subtitle extraction (different request fingerprint, more resilient)

Compatible with youtube-transcript-api >= 1.0 which switched from a
static class API to an instance-based API:
  - Old: YouTubeTranscriptApi.list_transcripts(video_id)
  - New: YouTubeTranscriptApi().list(video_id)

Snippets in v1.x are TranscriptSnippet objects with a .text attribute.

Set YOUTUBE_COOKIE_FILE in .env to a Netscape-format cookie file path to
authenticate requests and reduce throttling. Export from your browser using
the "Get cookies.txt LOCALLY" extension or: yt-dlp --cookies-from-browser chrome
"""
import logging
import os
import re
import tempfile

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
)

logger = logging.getLogger(__name__)

MAX_WORDS = 3000

_cookie_file = os.environ.get("YOUTUBE_COOKIE_FILE")
_api = YouTubeTranscriptApi(cookies=_cookie_file) if _cookie_file else YouTubeTranscriptApi()

if _cookie_file:
    logger.info("Transcript API using cookie file: %s", _cookie_file)


def _words_from_parts(parts: list[str]) -> list[str]:
    return " ".join(parts).split()


def _truncate(words: list[str]) -> str:
    if len(words) > MAX_WORDS:
        return " ".join(words[:MAX_WORDS]) + " [transcript truncated]"
    return " ".join(words)


def _fetch_via_api(video_id: str) -> str | None:
    """Fetch transcript using youtube-transcript-api."""
    transcript_list = _api.list(video_id)

    try:
        transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
    except NoTranscriptFound:
        # No English track — prefer manually created captions over generated
        try:
            transcript = transcript_list.find_manually_created_transcript(
                [t.language_code for t in transcript_list]
            )
        except NoTranscriptFound:
            transcript = next(iter(transcript_list), None)
        if transcript is None:
            return None

    fetched = transcript.fetch()

    parts = []
    for snippet in fetched:
        if hasattr(snippet, "text"):
            parts.append(snippet.text)
        elif isinstance(snippet, dict):
            parts.append(snippet.get("text", ""))

    words = _words_from_parts(parts)
    return _truncate(words) if words else None


def _parse_vtt(vtt_text: str) -> list[str]:
    """Extract plain text lines from a VTT subtitle file."""
    # Strip VTT timestamps (00:00:00.000 --> 00:00:00.000) and cue settings
    lines = vtt_text.splitlines()
    parts = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or re.match(r"[\d:.,\s]+-->", line):
            continue
        # Strip inline tags like <00:00:00.000>, <c>, </c>
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            parts.append(clean)
            seen.add(clean)
    return parts


def _fetch_via_ytdlp(video_id: str) -> str | None:
    """Fetch subtitles using yt-dlp as a fallback."""
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if _cookie_file:
            ydl_opts["cookiefile"] = _cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded vtt file
        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
        if not vtt_files:
            return None

        # Prefer manually created over auto-generated (auto files contain ".en." not ".en-orig.")
        # yt-dlp names manual captions as <id>.en.vtt, auto-generated as <id>.en.vtt too
        # but we'll just take the first one found since we only requested English
        vtt_path = os.path.join(tmpdir, vtt_files[0])
        with open(vtt_path, encoding="utf-8") as f:
            vtt_text = f.read()

    parts = _parse_vtt(vtt_text)
    words = _words_from_parts(parts)
    return _truncate(words) if words else None


def fetch_transcript(video_id: str) -> str | None:
    """
    Return transcript text truncated to MAX_WORDS, or None if unavailable.
    Tries youtube-transcript-api first, falls back to yt-dlp on failure.
    """
    try:
        result = _fetch_via_api(video_id)
        if result:
            return result
        logger.debug("No transcript via API for %s, trying yt-dlp", video_id)
    except (CouldNotRetrieveTranscript, NoTranscriptFound) as e:
        logger.debug("Transcript API failed for %s (%s), trying yt-dlp", video_id, e)
    except Exception:
        logger.warning("Transcript API error for %s, trying yt-dlp", video_id, exc_info=True)

    try:
        result = _fetch_via_ytdlp(video_id)
        if result:
            logger.debug("yt-dlp transcript succeeded for %s", video_id)
        return result
    except Exception:
        logger.warning("yt-dlp transcript failed for %s", video_id, exc_info=True)
        return None
