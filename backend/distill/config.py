"""Settings from config/settings.yaml, with secrets from .env."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    db_path: str = str(ROOT / "data" / "distill.db")
    youtube_api_key: str | None = None
    # Hard rules
    shorts_max_s: int = 180
    min_duration_s: int = 240
    blocked_title_keywords: list[str] = field(default_factory=list)
    # Ingest
    max_video_age_days: int = 14
    # Classification (the API key comes from ANTHROPIC_API_KEY in .env)
    llm_model: str = "claude-haiku-5-5"
    llm_price_input_per_mtok: float = 0.10
    llm_price_output_per_mtok: float = 0.50
    llm_monthly_budget_usd: float = 3.00
    llm_batch_threshold: int = 20
    # Discovery
    discovery_daily_cap: int = 10
    discovery_max_age_days: int = 30
    discovery_min_views: int = 1000
    discovery_searches_per_run: int = 10
    discovery_search_every_h: float = 8
    discovery_hn_every_h: float = 12
    discovery_hn_min_points: int = 50
    discovery_llm_every_days: float = 7
    discovery_adjacent_channels_per_run: int = 10


def load_settings() -> Settings:
    s = Settings()
    path = ROOT / "config" / "settings.yaml"
    if path.exists():
        for key, value in (yaml.safe_load(path.read_text()) or {}).items():
            if hasattr(s, key):
                setattr(s, key, value)
    s.youtube_api_key = os.getenv("YOUTUBE_API_KEY") or s.youtube_api_key
    s.db_path = os.getenv("DISTILL_DB", s.db_path)
    return s


settings = load_settings()
