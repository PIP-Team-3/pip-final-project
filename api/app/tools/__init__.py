from __future__ import annotations

import importlib

from .errors import ToolUsagePolicyError, ToolValidationError
from .registry import FunctionToolRegistry, FunctionToolSpec, function_tools as _registry_instance

# Ensure tool registrations execute on import.
importlib.import_module(".function_tools", __name__)

# Re-export the registry instance after side-effects complete.
function_tools = _registry_instance

__all__ = [
    "FunctionToolRegistry",
    "FunctionToolSpec",
    "ToolUsagePolicyError",
    "ToolValidationError",
    "function_tools",
]
