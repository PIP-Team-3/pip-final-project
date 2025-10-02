from __future__ import annotations

REDACTION_SUFFIX = "***"


def redact_vector_store_id(value: str | None) -> str:
    """Return a consistently redacted vector store identifier for logging."""

    if not value:
        return f"unknown{REDACTION_SUFFIX}"
    prefix = value[:8]
    return f"{prefix}{REDACTION_SUFFIX}"


__all__ = ["redact_vector_store_id", "REDACTION_SUFFIX"]
