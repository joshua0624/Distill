"""
YouTube transcript fetcher.

Fetches auto-generated or manual captions for a video, truncates to
~3000 words to stay within the LLM context window, and returns None
gracefully for any failure (private video, disabled captions, etc.).
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

        # Prefer English; fall back to any manually created, then auto-generated
        try:
            transcript = transcript_list.find_transcript(["en"])
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(
                transcript_list._generated_transcripts.keys()
                or transcript_list._manually_created_transcripts.keys()
            )

        snippets = transcript.fetch()
        full_text = " ".join(s.get("text", "") for s in snippets)
        words = full_text.split()

        if len(words) > MAX_WORDS:
            words = words[:MAX_WORDS]
            return " ".join(words) + " [transcript truncated]"

        return " ".join(words) if words else None

    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None
    except Exception:
        logger.debug("Transcript fetch failed for %s", video_id, exc_info=True)
        return None
