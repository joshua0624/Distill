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
