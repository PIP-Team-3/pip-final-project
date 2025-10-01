from __future__ import annotations

from typing import Any, List

from app.tools import function_tools

from .base import AgentDefinition, AgentRole
from .tooling import HOSTED_TOOLS


def build_tool_payloads(agent: AgentDefinition) -> List[Any]:
    """Construct the tool payload list for an agent run."""

    payloads: List[Any] = []
    for tool_name in agent.hosted_tools:
        spec = HOSTED_TOOLS.get(tool_name)
        if spec is None:
            raise ValueError(f"Hosted tool '{tool_name}' is not configured")
        if agent.role not in spec.allowed_roles:
            raise ValueError(
                f"Agent role {agent.role.value} is not permitted to use {tool_name}"
            )
        payloads.append({"type": tool_name})

    for tool_name in agent.function_tools:
        spec = function_tools.get(tool_name)
        payloads.append(spec.openai_tool)

    return payloads


__all__ = ["build_tool_payloads"]
