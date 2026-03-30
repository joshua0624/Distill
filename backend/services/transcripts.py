"""
YouTube transcript fetcher.

Fetches auto-generated or manual captions for a video, truncates to
~3000 words to stay within the LLM context window, and returns None
gracefully for any failure (private video, no captions, etc.).

Compatible with youtube-transcript-api >= 1.0 (snippets are objects, not dicts).
"""
import logging

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)

MAX_WORDS = 3000


def fetch_transcript(video_id: str) -> str | None:
    """
    Return the transcript text for a YouTube video, truncated to MAX_WORDS.
    Returns None if no transcript is available or on any error.
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Prefer English; fall back to any available transcript
        try:
            transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            # Take the first available transcript (auto-generated or otherwise)
            transcript = next(iter(transcript_list), None)
            if transcript is None:
                return None

        fetched = transcript.fetch()

        # v1.x: snippets are TranscriptSnippet objects with a .text attribute
        # v0.x: snippets were dicts with a "text" key — handle both defensively
        parts = []
        for snippet in fetched:
            if hasattr(snippet, "text"):
                parts.append(snippet.text)
            elif isinstance(snippet, dict):
                parts.append(snippet.get("text", ""))

        full_text = " ".join(parts)
        words = full_text.split()

        if not words:
            return None

        if len(words) > MAX_WORDS:
            words = words[:MAX_WORDS]
            return " ".join(words) + " [transcript truncated]"

        return " ".join(words)

    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None
    except Exception:
        logger.warning("Transcript fetch failed for %s", video_id, exc_info=True)
        return None
