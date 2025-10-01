from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from openai import OpenAI

from .settings import get_settings

settings = get_settings()

_client_kwargs: dict[str, Any] = {}
if settings.openai_api_key:
    _client_kwargs["api_key"] = settings.openai_api_key
if settings.openai_project:
    _client_kwargs["project"] = settings.openai_project
if settings.openai_base_url:
    _client_kwargs["base_url"] = settings.openai_base_url

_client: Optional[OpenAI] = None


def _build_client() -> OpenAI:
    kwargs = dict(_client_kwargs)
    if "api_key" not in kwargs:
        kwargs["api_key"] = settings.openai_api_key or "test-api-key"
    return OpenAI(**kwargs)


def get_client() -> OpenAI:
    """Return a shared OpenAI client instance."""

    global _client
    if _client is None:
        _client = _build_client()
    return _client


@dataclass(frozen=True)
class AgentDefaults:
    """Bundled runtime defaults for Responses-compatible agents."""

    model: str
    temperature: float
    max_output_tokens: int
    max_turns: int


agent_defaults = AgentDefaults(
    model=settings.openai_model,
    temperature=settings.openai_temperature,
    max_output_tokens=settings.openai_max_output_tokens,
    max_turns=settings.openai_max_turns,
)


@contextmanager
def traced_run(name: str) -> Iterator[Any]:
    """Context manager that starts an OpenAI trace span when enabled.

    The OpenAI Agents SDK emits spans to the Traces dashboard when tracing is active.
    See https://platform.openai.com/docs/guides/observability/traces for details.
    Disable tracing by setting the `OPENAI_TRACING_ENABLED` environment variable to
    `false` (case-insensitive).
    """

    if not settings.openai_tracing_enabled:
        yield None
        return

    client = get_client()
    traces = getattr(client, "traces", None)
    start_trace = getattr(traces, "start_trace", None)

    if callable(start_trace):
        with start_trace(name=name) as span:  # type: ignore[misc]
            yield span
    else:
        # Fallback to a no-op when the SDK does not yet expose tracing helpers.
        yield None
