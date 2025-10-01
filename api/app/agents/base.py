from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Protocol

try:  # pragma: no cover - fallback for older SDK builds
    from openai.types.responses.response_failed_event import (  # type: ignore[attr-defined]
        OutputGuardrailTripwireTriggered,
    )
except Exception:  # pragma: no cover - SDK compatibility shim
    class OutputGuardrailTripwireTriggered(RuntimeError):
        """Fallback guardrail exception when running against older OpenAI SDK builds."""


class GuardrailCheck(Protocol):
    """Callable signature for guardrail checks."""

    def __call__(self, payload: Any) -> tuple[bool, str | None]:
        ...


@dataclass(frozen=True)
class Guardrail:
    """Encapsulates a guardrail predicate and its associated metadata.

    See https://platform.openai.com/docs/guides/agents/guardrails for background.
    """

    name: str
    description: str
    check: GuardrailCheck

    def enforce(self, payload: Any) -> None:
        ok, message = self.check(payload)
        if ok:
            return
        detail = message or self.description
        raise OutputGuardrailTripwireTriggered(f"{self.name} tripwire triggered: {detail}")


class AgentRole(str, Enum):
    EXTRACTOR = "extractor"
    PLANNER = "planner"
    ENV_SPEC = "env_spec_builder"
    CODEGEN_DESIGN = "codegen_design"
    KID_EXPLAINER = "kid_explainer"


@dataclass(frozen=True)
class AgentDefinition:
    """Structured configuration describing an agent contract."""

    role: AgentRole
    summary: str
    system_prompt: str
    output_type: type
    input_guardrail: Guardrail
    output_guardrail: Guardrail
    hosted_tools: tuple[str, ...] = ()
    function_tools: tuple[str, ...] = ()

    def validate_input(self, payload: Any) -> None:
        self.input_guardrail.enforce(payload)

    def validate_output(self, payload: Any) -> None:
        self.output_guardrail.enforce(payload)


class AgentFactory(Protocol):
    """Callable that produces agent definitions."""

    def __call__(self) -> AgentDefinition:
        ...


class AgentRegistry:
    """Registry mapping roles to lazy factories."""

    def __init__(self) -> None:
        self._registry: dict[AgentRole, AgentFactory] = {}

    def register(self, role: AgentRole, factory: AgentFactory) -> None:
        if role in self._registry:
            raise ValueError(f"Agent role '{role}' already registered")
        self._registry[role] = factory

    def get(self, role: AgentRole | str) -> AgentDefinition:
        key = AgentRole(role)
        try:
            factory = self._registry[key]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Agent role '{role}' is not registered") from exc
        return factory()

    def roles(self) -> Iterable[AgentRole]:
        return tuple(self._registry.keys())


registry = AgentRegistry()
