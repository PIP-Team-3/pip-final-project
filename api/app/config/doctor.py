from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List

import openai

from .settings import get_settings

logger = logging.getLogger(__name__)

_ENV_FIELD_MAP: Dict[str, str] = {
    "supabase_url": "SUPABASE_URL",
    "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
    "supabase_anon_key": "SUPABASE_ANON_KEY",
    "openai_api_key": "OPENAI_API_KEY",
}

_CORE_KEYS: Iterable[str] = ("supabase_url", "supabase_service_role_key", "openai_api_key")


@dataclass(frozen=True)
class ConfigHealth:
    supabase_url_present: bool
    supabase_service_role_present: bool
    supabase_anon_present: bool
    openai_api_key_present: bool
    all_core_present: bool
    missing_env_keys: List[str]
    caps: Dict[str, int]
    responses_mode_enabled: bool
    openai_python_version: str
    models: Dict[str, str]
    tools: Dict[str, bool]


def _tool_status() -> Dict[str, bool]:
    try:
        from app.agents.tooling import HOSTED_TOOLS
    except Exception:  # pragma: no cover - defensive import fallback
        return {"file_search": False, "web_search": False}

    return {
        "file_search": "file_search" in HOSTED_TOOLS,
        "web_search": "web_search" in HOSTED_TOOLS,
    }


def config_snapshot() -> ConfigHealth:
    settings = get_settings()
    presence = {attr: bool(getattr(settings, attr)) for attr in _ENV_FIELD_MAP}
    missing = [
        _ENV_FIELD_MAP[attr]
        for attr in _CORE_KEYS
        if not presence.get(attr, False)
    ]
    caps = {
        "file_search_per_run": settings.tool_cap_file_search_per_run,
        "web_search_per_run": settings.tool_cap_web_search_per_run,
        "code_interpreter_seconds": settings.tool_cap_code_interpreter_seconds,
    }
    tools = _tool_status()
    return ConfigHealth(
        supabase_url_present=presence["supabase_url"],
        supabase_service_role_present=presence["supabase_service_role_key"],
        supabase_anon_present=presence["supabase_anon_key"],
        openai_api_key_present=presence["openai_api_key"],
        all_core_present=not missing,
        missing_env_keys=missing,
        caps=caps,
        responses_mode_enabled=True,
        openai_python_version=getattr(openai, "__version__", "unknown"),
        models={"selected": settings.openai_model},
        tools=tools,
    )


def ensure_startup_config() -> None:
    settings = get_settings()
    health = config_snapshot()
    if health.missing_env_keys:
        message = "Missing required environment variables: " + ", ".join(health.missing_env_keys)
        if settings.allow_missing_supabase:
            logger.warning("Env doctor continuing despite missing keys: %s", ", ".join(health.missing_env_keys))
        else:
            logger.error("Env doctor fatal configuration error: %s", message)
            raise RuntimeError(message)


__all__ = ["ConfigHealth", "config_snapshot", "ensure_startup_config"]
