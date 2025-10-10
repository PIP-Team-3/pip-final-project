from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, status

from .agents.tooling import ToolUsageTracker
from .config.doctor import config_snapshot
from .config.llm import get_client
from .config.settings import get_settings
from .data import SupabaseClientFactory, SupabaseDatabase, SupabaseStorage
from .services import FileSearchService


def _raise_env_error(missing_keys: list[str]) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "E_ENV_MISSING",
            "message": "Required environment configuration is missing",
            "missing": missing_keys,
        },
    )


@lru_cache
def _supabase_client_factory() -> SupabaseClientFactory:
    health = config_snapshot()
    if not health.supabase_url_present or not health.supabase_service_role_present:
        _raise_env_error(health.missing_env_keys or ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])

    settings = get_settings()
    return SupabaseClientFactory(settings.supabase_url or "", settings.supabase_service_role_key or "")


@lru_cache
def _supabase_client():
    factory = _supabase_client_factory()
    return factory.build()


@lru_cache
def _supabase_database() -> SupabaseDatabase:
    return SupabaseDatabase(_supabase_client())


@lru_cache
def _supabase_storage() -> SupabaseStorage:
    settings = get_settings()
    return SupabaseStorage(_supabase_client(), settings.supabase_bucket_papers)


@lru_cache
def _supabase_plans_storage() -> SupabaseStorage:
    """Storage instance for plan artifacts (notebooks, requirements, metrics)."""
    settings = get_settings()
    return SupabaseStorage(_supabase_client(), settings.supabase_bucket_plans)


def get_supabase_db() -> SupabaseDatabase:
    return _supabase_database()


def get_supabase_storage() -> SupabaseStorage:
    return _supabase_storage()


def get_supabase_plans_storage() -> SupabaseStorage:
    """Get storage instance for plan artifacts (notebooks, requirements)."""
    return _supabase_plans_storage()


def get_file_search_service() -> FileSearchService:
    return FileSearchService(get_client())


def get_tool_tracker() -> ToolUsageTracker:
    return ToolUsageTracker()


__all__ = [
    "get_file_search_service",
    "get_supabase_db",
    "get_supabase_storage",
    "get_tool_tracker",
]
