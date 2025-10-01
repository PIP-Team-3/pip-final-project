from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config.llm import agent_defaults, get_client, traced_run


@dataclass(slots=True)
class HelloAgentResult:
    message: str


def run_hello_agent(prompt: Optional[str] = None) -> HelloAgentResult:
    """Execute a demo call against the OpenAI Agents SDK.

    A trace is recorded automatically when `OPENAI_TRACING_ENABLED` is true.
    """

    question = prompt or "Share one tip for reproducible machine learning experiments."
    client = get_client()

    with traced_run("hello-agent-cli"):
        response = client.responses.create(
            model=agent_defaults.model,
            input=question,
            max_output_tokens=agent_defaults.max_output_tokens,
            temperature=agent_defaults.temperature,
        )

    text = getattr(response, "output_text", None) or ""
    if not text:
        segments: list[str] = []
        for item in getattr(response, "output", []) or []:  # type: ignore[assignment]
            for block in getattr(item, "content", []) or []:
                value = getattr(block, "text", None)
                if value:
                    segments.append(value)
        text = "\n".join(segments) if segments else "(no response text received)"

    return HelloAgentResult(message=text)


if __name__ == "__main__":
    result = run_hello_agent()
    print(result.message)
