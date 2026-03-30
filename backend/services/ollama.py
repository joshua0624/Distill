"""
Ollama LLM integration for content scoring.

Calls the local Ollama REST API to score a content item for relevance,
generate a summary, and flag low-density content. Returns structured
results parsed from the model's JSON output.

Ollama API: POST /api/generate with {"model": ..., "prompt": ..., "format": "json", "stream": false}
"""
import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import TypedDict

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
REQUEST_TIMEOUT = 180  # seconds — generous for slow hardware


class ScoreResult(TypedDict):
    relevance_score: int
    summary: str
    is_low_density: bool


_FALLBACK: ScoreResult = {
    "relevance_score": 50,
    "summary": "",
    "is_low_density": False,
}


def _load_interest_profile() -> str:
    profile_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config",
        "interest_profile.txt",
    )
    if not os.path.exists(profile_path):
        logger.warning(
            "config/interest_profile.txt not found. "
            "Create it with a plain-text description of your interests "
            "to enable personalized scoring. Using generic scoring for now."
        )
        return (
            "Technology, software engineering, science, machine learning, "
            "productivity, and in-depth educational content."
        )
    with open(profile_path) as f:
        return f.read().strip()


def _build_prompt(
    title: str,
    source_name: str,
    item_type: str,
    description: str | None,
    transcript_or_body: str | None,
    interest_profile: str,
) -> str:
    content_type_label = "YouTube video" if item_type == "video" else "Reddit post"

    if transcript_or_body:
        content_section = f"Content:\n{transcript_or_body}"
    elif description:
        content_section = f"Description:\n{description}"
    else:
        content_section = "(Title only — no description or transcript available.)"

    return f"""You are scoring a {content_type_label} for personal relevance. Be accurate — do not default to 0.

USER INTERESTS:
{interest_profile}

CONTENT TO SCORE:
Title: {title}
Source: {source_name}
{content_section}

SCORING RULES:
- Score 80-100: content is directly and explicitly about something named in the user's interest list
- Score 50-79: content is clearly adjacent to a named interest and the user would plausibly enjoy it
- Score 20-49: loosely related, mildly interesting
- Score 0-19: off-topic, unlisted, or explicitly unwanted

HARD RULES — apply these before anything else:
- Games: ONLY games explicitly named in the interest list score above 20. Clash of Clans, Apex Legends, Counter-Strike, Minecraft, Hypixel, and any other game NOT named in the list scores 0-15, no matter how interesting the content is.
- Sports: ONLY the specific teams/sports named in the interest list score above 20. Other teams and other sports score 0-15.
- Do NOT infer broad categories. "The user likes VALORANT" does NOT mean they like all FPS games or all competitive games.
- Do NOT reward content just because the transcript discusses strategy, skill, or mechanics — that applies to every game and is not a match signal.
- is_low_density is true ONLY for: pure reaction clips, highlight reels with no analysis, or obvious clip-padding. Game guides, analysis, and commentary are NOT low density.

Respond with JSON only, no explanation:
{{"relevance_score": <integer 0-100>, "summary": "<2-3 sentences about what this content covers>", "is_low_density": <true or false>}}"""


def _call_ollama(prompt: str) -> str:
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.3},
        }
    ).encode()

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        body = json.loads(resp.read())
    return body.get("response", "")


def _parse_response(raw: str) -> ScoreResult:
    """Parse JSON from model output; extract embedded JSON if needed."""
    raw = raw.strip()

    # Try direct parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Extract first {...} block from the response
        match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not match:
            logger.warning("Could not find JSON in model response: %r", raw[:200])
            return _FALLBACK
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("Failed to parse extracted JSON from: %r", raw[:200])
            return _FALLBACK

    score = data.get("relevance_score")
    summary = data.get("summary", "")
    low_density = data.get("is_low_density", False)

    # Validate and coerce
    if not isinstance(score, int):
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 50

    score = max(0, min(100, score))

    if not isinstance(summary, str):
        summary = str(summary)

    return {
        "relevance_score": score,
        "summary": summary.strip(),
        "is_low_density": bool(low_density),
    }


def score_item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    source_name: str,
    description: str | None,
    transcript_or_body: str | None,
) -> ScoreResult:
    """
    Score a single content item. Returns a ScoreResult dict.
    On any Ollama error, logs and returns the fallback (score=50).
    """
    interest_profile = _load_interest_profile()
    prompt = _build_prompt(
        title=title,
        source_name=source_name,
        item_type=item_type,
        description=description,
        transcript_or_body=transcript_or_body,
        interest_profile=interest_profile,
    )

    try:
        raw = _call_ollama(prompt)
    except urllib.error.URLError as e:
        logger.error("Ollama unreachable at %s: %s", OLLAMA_HOST, e)
        raise
    except TimeoutError:
        logger.error("Ollama timed out scoring item %s", item_id)
        raise

    return _parse_response(raw)
