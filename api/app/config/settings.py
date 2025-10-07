from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    openai_api_key: Optional[str] = None
    openai_project: Optional[str] = None
    openai_base_url: Optional[str] = None

    # Legacy single model (deprecated - use role-specific models below)
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.1
    openai_max_output_tokens: int = 4096  # Increased from 1024 to handle multiple claims extraction
    openai_max_turns: int = 6
    openai_tracing_enabled: bool = True

    # Role-specific models (preferred)
    openai_extractor_model: str = "gpt-4o"  # Options: gpt-4o, o3-mini
    openai_planner_model: str = "o3-mini"   # Options: o3-mini, gpt-5

    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_bucket_papers: str = "papers"

    allow_missing_supabase: bool = False

    tool_cap_file_search_per_run: int = 10
    tool_cap_web_search_per_run: int = 5
    tool_cap_code_interpreter_seconds: int = 60

    p2n_dev_user_id: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
