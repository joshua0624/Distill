"""Hard rules: applied to every video before (and instead of) any LLM call."""
import re
from dataclasses import dataclass

from distill.config import Settings


@dataclass
class Decision:
    visible: bool
    reason: str


def decide(video: dict, tier: str, sport_rules: list[dict], s: Settings) -> Decision:
    """Decide a video from its metadata alone.

    `video` needs title, duration_s, is_short, live_status. Mixed and candidate
    videos that pass every hard rule are held as 'pending_llm' — never shown unfiltered.
    """
    if tier == "blocked":
        return Decision(False, "blocked_channel")
    if video.get("is_short"):
        return Decision(False, "short")
    if video.get("live_status") in ("upcoming", "live"):
        return Decision(False, video["live_status"])

    title = (video.get("title") or "").lower()
    if any(k.lower() in title for k in s.blocked_title_keywords):
        return Decision(False, "blocked_keyword")

    duration = video.get("duration_s") or 0
    min_duration = s.min_duration_s
    if sport_rules:
        matched = [r for r in sport_rules
                   if re.search(r["title_pattern"], video.get("title") or "", re.IGNORECASE)]
        if not matched:
            return Decision(False, "sport_rule_miss")
        min_duration = min(r["min_duration_s"] or s.min_duration_s for r in matched)
    if duration < min_duration:
        return Decision(False, "too_short")

    if tier == "trusted":
        return Decision(True, "sport_rule" if sport_rules else "trusted")
    return Decision(False, "pending_llm")
