from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAIError
from pydantic import BaseModel, Field, ValidationError

from ..agents import AgentRole, OutputGuardrailTripwireTriggered, get_agent
from ..agents.runtime import build_tool_payloads
from ..agents.tooling import ToolUsageTracker
from ..config.llm import agent_defaults, get_client, traced_run, traced_subspan
from ..config.settings import get_settings
from ..data.models import PlanCreate, StorageArtifact
from ..materialize.notebook import build_notebook_bytes, build_requirements
from ..data.supabase import is_valid_uuid
from ..dependencies import get_supabase_db, get_supabase_storage, get_tool_tracker
from ..schemas.plan_v1_1 import PlanDocumentV11
from ..tools.errors import ToolUsagePolicyError
from ..utils.redaction import redact_vector_store_id

logger = logging.getLogger(__name__)

FILE_SEARCH_STAGE_EVENT = "response.file_search_call.searching"
COMPLETED_EVENT_TYPE = "response.completed"
FAILED_EVENT_TYPES = {"response.failed", "error"}  # SDK 1.109.1: "error" not "response.error"
POLICY_CAP_CODE = "E_POLICY_CAP_EXCEEDED"
ERROR_PLAN_NOT_READY = "E_PLAN_NOT_READY"
ERROR_PLAN_OPENAI = "E_PLAN_OPENAI_ERROR"
ERROR_PLAN_FAILED = "E_PLAN_RUN_FAILED"
ERROR_PLAN_NO_OUTPUT = "E_PLAN_NO_OUTPUT"
ERROR_PLAN_SCHEMA_INVALID = "E_PLAN_SCHEMA_INVALID"
ERROR_PLAN_GUARDRAIL = "E_PLAN_GUARDRAIL_FAILED"
PLAN_FILE_SEARCH_RESULTS = 8
ERROR_PLAN_NOT_FOUND = "E_PLAN_NOT_FOUND"
ERROR_PLAN_ASSET_MISSING = "E_PLAN_ASSET_MISSING"
DEFAULT_PLAN_STATUS = "draft"
MATERIALIZE_SIGNED_URL_TTL = 120


router = APIRouter(prefix="/api/v1/papers", tags=["plans"])
plan_assets_router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


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


class MaterializeResponse(BaseModel):
    notebook_asset_path: str
    env_asset_path: str
    env_hash: str


class PlanAssetsResponse(BaseModel):
    notebook_signed_url: str
    env_signed_url: str
    expires_at: datetime


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
    tools = list(tool_payloads)

    # Ensure file_search tool exists with max_num_results and vector_store_ids
    # Only add vector_store_ids if we have a valid one (don't pass empty arrays)
    has_file_search = False
    for i, tool in enumerate(tools):
        if isinstance(tool, dict) and tool.get("type") == "file_search":
            file_search_config = {
                "type": "file_search",
                "max_num_results": PLAN_FILE_SEARCH_RESULTS,
            }
            if paper.vector_store_id:
                file_search_config["vector_store_ids"] = [paper.vector_store_id]
            tools[i] = file_search_config
            has_file_search = True
            break

    if not has_file_search:
        file_search_config = {
            "type": "file_search",
            "max_num_results": PLAN_FILE_SEARCH_RESULTS,
        }
        if paper.vector_store_id:
            file_search_config["vector_store_ids"] = [paper.vector_store_id]
        tools.insert(0, file_search_config)

    # Responses API input: List of Message objects
    # Each message MUST have "type": "message" at top level (verified via SDK types)
    policy_budget = min(payload.budget_minutes, 20)

    system_msg = {
        "type": "message",
        "role": "system",
        "content": [
            {"type": "input_text", "text": agent.system_prompt}
        ]
    }

    user_msg = {
        "type": "message",
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
        ]
    }

    input_blocks = [system_msg, user_msg]
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
            planner_settings = get_settings()
            planner_model = planner_settings.openai_planner_model
            stream_manager = client.responses.stream(
                model=planner_model,
                input=input_blocks,
                tools=tools,
                temperature=agent_defaults.temperature,
                max_output_tokens=agent_defaults.max_output_tokens,
            )
            with stream_manager as stream:
                for event in stream:
                    event_type = getattr(event, "type", "")
                    logger.info(f"planner.event type={event_type} event={event}")

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

        # Parse output text from response
        output_text = getattr(final_response, "output_text", None)
        if not output_text:
            # Fallback: assemble from output array
            parts = []
            for item in getattr(final_response, "output", []) or []:
                for block in getattr(item, "content", []) or []:
                    text = getattr(block, "text", None)
                    if text:
                        parts.append(text)
            output_text = "\n".join(parts) if parts else ""

        if not output_text or not output_text.strip():
            logger.warning(
                "planner.run.empty_output paper_id=%s vector_store_id=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
            )
            record_trace("failed", ERROR_PLAN_NO_OUTPUT)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": ERROR_PLAN_NO_OUTPUT,
                    "message": "Planner produced empty output",
                    "remediation": "Retry planning or adjust prompts",
                },
            )

        # Parse JSON
        try:
            plan_raw = json.loads(output_text.strip())
        except json.JSONDecodeError as exc:
            logger.error(
                "planner.run.invalid_json paper_id=%s vector_store_id=%s output=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
                output_text[:200],
            )
            record_trace("failed", ERROR_PLAN_SCHEMA_INVALID)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ERROR_PLAN_SCHEMA_INVALID,
                    "message": f"Planner returned invalid JSON: {exc}",
                    "remediation": "Retry planning or adjust system prompt",
                },
            ) from exc

        # Convert to dataclass for guardrail check
        from ..agents.types import PlannerOutput

        try:
            parsed_output = PlannerOutput(**plan_raw)
        except (TypeError, ValueError) as exc:
            logger.error(
                "planner.run.dataclass_mapping_failed paper_id=%s vector_store_id=%s error=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
                exc,
            )
            record_trace("failed", ERROR_PLAN_SCHEMA_INVALID)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ERROR_PLAN_SCHEMA_INVALID,
                    "message": f"Planner output structure mismatch: {exc}",
                    "remediation": "Verify planner prompt matches expected schema",
                },
            ) from exc

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
        budget_minutes=plan_model.policy.budget_minutes,
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





@plan_assets_router.post("/{plan_id}/materialize", response_model=MaterializeResponse)
async def materialize_plan_assets(
    plan_id: str,
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
):
    plan_record = db.get_plan(plan_id)
    if not plan_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_PLAN_NOT_FOUND,
                "message": "Plan not found",
                "remediation": "Create the plan before materializing assets",
            },
        )
    try:
        plan = PlanDocumentV11.model_validate(plan_record.plan_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ERROR_PLAN_SCHEMA_INVALID,
                "message": "Stored plan payload failed validation",
                "errors": exc.errors()[:3],
            },
        ) from exc

    notebook_key = f"plans/{plan_id}/notebook.ipynb"
    env_key = f"plans/{plan_id}/requirements.txt"

    with traced_run("p2n.materialize") as span:
        with traced_subspan(span, "p2n.materialize.codegen"):
            notebook_bytes = build_notebook_bytes(plan, plan_id)
            requirements_text, env_hash = build_requirements(plan)
        with traced_subspan(span, "p2n.materialize.persist"):
            storage.store_asset(notebook_key, notebook_bytes, "application/x-ipynb+json")
            storage.store_text(env_key, requirements_text, "text/plain")
        db.set_plan_env_hash(plan_id, env_hash)

    logger.info(
        "plan.materialize.complete plan_id=%s notebook=%s env=%s env_hash=%s",
        plan_id,
        notebook_key,
        env_key,
        env_hash[:8] + "***",
    )

    return MaterializeResponse(
        notebook_asset_path=notebook_key,
        env_asset_path=env_key,
        env_hash=env_hash,
    )


@plan_assets_router.get("/{plan_id}/assets", response_model=PlanAssetsResponse)
async def get_plan_assets(
    plan_id: str,
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
):
    plan_record = db.get_plan(plan_id)
    if not plan_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_PLAN_NOT_FOUND,
                "message": "Plan not found",
                "remediation": "Create and materialize the plan before verifying assets",
            },
        )

    notebook_key = f"plans/{plan_id}/notebook.ipynb"
    env_key = f"plans/{plan_id}/requirements.txt"
    missing = [key for key in (notebook_key, env_key) if not storage.object_exists(key)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_PLAN_ASSET_MISSING,
                "message": "Plan assets have not been materialized",
                "missing": missing,
            },
        )

    ttl = MATERIALIZE_SIGNED_URL_TTL
    notebook_artifact = storage.create_signed_url(notebook_key, expires_in=ttl)
    env_artifact = storage.create_signed_url(env_key, expires_in=ttl)

    def _safe_url(artifact: StorageArtifact) -> str:
        return artifact.signed_url or ""

    expires_at = notebook_artifact.expires_at or env_artifact.expires_at or (datetime.now(timezone.utc) + timedelta(seconds=ttl))

    return PlanAssetsResponse(
        notebook_signed_url=_safe_url(notebook_artifact),
        env_signed_url=_safe_url(env_artifact),
        expires_at=expires_at,
    )
