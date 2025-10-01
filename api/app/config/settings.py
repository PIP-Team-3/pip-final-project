from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    openai_api_key: Optional[str] = None
    openai_project: Optional[str] = None
    openai_base_url: Optional[str] = None

    openai_model: str = "gpt-4.1-mini"
    openai_temperature: float = 0.1
    openai_max_output_tokens: int = 1024
    openai_max_turns: int = 6
    openai_tracing_enabled: bool = True

    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_bucket_papers: str = "papers"

    allow_missing_supabase: bool = False

    tool_cap_file_search_per_run: int = 10
    tool_cap_web_search_per_run: int = 5
    tool_cap_code_interpreter_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
