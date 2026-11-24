"""Settings, read from .env (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# Free on OpenRouter. Any OpenRouter model ID works, e.g. anthropic/claude-sonnet-5.5 (paid).
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_db_url: str | None  # optional: lets the seed script create the tables with psql
    openrouter_api_key: str | None
    openrouter_model: str
    request_date: date | None  # None = today
    data_dir: Path
    cache_dir: Path

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    raw_date = (os.getenv("REQUEST_DATE") or "").strip()
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_db_url=os.getenv("SUPABASE_DB_URL") or None,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        openrouter_model=(os.getenv("OPENROUTER_MODEL") or "").strip() or DEFAULT_MODEL,
        request_date=date.fromisoformat(raw_date) if raw_date else None,
        data_dir=ROOT / "data",
        cache_dir=ROOT / ".cache",
    )


def resolve_request_date(settings: Settings, override: date | None = None) -> date:
    """Query parameter wins, then the REQUEST_DATE setting, then today."""
    return override or settings.request_date or date.today()
