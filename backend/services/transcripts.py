"""
YouTube transcript fetcher.

Compatible with youtube-transcript-api >= 1.0 which switched from a
static class API to an instance-based API:
  - Old: YouTubeTranscriptApi.list_transcripts(video_id)
  - New: YouTubeTranscriptApi().list(video_id)

Snippets in v1.x are TranscriptSnippet objects with a .text attribute.
"""
import logging

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
)

logger = logging.getLogger(__name__)

MAX_WORDS = 3000

_api = YouTubeTranscriptApi()


def fetch_transcript(video_id: str) -> str | None:
    """
    Return transcript text truncated to MAX_WORDS, or None if unavailable.
    """
    try:
        transcript_list = _api.list(video_id)

        try:
            transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
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

        words = " ".join(parts).split()
        if not words:
            return None

        if len(words) > MAX_WORDS:
            return " ".join(words[:MAX_WORDS]) + " [transcript truncated]"

        return " ".join(words)

    except (CouldNotRetrieveTranscript, NoTranscriptFound) as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None
    except Exception:
        logger.warning("Transcript fetch failed for %s", video_id, exc_info=True)
        return None
