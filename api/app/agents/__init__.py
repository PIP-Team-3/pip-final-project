from __future__ import annotations

from .base import (
    AgentDefinition,
    AgentRole,
    Guardrail,
    OutputGuardrailTripwireTriggered,
    registry,
)
from . import definitions  # noqa: F401  # ensure agent factories are registered
from .hello import run_hello_agent


def get_agent(role: AgentRole | str) -> AgentDefinition:
    """Return the registered agent definition for the given role."""

    return registry.get(role)


__all__ = [
    "AgentDefinition",
    "AgentRole",
    "Guardrail",
    "OutputGuardrailTripwireTriggered",
    "get_agent",
    "registry",
    "run_hello_agent",
]
