from __future__ import annotations

import re

REDACTION_SUFFIX = "***"


def redact_vector_store_id(value: str | None) -> str:
    """Return a consistently redacted vector store identifier for logging."""

    if not value:
        return f"unknown{REDACTION_SUFFIX}"
    prefix = value[:8]
    return f"{prefix}{REDACTION_SUFFIX}"


def redact_signed_url(url: str | None) -> str:
    """
    Redact query string parameters from signed URLs.

    Preserves the path but removes all query parameters that might contain tokens.
    Example: https://example.com/file.pdf?token=abc123 -> https://example.com/file.pdf?<redacted>
    """
    if not url:
        return f"none{REDACTION_SUFFIX}"

    # Split on query string
    if "?" in url:
        base, _ = url.split("?", 1)
        return f"{base}?<redacted>"

    return url


def redact_api_key(key: str | None) -> str:
    """
    Redact API keys, showing only prefix.

    Example: sk-proj-abc123def456 -> sk-proj-***
    """
    if not key:
        return f"none{REDACTION_SUFFIX}"

    # Look for common API key patterns
    if key.startswith("sk-"):
        parts = key.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}-{REDACTION_SUFFIX}"
        return f"{parts[0]}-{REDACTION_SUFFIX}"

    # Generic: show first 8 chars
    if len(key) > 8:
        return f"{key[:8]}{REDACTION_SUFFIX}"

    return REDACTION_SUFFIX


__all__ = ["redact_vector_store_id", "redact_signed_url", "redact_api_key", "REDACTION_SUFFIX"]
