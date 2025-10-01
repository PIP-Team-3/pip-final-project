from __future__ import annotations

class ToolValidationError(ValueError):
    """Raised when a tool receives invalid input arguments."""

    status_code = 422


class ToolUsagePolicyError(RuntimeError):
    """Raised when a tool exceeds configured policy caps."""

    status_code = 429


__all__ = ["ToolValidationError", "ToolUsagePolicyError"]
