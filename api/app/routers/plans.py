from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAIError
from openai.types.responses import FileSearchTool as ResponsesFileSearchTool
from pydantic import BaseModel, Field, ValidationError

from ..agents import AgentRole, OutputGuardrailTripwireTriggered, get_agent
from ..agents.runtime import build_tool_payloads
from ..agents.tooling import ToolUsageTracker
from ..config.llm import agent_defaults, get_client, traced_run, traced_subspan
from ..config.settings import get_settings
from ..data.models import PlanCreate
from ..data.supabase import is_valid_uuid
from ..dependencies import get_supabase_db, get_tool_tracker
from ..schemas.plan_v1_1 import PlanDocumentV11
from ..tools.errors import ToolUsagePolicyError
from ..utils.redaction import redact_vector_store_id

logger = logging.getLogger(__name__)

FILE_SEARCH_STAGE_EVENT = "response.file_search_call.searching"
COMPLETED_EVENT_TYPE = "response.completed"
FAILED_EVENT_TYPES = {"response.failed", "response.error"}
POLICY_CAP_CODE = "E_POLICY_CAP_EXCEEDED"
ERROR_PLAN_NOT_READY = "E_PLAN_NOT_READY"
ERROR_PLAN_OPENAI = "E_PLAN_OPENAI_ERROR"
ERROR_PLAN_FAILED = "E_PLAN_RUN_FAILED"
ERROR_PLAN_NO_OUTPUT = "E_PLAN_NO_OUTPUT"
ERROR_PLAN_SCHEMA_INVALID = "E_PLAN_SCHEMA_INVALID"
ERROR_PLAN_GUARDRAIL = "E_PLAN_GUARDRAIL_FAILED"
PLAN_FILE_SEARCH_RESULTS = 8
DEFAULT_PLAN_STATUS = "draft"


router = APIRouter(prefix="/api/v1/papers", tags=["plans"])


class PlannerClaim(BaseModel):
    dataset: Optional[str] = None
    split: Optional[str] = None
    metric: Optional[str] = None
    value: Optional[float] = None
    units: Optional[str] = None
    citation: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class PlannerRequest(BaseModel):
    claims: list[PlannerClaim] = Field(..., min_length=1)
    budget_minutes: int = Field(20, ge=1, le=20)


class PlannerResponse(BaseModel):
    plan_id: str
    plan_version: str
    plan_json: PlanDocumentV11


@router.post("/{paper_id}/plan", response_model=PlannerResponse)
async def create_plan(
    paper_id: str,
    payload: PlannerRequest,
    db=Depends(get_supabase_db),
    tracker: ToolUsageTracker = Depends(get_tool_tracker),
):
    paper = db.get_paper(paper_id)
    if not paper or not paper.vector_store_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_PLAN_NOT_READY,
                "message": "Paper is not ready for planning",
                "remediation": "Ingest the paper and ensure extractor has attached a vector store",
            },
        )

    agent = get_agent(AgentRole.PLANNER)
    client = get_client()
    tool_payloads = build_tool_payloads(agent)

    tools: list[Any] = []
    for tool in tool_payloads:
        if isinstance(tool, dict) and tool.get("type") == "file_search":
            fs_tool = ResponsesFileSearchTool(
                type="file_search",
                vector_store_ids=[paper.vector_store_id],
                max_num_results=PLAN_FILE_SEARCH_RESULTS,
            )
            tools.append(fs_tool.model_dump(mode="json"))
        else:
            tools.append(tool)

    attachments = [
        {
            "file_search": {
                "vector_store_ids": [paper.vector_store_id],
                "max_num_results": PLAN_FILE_SEARCH_RESULTS,
            }
        }
    ]

    system_content = {
        "role": "system",
        "content": [{"type": "text", "text": agent.system_prompt}],
    }

    policy_budget = min(payload.budget_minutes, 20)
    user_payload = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "paper": {
                            "id": paper.id,
                            "title": paper.title,
                            "vector_store_id": paper.vector_store_id,
                        },
                        "claims": [claim.model_dump() for claim in payload.claims],
                        "policy": {"budget_minutes": policy_budget},
                    }
                ),
            }
        ],
    }
    file_search_calls = 0
    span = None

    def record_trace(status_label: str, error_code: str | None = None) -> None:
        if span is None:
            return
        setter = getattr(span, "set_attribute", None)
        if callable(setter):
            setter("p2n.plan.file_search.calls", file_search_calls)
            setter("p2n.plan.status", status_label)
            if error_code:
                setter("p2n.error.code", error_code)

    final_response: Any | None = None

    try:
        with traced_run("p2n.planner.run") as traced_span:
            span = traced_span
            stream_manager = client.responses.stream(
                model=agent_defaults.model,
                input=[system_content, user_payload],
                tools=tools,
                attachments=attachments,
                temperature=agent_defaults.temperature,
                max_output_tokens=agent_defaults.max_output_tokens,
                text_format=agent.output_type,
            )
            with stream_manager as stream:
                for event in stream:
                    event_type = getattr(event, "type", "")

                    if event_type == FILE_SEARCH_STAGE_EVENT:
                        with traced_subspan(span, "p2n.planner.tool.file_search"):
                            tracker.record_call("file_search")
                        file_search_calls += 1
                        continue

                    if event_type in FAILED_EVENT_TYPES:
                        error = getattr(event, "error", None)
                        message = getattr(error, "message", None) or "Planner run failed"
                        logger.error(
                            "planner.run.failed paper_id=%s vector_store_id=%s message=%s",
                            paper.id,
                            redact_vector_store_id(paper.vector_store_id),
                            message,
                        )
                        record_trace("failed", ERROR_PLAN_FAILED)
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail={
                                "code": ERROR_PLAN_FAILED,
                                "message": message,
                                "remediation": "Retry planning after resolving the upstream failure",
                            },
                        )

                    if event_type == COMPLETED_EVENT_TYPE:
                        final_response = getattr(event, "response", None)

                if final_response is None:
                    final_response = stream.get_final_response()
    except OpenAIError as exc:
        logger.exception(
            "planner.run.openai_error paper_id=%s vector_store_id=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
        )
        record_trace("failed", ERROR_PLAN_OPENAI)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": ERROR_PLAN_OPENAI,
                "message": "OpenAI API request failed during planning",
                "remediation": "Verify API credentials and retry the planning run",
            },
        ) from exc
    except ToolUsagePolicyError as exc:
        logger.warning(
            "planner.policy.cap_exceeded paper_id=%s vector_store_id=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
        )
        record_trace("policy.cap.exceeded", POLICY_CAP_CODE)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": POLICY_CAP_CODE,
                "message": str(exc),
                "remediation": "Reduce File Search usage or adjust the configured cap",
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception(
            "planner.run.unexpected_error paper_id=%s vector_store_id=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
        )
        record_trace("failed", ERROR_PLAN_FAILED)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": ERROR_PLAN_FAILED,
                "message": "Unexpected error during planning",
                "remediation": "Check server logs for details and retry",
            },
        ) from exc

    if not final_response:
        logger.warning(
            "planner.run.no_output paper_id=%s vector_store_id=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
        )
        record_trace("failed", ERROR_PLAN_NO_OUTPUT)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": ERROR_PLAN_NO_OUTPUT,
                "message": "Planner did not produce any output",
                "remediation": "Retry planning or adjust prompts",
            },
        )

    parsed_output = getattr(final_response, "output_parsed", None)
    if parsed_output is None:
        logger.warning(
            "planner.run.output_unparsed paper_id=%s vector_store_id=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
        )
        record_trace("failed", ERROR_PLAN_NO_OUTPUT)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": ERROR_PLAN_NO_OUTPUT,
                "message": "Planner output was not parseable",
                "remediation": "Ensure planner schema matches agent output",
            },
        )

    try:
        with traced_subspan(span, "p2n.planner.guardrail.enforce"):
            agent.output_guardrail.enforce(parsed_output)
    except OutputGuardrailTripwireTriggered as exc:
        logger.warning(
            "planner.guardrail.failed paper_id=%s vector_store_id=%s reason=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
            exc,
        )
        record_trace("failed", ERROR_PLAN_GUARDRAIL)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": ERROR_PLAN_GUARDRAIL,
                "message": "Planner guardrail rejected the plan",
                "remediation": "Review missing justifications or adjust planner prompts",
            },
        ) from exc

    plan_dict = asdict(parsed_output)
    if not plan_dict.get("policy"):
        plan_dict["policy"] = {"budget_minutes": policy_budget, "max_retries": 1}

    try:
        with traced_subspan(span, "p2n.planner.validation.schema"):
            plan_model = PlanDocumentV11.model_validate(plan_dict)
    except ValidationError as exc:
        messages = "; ".join(err.get("msg", "invalid field") for err in exc.errors()[:3])
        logger.warning(
            "planner.schema.invalid paper_id=%s vector_store_id=%s errors=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
            messages,
        )
        record_trace("failed", ERROR_PLAN_SCHEMA_INVALID)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ERROR_PLAN_SCHEMA_INVALID,
                "message": "Planner output failed schema validation",
                "remediation": "Refine planner prompt or manual review",
                "errors": messages,
            },
        ) from exc

    record_trace("completed")

    plan_id = str(uuid4())
    now = datetime.now(timezone.utc)
    settings = get_settings()
    plan_payload = PlanCreate(
        id=plan_id,
        paper_id=paper.id,
        version=plan_model.version,
        plan_json=plan_model.model_dump(),
        env_hash=None,
        compute_budget_minutes=plan_model.policy.budget_minutes,
        status=DEFAULT_PLAN_STATUS,
        created_by=settings.p2n_dev_user_id if is_valid_uuid(settings.p2n_dev_user_id) else None,
        created_at=now,
        updated_at=now,
    )
    db.insert_plan(plan_payload)

    logger.info(
        "planner.run.complete paper_id=%s vector_store_id=%s plan_id=%s",
        paper.id,
        redact_vector_store_id(paper.vector_store_id),
        plan_id,
    )

    return PlannerResponse(
        plan_id=plan_id,
        plan_version=plan_model.version,
        plan_json=plan_model,
    )



