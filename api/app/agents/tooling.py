from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict

from app.config.settings import get_settings
from app.tools.errors import ToolUsagePolicyError

from .base import AgentRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HostedToolSpec:
    name: str
    description: str
    docs_url: str
    max_calls: int | None
    max_duration_seconds: float | None
    allowed_roles: tuple[AgentRole, ...]


def _build_hosted_tools() -> Dict[str, HostedToolSpec]:
    settings = get_settings()
    return {
        "file_search": HostedToolSpec(
            name="file_search",
            description="Retrieve citations from indexed papers via File Search.",
            docs_url="https://platform.openai.com/docs/guides/tools/file-search",
            max_calls=settings.tool_cap_file_search_per_run,
            max_duration_seconds=None,
            allowed_roles=(AgentRole.EXTRACTOR, AgentRole.PLANNER),
        ),
        "web_search": HostedToolSpec(
            name="web_search",
            description="Perform grounded Web Search lookups for datasets and licenses.",
            docs_url="https://platform.openai.com/docs/guides/tools/web-search",
            max_calls=settings.tool_cap_web_search_per_run,
            max_duration_seconds=None,
            allowed_roles=(AgentRole.PLANNER,),
        ),
        "code_interpreter": HostedToolSpec(
            name="code_interpreter",
            description="Run bounded preflight code for schema inspection only.",
            docs_url="https://platform.openai.com/docs/guides/tools/code-interpreter",
            max_calls=None,
            max_duration_seconds=float(settings.tool_cap_code_interpreter_seconds),
            allowed_roles=(AgentRole.ENV_SPEC,),
        ),
    }


HOSTED_TOOLS: Dict[str, HostedToolSpec] = _build_hosted_tools()


class ToolUsageTracker:
    """Tracks per-run usage caps for hosted tools."""

    def __init__(self) -> None:
        self._call_counts: Dict[str, int] = {name: 0 for name in HOSTED_TOOLS}
        self._time_budget: Dict[str, float] = {name: 0.0 for name in HOSTED_TOOLS}

    def record_call(self, tool_name: str, seconds: float | None = None) -> None:
        if tool_name not in HOSTED_TOOLS:
            raise ToolUsagePolicyError(f"Tool '{tool_name}' is not configured for usage tracking")

        spec = HOSTED_TOOLS[tool_name]
        self._call_counts[tool_name] += 1
        logger.debug("Tool %s invoked (%d/%s)", tool_name, self._call_counts[tool_name], spec.max_calls)
        if spec.max_calls is not None and self._call_counts[tool_name] > spec.max_calls:
            message = f"{tool_name} exceeded per-run cap of {spec.max_calls} invocations"
            logger.warning(message)
            raise ToolUsagePolicyError(message)

        if seconds:
            self._time_budget[tool_name] += seconds
            logger.debug(
                "Tool %s consumed %ss (%s/%s)",
                tool_name,
                seconds,
                self._time_budget[tool_name],
                spec.max_duration_seconds,
            )
            if (
                spec.max_duration_seconds is not None
                and self._time_budget[tool_name] > spec.max_duration_seconds
            ):
                message = (
                    f"{tool_name} exceeded time budget of {spec.max_duration_seconds:.0f}s"
                )
                logger.warning(message)
                raise ToolUsagePolicyError(message)

    def reset(self) -> None:
        for key in self._call_counts:
            self._call_counts[key] = 0
            self._time_budget[key] = 0.0


__all__ = ["HOSTED_TOOLS", "HostedToolSpec", "ToolUsageTracker"]
