from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from pydantic import BaseModel, ValidationError

from .errors import ToolValidationError

RegisteredHandler = Callable[..., Any]


@dataclass(slots=True)
class FunctionToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: RegisteredHandler
    openai_tool: Any


class FunctionToolRegistry:
    """Registry of allow-listed function tools.

    Inspired by https://platform.openai.com/docs/guides/agents/tools#function-tools
    """

    def __init__(self) -> None:
        self._tools: Dict[str, FunctionToolSpec] = {}

    def register(self, spec: FunctionToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> FunctionToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Tool '{name}' is not allow-listed") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools.keys())

    def call(self, name: str, payload: dict[str, Any]) -> Any:
        spec = self.get(name)
        try:
            args = spec.args_model.model_validate(payload)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc
        return spec.handler(args)


function_tools = FunctionToolRegistry()


__all__ = ["FunctionToolSpec", "FunctionToolRegistry", "function_tools"]
