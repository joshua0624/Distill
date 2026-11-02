"""Hard rules (every video, before any LLM call) and the classification rules from rules.yaml."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from distill.config import ROOT, Settings

RULES_PATH = ROOT / "config" / "rules.yaml"


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


# --- Classification rules (config/rules.yaml) ---

ORDINALS = {
    "substance": ["low", "medium", "high"],
    "interest_match": ["none", "some", "strong"],
}


def load_llm_rules(path: Path = RULES_PATH) -> list[dict]:
    rules = yaml.safe_load(path.read_text()) or []
    for i, r in enumerate(rules):
        if not ({"hide_if", "show_if", "default"} & r.keys()):
            raise ValueError(f"{path.name} rule {i + 1} needs hide_if, show_if or default")
        r.setdefault("name", f"rule {i + 1}")
    return rules


def _matches(cls: dict, conditions: dict) -> bool:
    for key, want in conditions.items():
        if key == "slop_signals_any":
            if not set(cls.get("slop_signals") or []) & set(want):
                return False
        elif key.endswith("_at_least"):
            field = key.removesuffix("_at_least")
            scale = ORDINALS[field]
            if cls.get(field) not in scale or scale.index(cls[field]) < scale.index(want):
                return False
        else:
            values = want if isinstance(want, list) else [want]
            if cls.get(key) not in values:
                return False
    return True


def decide_llm(cls: dict, rules: list[dict]) -> Decision:
    """First matching rule wins; the reason is `rule:<name>` so the Hidden view can show it."""
    for r in rules:
        if "default" in r:
            return Decision(r["default"] == "show", f"rule:{r['name']}")
        if "hide_if" in r and _matches(cls, r["hide_if"]):
            return Decision(False, f"rule:{r['name']}")
        if "show_if" in r and _matches(cls, r["show_if"]):
            return Decision(True, f"rule:{r['name']}")
    return Decision(True, "rule:no_match")
