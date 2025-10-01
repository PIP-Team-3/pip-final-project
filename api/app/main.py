from __future__ import annotations

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from .config.doctor import ensure_startup_config
from .config.llm import agent_defaults, get_client, traced_run
from .config.settings import get_settings
from .routers import api_router

ensure_startup_config()

app = FastAPI(title="P2N API", version="0.1.0")
app.include_router(api_router)

settings = get_settings()


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    tracing_enabled: bool = Field(default_factory=lambda: settings.openai_tracing_enabled)


class HelloAgentRequest(BaseModel):
    prompt: str | None = Field(
        default=None,
        description="Optional custom prompt to send to the demo agent.",
    )


class HelloAgentResponse(BaseModel):
    message: str


@app.get("/health", response_model=HealthResponse, tags=["health"], status_code=status.HTTP_200_OK)
async def health() -> HealthResponse:
    """Readiness probe for upstream orchestration."""

    return HealthResponse()


@app.get("/health/live", response_model=HealthResponse, tags=["health"], status_code=status.HTTP_200_OK)
async def liveness() -> HealthResponse:
    """Lightweight liveness probe for container orchestration."""

    return HealthResponse()


@app.post("/debug/hello-agent", response_model=HelloAgentResponse, tags=["debug"], status_code=status.HTTP_200_OK)
async def hello_agent(payload: HelloAgentRequest) -> HelloAgentResponse:
    """Trigger a minimal Agent SDK call to verify connectivity and tracing."""

    prompt = payload.prompt or "Introduce yourself and mention reproducible experiments."
    client = get_client()

    with traced_run("hello-agent-demo"):
        response = client.responses.create(
            model=agent_defaults.model,
            input=prompt,
            max_output_tokens=agent_defaults.max_output_tokens,
            temperature=agent_defaults.temperature,
        )

    message = getattr(response, "output_text", "")
    if not message:
        # Fallback: assemble text manually from the content array when needed.
        parts = []
        for item in getattr(response, "output", []) or []:  # type: ignore[assignment]
            for block in getattr(item, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        message = "\n".join(parts) if parts else "(no response text received)"

    return HelloAgentResponse(message=message)
