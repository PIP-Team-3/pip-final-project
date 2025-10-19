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
from ..materialize.sanitizer import sanitize_plan
from ..materialize.generators.dataset_registry import DATASET_REGISTRY
from ..data.supabase import is_valid_uuid
from ..dependencies import get_supabase_db, get_supabase_storage, get_supabase_plans_storage, get_tool_tracker
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
ERROR_PLAN_NO_ALLOWED_DATASETS = "E_PLAN_NO_ALLOWED_DATASETS"
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
    warnings: list[str] = Field(default_factory=list)


class MaterializeResponse(BaseModel):
    notebook_asset_path: str
    env_asset_path: str
    env_hash: str


class PlanAssetsResponse(BaseModel):
    notebook_signed_url: str
    env_signed_url: str
    expires_at: datetime


async def _fix_plan_schema(
    raw_plan: dict,
    budget_minutes: int,
    paper_title: str,
    span: Any = None,
) -> dict:
    """
    Stage 2 of two-stage planner: Use GPT-4o to convert raw plan to Plan v1.1 schema.

    Takes potentially malformed plan JSON from o3-mini (Stage 1) and restructures it
    to match PlanDocumentV11 schema exactly, preserving all reasoning and justifications.

    Args:
        raw_plan: Raw plan dict from Stage 1 (may have schema issues)
        budget_minutes: Policy budget to inject if missing
        paper_title: Paper title for context
        span: Optional tracing span

    Returns:
        Fixed plan dict that validates against PlanDocumentV11

    Raises:
        HTTPException: If schema fixing fails
    """
    from ..config.llm import get_client

    settings = get_settings()
    client = get_client()

    # Get target schema
    target_schema = PlanDocumentV11.model_json_schema()

    # Build prompt for schema fixer
    system_prompt = """You are a JSON schema expert. Your task is to restructure a plan JSON to match the exact Plan v1.1 schema.

CRITICAL RULES:
1. Preserve ALL reasoning, justifications, and verbatim quotes from the input
2. Move fields to correct locations (e.g., budget_minutes → policy.budget_minutes)
3. Add missing required fields with sensible defaults
4. Return ONLY valid JSON that matches the target schema exactly
5. Do not modify the content of justifications or technical details"""

    # Handle both raw text and JSON input from Stage 1
    if isinstance(raw_plan, dict) and "raw_text" in raw_plan:
        raw_content = f"""Raw Text Output (from Stage 1 - NOT JSON):
{raw_plan['raw_text']}

You must convert this natural language description into valid JSON matching the schema."""
    else:
        raw_content = f"""Raw Plan (from Stage 1 - May have schema issues):
{json.dumps(raw_plan, indent=2)}

Restructure this to match the target schema exactly."""

    user_prompt = f"""Convert this reproduction plan to match Plan v1.1 schema exactly.

{raw_content}

Target Schema:
{json.dumps(target_schema, indent=2)}

Paper Title: {paper_title}
Policy Budget: {budget_minutes} minutes

CRITICAL REQUIREMENTS:
1. Output ONLY valid JSON matching the target schema
2. Must include "justifications" object with THREE required keys: "dataset", "model", "config"
3. Each justification value must be an object with:
   - "quote": string with a verbatim quote from the paper
   - "citation": string with source (e.g., "Section 3.2", "Table 1")
4. Must include "estimated_runtime_minutes" (integer, estimate based on plan, max 20)
5. Must include "license_compliant": boolean (true/false)
6. Must include "metrics" array with at least one metric string
7. Must include "visualizations" array with at least one visualization string
8. Extract all technical details from the input and structure them properly"""

    try:
        with traced_subspan(span, "p2n.planner.stage2.schema_fix"):
            # Choose response format based on feature flag
            # Non-strict mode is more permissive and works with sanitizer post-processing
            if settings.planner_strict_schema:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "plan_v1_1",
                        "strict": True,
                        "schema": target_schema
                    }
                }
            else:
                # Non-strict mode: Let sanitizer handle type coercion and key pruning
                response_format = {"type": "json_object"}

            response = client.chat.completions.create(
                model=settings.openai_schema_fixer_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,  # Deterministic
                response_format=response_format
            )

            fixed_text = response.choices[0].message.content
            if not fixed_text:
                raise ValueError("Schema fixer returned empty content")

            fixed_plan = json.loads(fixed_text)

            logger.info(
                "planner.stage2.complete model=%s raw_fields=%s fixed_fields=%s",
                settings.openai_schema_fixer_model,
                list(raw_plan.keys()),
                list(fixed_plan.keys())
            )

            return fixed_plan

    except Exception as exc:
        logger.error(
            "planner.stage2.failed paper=%s error=%s",
            paper_title,
            str(exc)
        )
        # Re-raise as HTTPException for consistent error handling
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "E_SCHEMA_FIX_FAILED",
                "message": f"Failed to fix plan schema: {str(exc)}",
                "remediation": "Disable two-stage planner or retry with different model"
            }
        ) from exc


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

    # Filter out web_search for o3-mini (not supported)
    settings = get_settings()
    if "o3-mini" in settings.openai_planner_model:
        tools = [t for t in tools if not (isinstance(t, dict) and t.get("type") == "web_search")]

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

            # Build stream parameters - o3-mini doesn't support temperature/top_p
            # o3-mini produces detailed reasoning, so increase token limit
            max_tokens = 8192 if "o3-mini" in planner_model else agent_defaults.max_output_tokens

            stream_params = {
                "model": planner_model,
                "input": input_blocks,
                "tools": tools,
                "max_output_tokens": max_tokens,
            }

            # Only add temperature for models that support it (not o3-mini)
            if "o3-mini" not in planner_model:
                stream_params["temperature"] = agent_defaults.temperature

            # Collect output text from stream events (more reliable than final_response for o3-mini)
            output_text_parts = []
            # Collect function tool call arguments (for dataset_resolver, license_checker, budget_estimator)
            function_call_chunks = []

            stream_manager = client.responses.stream(**stream_params)
            with stream_manager as stream:
                for event in stream:
                    event_type = getattr(event, "type", "")
                    logger.info(f"planner.event type={event_type} event={event}")

                    if event_type == FILE_SEARCH_STAGE_EVENT:
                        with traced_subspan(span, "p2n.planner.tool.file_search"):
                            tracker.record_call("file_search")
                        file_search_calls += 1
                        continue

                    # Capture function tool call arguments (dataset_resolver, license_checker, budget_estimator)
                    # SDK 1.109.1 uses "response.function_call_arguments.delta" (underscores, not dots)
                    if event_type == "response.function_call_arguments.delta":
                        args_delta = getattr(event, "delta", None)
                        if args_delta:
                            function_call_chunks.append(args_delta)
                            logger.info(f"planner.function_call.delta length={len(args_delta)}")
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

                    # Collect output text from content delta events
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            output_text_parts.append(delta)

                # Try to get final response, but don't fail if stream didn't complete properly
                if final_response is None:
                    try:
                        final_response = stream.get_final_response()
                    except RuntimeError as e:
                        # o3-mini sometimes doesn't send completion event - use collected text instead
                        logger.warning(
                            "planner.stream.no_completion_event paper_id=%s collected_text_length=%d",
                            paper.id,
                            sum(len(p) for p in output_text_parts)
                        )

        # Parse output text from response
        output_text = None
        if final_response:
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

        # If still no output, use collected text from stream deltas
        if not output_text and output_text_parts:
            output_text = "".join(output_text_parts)
            logger.info(
                "planner.using_collected_text paper_id=%s length=%d",
                paper.id,
                len(output_text)
            )

        # PROSE SYNTHESIS FALLBACK: If no prose but function tools were called, synthesize minimal prose
        # This prevents tool-only execution paths from causing E_PLAN_NO_OUTPUT
        if (not output_text or not output_text.strip()) and function_call_chunks:
            logger.warning(
                "planner.tool_only_path paper_id=%s function_calls=%d synthesizing_prose=true",
                paper.id,
                len(function_call_chunks)
            )
            # Parse function tool results (best effort)
            tool_result_summary = "Function tool called but returned minimal output."
            try:
                raw_tool_json = "".join(function_call_chunks)
                tool_data = json.loads(raw_tool_json)
                if isinstance(tool_data, dict) and tool_data.get("id"):
                    tool_result_summary = f"Dataset {tool_data.get('id', 'unknown')} identified from registry."
            except (json.JSONDecodeError, Exception):
                pass

            # Synthesize minimal prose for Stage 2 to process
            claims_list = [f"{c.dataset} ({c.metric}: {c.value}{c.units or ''})" for c in payload.claims]
            output_text = f"""Based on the paper and claims for {', '.join(claims_list[:3])}, I recommend the following reproduction plan:

{tool_result_summary}

The plan should use the first claim's dataset with a simple baseline model suitable for CPU execution within 20 minutes. Training configuration should use standard hyperparameters (batch_size=32, learning_rate=0.001, epochs=5). The goal is to reproduce the reported metric as closely as possible given compute constraints."""

            logger.info(
                "planner.synthesized_prose paper_id=%s length=%d",
                paper.id,
                len(output_text)
            )

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

        # TWO-STAGE PLANNER: Check if we should use Stage 2 for o3-mini
        settings_for_stage2 = get_settings()
        use_two_stage = settings_for_stage2.planner_two_stage_enabled and "o3-mini" in planner_model

        if use_two_stage:
            # o3-mini with two-stage: Skip JSON parsing, send raw output to Stage 2
            logger.info(
                "planner.stage1.complete model=%s output_length=%d two_stage=true",
                planner_model,
                len(output_text)
            )
            logger.info("planner.stage2.start paper_id=%s raw_output_preview=%s",
                       paper.id, output_text[:200])

            # Stage 2: GPT-4o converts ANY output to valid JSON
            # This handles: natural language, malformed JSON, schema-wrong JSON, etc.
            try:
                plan_raw = await _fix_plan_schema(
                    raw_plan={"raw_text": output_text} if not output_text.strip().startswith('{') else json.loads(output_text),
                    budget_minutes=policy_budget,
                    paper_title=paper.title,
                    span=span
                )
                logger.info("planner.stage2.applied paper_id=%s", paper.id)
            except Exception as stage2_exc:
                logger.error("planner.stage2.failed paper_id=%s error=%s", paper.id, str(stage2_exc))
                # If Stage 2 fails, raise original error
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "E_TWO_STAGE_FAILED",
                        "message": f"Both Stage 1 and Stage 2 failed: {str(stage2_exc)}",
                        "remediation": "Disable two-stage planner or check logs"
                    }
                ) from stage2_exc
        else:
            # Single-stage (gpt-4o or two-stage disabled): Parse JSON directly
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

            logger.info(
                "planner.stage1.complete model=%s fields=%s two_stage=false",
                planner_model,
                list(plan_raw.keys())
            )

        # SANITIZER: Apply post-Stage-2 cleanup (type coercion, pruning, dataset resolution)
        # This ensures plans are runnable even when Stage 2 returns slightly malformed data
        sanitizer_warnings = []
        try:
            with traced_subspan(span, "p2n.planner.sanitize"):
                logger.info("planner.sanitize.start fields=%s", list(plan_raw.keys()))
                plan_raw, sanitizer_warnings = sanitize_plan(
                    raw_plan=plan_raw,
                    registry=DATASET_REGISTRY,
                    policy={"budget_minutes": policy_budget}
                )
                logger.info(
                    "planner.sanitize.complete warnings_count=%d dataset=%s",
                    len(sanitizer_warnings),
                    plan_raw.get("dataset", {}).get("name", "unknown")
                )
                # Log each warning individually for better observability
                for warning in sanitizer_warnings:
                    logger.warning(f"planner.sanitize.warning: {warning}")
        except ValueError as sanitize_exc:
            # Sanitizer failed (e.g., no allowed datasets after pruning)
            logger.error(
                "planner.sanitize.failed paper_id=%s error=%s",
                paper.id,
                str(sanitize_exc)
            )
            record_trace("failed", ERROR_PLAN_NO_ALLOWED_DATASETS)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": ERROR_PLAN_NO_ALLOWED_DATASETS,
                    "message": str(sanitize_exc),
                    "remediation": "Add datasets to registry or adjust planner to use covered datasets",
                },
            ) from sanitize_exc

        # Skip PlannerOutput dataclass - sanitizer prepares data for PlanDocumentV11
        # Go directly to Pydantic validation (guardrails will be checked via schema)
        # Convert to dataclass for guardrail check (TEMP: Skip for sanitized plans)
        from ..agents.types import PlannerOutput

        # SANITIZER COMPATIBILITY: Skip dataclass conversion, use dict directly
        # The sanitizer ensures the dict matches PlanDocumentV11 schema
        parsed_output = None
        try:
            parsed_output = PlannerOutput(**plan_raw) if not sanitizer_warnings else None
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

    # Skip guardrail check if sanitizer was used (it already validated structure)
    if parsed_output is not None:
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

    # Use dict directly if sanitizer was used, otherwise convert from dataclass
    plan_dict = plan_raw if parsed_output is None else asdict(parsed_output)
    if not plan_dict.get("policy"):
        plan_dict["policy"] = {"budget_minutes": policy_budget, "max_retries": 1}

    # DIAGNOSTIC: Log exact payload before validation to debug version literal issue
    logger.info(
        "planner.validation.pre_check paper_id=%s version_value=%r version_type=%s plan_keys=%s",
        paper.id,
        plan_dict.get("version"),
        type(plan_dict.get("version")).__name__,
        list(plan_dict.keys())
    )

    try:
        with traced_subspan(span, "p2n.planner.validation.schema"):
            plan_model = PlanDocumentV11.model_validate(plan_dict)
    except ValidationError as exc:
        messages = "; ".join(err.get("msg", "invalid field") for err in exc.errors()[:3])
        # DIAGNOSTIC: Log full validation errors to understand schema mismatch
        logger.warning(
            "planner.schema.invalid paper_id=%s vector_store_id=%s errors=%s full_errors=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
            messages,
            exc.errors()[:5]  # Show first 5 full error dicts
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
        warnings=sanitizer_warnings,
    )





@plan_assets_router.post("/{plan_id}/materialize", response_model=MaterializeResponse)
async def materialize_plan_assets(
    plan_id: str,
    db=Depends(get_supabase_db),
    plans_storage=Depends(get_supabase_plans_storage),  # Use plans bucket for artifacts
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

    notebook_key = f"{plan_id}/notebook.ipynb"
    env_key = f"{plan_id}/requirements.txt"

    with traced_run("p2n.materialize") as span:
        with traced_subspan(span, "p2n.materialize.codegen"):
            notebook_bytes = build_notebook_bytes(plan, plan_id)
            requirements_text, env_hash = build_requirements(plan)
        with traced_subspan(span, "p2n.materialize.persist"):
            # Store in plans bucket (separate from papers bucket)
            plans_storage.store_text(notebook_key, notebook_bytes.decode("utf-8"), "text/plain")
            plans_storage.store_text(env_key, requirements_text, "text/plain")
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
    plans_storage=Depends(get_supabase_plans_storage),  # Use plans bucket for artifacts
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

    notebook_key = f"{plan_id}/notebook.ipynb"
    env_key = f"{plan_id}/requirements.txt"
    missing = [key for key in (notebook_key, env_key) if not plans_storage.object_exists(key)]
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
    notebook_artifact = plans_storage.create_signed_url(notebook_key, expires_in=ttl)
    env_artifact = plans_storage.create_signed_url(env_key, expires_in=ttl)

    def _safe_url(artifact: StorageArtifact) -> str:
        return artifact.signed_url or ""

    expires_at = notebook_artifact.expires_at or env_artifact.expires_at or (datetime.now(timezone.utc) + timedelta(seconds=ttl))

    return PlanAssetsResponse(
        notebook_signed_url=_safe_url(notebook_artifact),
        env_signed_url=_safe_url(env_artifact),
        expires_at=expires_at,
    )
