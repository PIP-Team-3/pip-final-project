"""
JSONizer: Rescue pass to convert messy/free-form text into strict JSON.

Used as fail-safe when extractor/planner streaming doesn't emit proper tool call.
Requires OpenAI Responses API with json_schema (strict=True) support (SDK 1.109.1+).
"""
from __future__ import annotations

import json
from typing import Any, Dict

from openai import OpenAI


def jsonize_or_raise(
    client: OpenAI,
    raw_text: str,
    schema: Dict[str, Any],
    name: str = "extractor_output",
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """
    Convert free-form text into strict JSON conforming to `schema`.

    Args:
        client: OpenAI client instance
        raw_text: Raw model output text to convert
        schema: JSON Schema dict (Pydantic .model_json_schema())
        name: Schema name for json_schema
        model: Model to use for JSONization (default: gpt-4o-mini)

    Returns:
        Parsed dict conforming to schema

    Raises:
        json.JSONDecodeError: If JSONization fails
        OpenAIError: If API call fails
    """
    # Responses API input: List of Message objects
    # Each message MUST have "type": "message" at top level (verified via SDK types)
    system_msg = {
        "type": "message",
        "role": "system",
        "content": [
            {
                "type": "input_text",
                "text": (
                    "You convert free-form text into a single JSON object that "
                    "matches the provided JSON Schema exactly. Return ONLY the JSON."
                ),
            }
        ]
    }

    user_msg = {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "SCHEMA:"},
            {"type": "input_text", "text": json.dumps(schema, ensure_ascii=False)},
            {"type": "input_text", "text": "\n\nTEXT:"},
            {"type": "input_text", "text": raw_text},
        ]
    }

    resp = client.responses.create(
        model=model,
        input=[system_msg, user_msg],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": name, "schema": schema, "strict": True},
        },
        temperature=0,
    )

    # Prefer parsed output (present with strict json_schema)
    parsed = getattr(resp, "output_parsed", None)
    if parsed is not None:
        return parsed

    # Fallback: parse text manually (rarely needed)
    chunks = []
    for part in getattr(resp, "output", []) or []:
        for c in getattr(part, "content", []) or []:
            if c.get("type") == "output_text":
                chunks.append(c.get("text", ""))
    text = "".join(chunks).strip()
    return json.loads(text)
