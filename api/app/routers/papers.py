from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from openai import OpenAIError, pydantic_function_tool
from pydantic import BaseModel, HttpUrl

from ..agents import AgentRole, OutputGuardrailTripwireTriggered, get_agent
from ..agents.jsonizer import jsonize_or_raise
from ..agents.runtime import build_tool_payloads
from ..agents.schemas import ExtractorOutputModel
from ..agents.tooling import ToolUsageTracker
from ..agents.types import ExtractorOutput, ExtractedClaim, Citation
from ..config.llm import agent_defaults, get_client, traced_run, traced_subspan
from ..data import PaperCreate
from ..config.settings import get_settings
from ..data.supabase import is_valid_uuid
from ..dependencies import (
    get_file_search_service,
    get_supabase_db,
    get_supabase_storage,
    get_tool_tracker,
)
from ..services import FileSearchService
from ..tools.errors import ToolUsagePolicyError
from ..utils.redaction import redact_vector_store_id

logger = logging.getLogger(__name__)

MAX_PAPER_BYTES = 15 * 1024 * 1024  # 15 MiB limit for uploads
EXTRACTOR_AGENT_NAME = "extractor"
START_EVENT_TYPE = "response.created"
FILE_SEARCH_STAGE_EVENT = "response.file_search_call.searching"
TOKEN_EVENT_TYPE = "response.output_text.delta"
REASONING_EVENT_PREFIX = "response.reasoning"
COMPLETED_EVENT_TYPE = "response.completed"
FAILED_EVENT_TYPES = {"response.failed", "error"}  # SDK 1.109.1: "error" not "response.error"

ERROR_LOW_CONFIDENCE = "E_EXTRACT_LOW_CONFIDENCE"
ERROR_RUN_FAILED = "E_EXTRACT_RUN_FAILED"
ERROR_NO_OUTPUT = "E_EXTRACT_NO_OUTPUT"
ERROR_OPENAI = "E_EXTRACT_OPENAI_ERROR"
POLICY_CAP_CODE = "E_POLICY_CAP_EXCEEDED"
FILE_SEARCH_MAX_RESULTS = 8

# Function tool for forced structured output (Responses API requirement)
EMIT_TOOL_NAME = "emit_extractor_output"
EMIT_EXTRACTOR_OUTPUT_TOOL = pydantic_function_tool(
    ExtractorOutputModel,
    name=EMIT_TOOL_NAME,
    description="Emit the extractor's final structured results as one JSON object.",
)

router = APIRouter(prefix="/api/v1/papers", tags=["papers"])


class IngestResponse(BaseModel):
    paper_id: str
    vector_store_id: str
    storage_path: str


class VerifyResponse(BaseModel):
    storage_path_present: bool
    vector_store_present: bool


def _require_pdf(file: UploadFile) -> None:
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "E_UNSUPPORTED_MEDIA_TYPE",
                "message": "Only PDF uploads are supported",
                "remediation": "Upload a paper in PDF format",
            },
        )


async def _download_url(url: HttpUrl) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(str(url))
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "E_FETCH_FAILED",
                    "message": "Failed to download the provided URL",
                    "remediation": "Ensure the link is publicly accessible",
                },
            )
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={
                    "code": "E_UNSUPPORTED_MEDIA_TYPE",
                    "message": "Fetched resource is not a PDF",
                    "remediation": "Provide a direct link to a PDF",
                },
            )
        filename = url.path.split("/")[-1] or f"paper-{uuid4().hex}.pdf"
        return response.content, filename


def _compute_checksum(data: bytes) -> str:
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def _build_storage_path(timestamp: datetime, paper_id: str) -> str:
    return (
        f"papers/dev/{timestamp.year:04d}/{timestamp.month:02d}/{timestamp.day:02d}/{paper_id}.pdf"
    )


def _sse_event(event_type: str, payload: dict[str, Any]) -> str:
    data = {"agent": EXTRACTOR_AGENT_NAME, **payload}
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_paper(
    file: Optional[UploadFile] = File(None),
    url: Optional[HttpUrl] = None,
    title: Optional[str] = None,
    created_by: Optional[str] = Form(None),
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
    file_search: FileSearchService = Depends(get_file_search_service),
):
    settings = get_settings()
    fallback_created_by: Optional[str] = (
        settings.p2n_dev_user_id if is_valid_uuid(settings.p2n_dev_user_id) else None
    )

    effective_created_by: Optional[str] = None
    if created_by and is_valid_uuid(created_by):
        effective_created_by = created_by
    elif created_by:
        logger.info("ingest.created_by.invalid provided value omitted")

    if not created_by and not effective_created_by:
        effective_created_by = fallback_created_by
    created_by_present = bool(effective_created_by)
    logger.info("ingest.request created_by_present=%s", created_by_present)

    if file:
        _require_pdf(file)
        data = await file.read()
        filename = file.filename or f"paper-{uuid4().hex}.pdf"
    else:
        data, filename = await _download_url(url)  # type: ignore[arg-type]

    if len(data) > MAX_PAPER_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "E_FILE_TOO_LARGE",
                "message": "PDF exceeds 15 MiB upload cap",
                "remediation": "Compress or trim the PDF before uploading",
            },
        )

    checksum = _compute_checksum(data)
    existing = db.get_paper_by_checksum(checksum)
    if existing:
        logger.info(
            "ingest.idempotent paper_id=%s storage_path=%s vector_store_id=%s created_by_present=%s",
            existing.id,
            existing.pdf_storage_path,
            redact_vector_store_id(existing.vector_store_id),
            existing.created_by is not None,
        )
        return IngestResponse(
            paper_id=existing.id,
            vector_store_id=existing.vector_store_id,
            storage_path=existing.pdf_storage_path,
        )

    paper_id = str(uuid4())
    now = datetime.now(timezone.utc)
    storage_path = _build_storage_path(now, paper_id)
    logger.info("ingest.storage.write paper_id=%s path=%s", paper_id, storage_path)
    with traced_run("p2n.ingest.storage.write"):
        storage.store_pdf(storage_path, data)

    vector_store_id: Optional[str] = None
    logger.info("ingest.file_search.index paper_id=%s", paper_id)
    try:
        with traced_run("p2n.ingest.file_search.index"):
            vector_store_id = file_search.create_vector_store(name=f"paper-{paper_id}")
            file_search.add_pdf(vector_store_id, filename=filename, data=data)
    except OpenAIError as exc:
        logger.exception(
            "ingest.file_search.failed paper_id=%s vector_store_id=%s",
            paper_id,
            redact_vector_store_id(vector_store_id),
        )
        cleanup_ok = storage.delete_object(storage_path)
        log_func = logger.info if cleanup_ok else logger.warning
        log_func(
            "ingest.storage.cleanup.%s paper_id=%s path=%s vector_store_id=%s",
            "completed" if cleanup_ok else "not_found",
            paper_id,
            storage_path,
            redact_vector_store_id(vector_store_id),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "E_FILESEARCH_INDEX_FAILED",
                "message": "Failed to index paper into File Search",
                "remediation": "Verify the OpenAI API key has File Search access and retry the ingest",
            },
        ) from exc

    try:
        paper = db.insert_paper(
            PaperCreate(
                id=paper_id,
                title=title or filename,
                source_url=url,
                pdf_storage_path=storage_path,
                vector_store_id=vector_store_id,
                pdf_sha256=checksum,
                status="ready",
                created_by=effective_created_by,
                created_at=now,
                updated_at=now,
            )
        )
    except Exception as exc:
        logger.exception(
            "ingest.db.insert.failed paper_id=%s storage_path=%s vector_store_id=%s created_by_present=%s",
            paper_id,
            storage_path,
            redact_vector_store_id(vector_store_id),
            created_by_present,
        )
        try:
            cleanup_ok = storage.delete_object(storage_path)
        except Exception as cleanup_exc:  # pragma: no cover - defensive logging
            logger.warning(
                "ingest.storage.cleanup.error paper_id=%s path=%s vector_store_id=%s error=%s",
                paper_id,
                storage_path,
                redact_vector_store_id(vector_store_id),
                cleanup_exc,
            )
        else:
            log_func = logger.info if cleanup_ok else logger.warning
            log_func(
                "ingest.storage.cleanup.%s paper_id=%s path=%s vector_store_id=%s",
                "completed" if cleanup_ok else "not_found",
                paper_id,
                storage_path,
                redact_vector_store_id(vector_store_id),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "E_DB_INSERT_FAILED",
                "message": "Failed to persist paper metadata",
                "remediation": "Review Supabase credentials and retry the ingest",
            },
        ) from exc

    logger.info(
        "ingest.completed paper_id=%s storage_path=%s vector_store_id=%s created_by_present=%s",
        paper.id,
        paper.pdf_storage_path,
        redact_vector_store_id(vector_store_id),
        created_by_present,
    )
    return IngestResponse(
        paper_id=paper.id,
        vector_store_id=vector_store_id,
        storage_path=paper.pdf_storage_path,
    )


@router.get("/{paper_id}/verify", response_model=VerifyResponse)
async def verify_ingest(
    paper_id: str,
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
    file_search: FileSearchService = Depends(get_file_search_service),
):
    paper = db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")

    storage_present = storage.object_exists(paper.pdf_storage_path)
    vector_present = file_search.vector_store_exists(paper.vector_store_id)
    return VerifyResponse(
        storage_path_present=storage_present,
        vector_store_present=vector_present,
    )


@router.post("/{paper_id}/extract")
async def run_extractor(
    paper_id: str,
    db=Depends(get_supabase_db),
    tracker: ToolUsageTracker = Depends(get_tool_tracker),
):
    paper = db.get_paper(paper_id)
    if not paper or not paper.vector_store_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not ready for extraction")

    logger.info(
        "extractor.run.start paper_id=%s vector_store_id=%s",
        paper.id,
        redact_vector_store_id(paper.vector_store_id),
    )
    agent = get_agent(AgentRole.EXTRACTOR)
    client = get_client()
    tool_payloads = build_tool_payloads(agent)
    tools = list(tool_payloads)

    # Build tools: file_search + forced function tool for structured output
    # NOTE: API expects vector_store_ids at TOP LEVEL of tool, not nested in file_search
    tools = [
        {
            "type": "file_search",
            "vector_store_ids": [paper.vector_store_id],
            "max_num_results": FILE_SEARCH_MAX_RESULTS,
        },
        EMIT_EXTRACTOR_OUTPUT_TOOL,
    ]

    # Require at least one tool call - model will use File Search first, then emit_extractor_output
    # The explicit workflow in system + user prompts guides the model to call both in sequence
    tool_choice = "required"

    # Responses API input: List of Message objects
    # Each message MUST have "type": "message" at top level (verified via SDK types)
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
                "text": (
                    f"Paper ID: {paper.id}\n"
                    f"Title: {paper.title}\n\n"
                    "IMPORTANT: Follow the workflow in the system prompt exactly:\n"
                    "1. First use File Search to retrieve the paper content\n"
                    "2. Then call emit_extractor_output with your findings\n\n"
                    "Task: Extract quantitative performance claims from the paper.\n\n"
                    "Requirements:\n"
                    "- Each claim includes: dataset_name, split, metric_name, metric_value, units, method_snippet, source_citation, confidence (0..1).\n"
                    "- Cite the paper section/table in `source_citation`.\n"
                    "- Exclude ambiguous statements ('better', 'state of the art') unless quantified.\n"
                    "- Return ONLY JSON that matches the schema. No additional text."
                ),
            }
        ]
    }

    input_blocks = [system_msg, user_msg]

    def event_stream() -> Iterator[str]:
        file_search_calls = 0
        guardrail_status = "pending"
        final_response: Any | None = None
        span: Any | None = None
        args_chunks: list[str] = []  # Collect tool call arguments
        token_buffer: list[str] = []  # Fallback for JSONizer rescue

        def record_trace(status: str, code: Optional[str] = None) -> None:
            if span is None:
                return
            setter = getattr(span, "set_attribute", None)
            if callable(setter):
                setter("p2n.tool.file_search.calls", file_search_calls)
                setter("p2n.guardrail.extractor", status)
                if code:
                    setter("p2n.error.code", code)

        try:
            with traced_run("p2n.extractor.run") as traced_span:
                span = traced_span
                # DEBUG: Log the tools structure
                import sys
                extractor_settings = get_settings()
                extractor_model = extractor_settings.openai_extractor_model
                print(f"DEBUG extractor.tools={tools}", file=sys.stderr)
                print(f"DEBUG extractor.model={extractor_model}", file=sys.stderr)
                # Force tool call (no response_format needed - tool args ARE the JSON)
                stream_manager = client.responses.stream(
                    model=extractor_model,
                    input=input_blocks,
                    tools=tools,
                    tool_choice=tool_choice,
                    temperature=0,  # Deterministic for extraction
                    max_output_tokens=agent_defaults.max_output_tokens,
                )
                with stream_manager as stream:
                    for event in stream:
                        event_type = getattr(event, "type", "")
                        # DEBUG: Log ALL event types to diagnose mismatch
                        print(f"DEBUG EVENT: type={event_type}", file=sys.stderr)

                        if event_type == START_EVENT_TYPE:
                            yield _sse_event("stage_update", {"stage": "extract_start"})
                            continue

                        if event_type == FILE_SEARCH_STAGE_EVENT:
                            with traced_subspan(span, "p2n.extractor.tool.file_search"):
                                try:
                                    tracker.record_call("file_search")
                                except ToolUsagePolicyError as exc:
                                    logger.warning(
                                        "extractor.policy.cap_exceeded paper_id=%s vector_store_id=%s",
                                        paper.id,
                                        redact_vector_store_id(paper.vector_store_id),
                                    )
                                    record_trace("policy.cap.exceeded", POLICY_CAP_CODE)
                                    yield _sse_event(
                                        "error",
                                        {
                                            "code": POLICY_CAP_CODE,
                                            "message": str(exc),
                                            "remediation": "Reduce File Search usage or adjust the configured cap",
                                        },
                                    )
                                    return
                                file_search_calls += 1
                            yield _sse_event("stage_update", {"stage": "file_search_call"})
                            continue

                        # Capture function tool call arguments (the JSON we want)
                        # SDK 1.109.1 uses "response.function_call_arguments.delta" (underscores, not dots)
                        if event_type == "response.function_call_arguments.delta":
                            # The delta attribute contains the argument chunk (str)
                            args_delta = getattr(event, "delta", None)
                            if args_delta:
                                args_chunks.append(args_delta)
                            continue

                        if event_type == TOKEN_EVENT_TYPE:
                            delta = getattr(event, "delta", "")
                            if delta:
                                token_buffer.append(delta)  # Capture for JSONizer fallback
                                yield _sse_event("token", {"delta": delta, "agent": "extractor"})
                            continue

                        if event_type.startswith(REASONING_EVENT_PREFIX):
                            message = getattr(event, "delta", None) or getattr(event, "text", None)
                            if message:
                                yield _sse_event("log_line", {"message": message})
                            continue

                        if event_type == COMPLETED_EVENT_TYPE:
                            final_response = getattr(event, "response", None)
                            continue

                        if event_type in FAILED_EVENT_TYPES:
                            error = getattr(event, "error", None)
                            message = getattr(error, "message", None) or "Extractor run failed"
                            logger.error(
                                "extractor.run.failed paper_id=%s vector_store_id=%s message=%s",
                                paper.id,
                                redact_vector_store_id(paper.vector_store_id),
                                message,
                            )
                            record_trace("failed", ERROR_RUN_FAILED)
                            yield _sse_event(
                                "error",
                                {
                                    "code": ERROR_RUN_FAILED,
                                    "message": message,
                                    "remediation": "Retry extraction after resolving the upstream failure",
                                },
                            )
                            return

                    # Get final response
                    if final_response is None:
                        try:
                            final_response = stream.get_final_response()
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.exception(
                                "extractor.final_response.error paper_id=%s vector_store_id=%s",
                                paper.id,
                                redact_vector_store_id(paper.vector_store_id),
                            )
                            # Continue - we might still have args_chunks
        except OpenAIError as exc:
            logger.exception(
                "extractor.run.openai_error paper_id=%s vector_store_id=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
            )
            record_trace("failed", ERROR_OPENAI)
            yield _sse_event(
                "error",
                {
                    "code": ERROR_OPENAI,
                    "message": "OpenAI API request failed during extraction",
                    "remediation": "Verify API credentials and retry the extraction",
                },
            )
            return
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "extractor.run.unexpected_error paper_id=%s vector_store_id=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
            )
            record_trace("failed", ERROR_RUN_FAILED)
            yield _sse_event(
                "error",
                {
                    "code": ERROR_RUN_FAILED,
                    "message": "Unexpected error during extraction",
                    "remediation": "Check server logs for details and retry",
                },
            )
            return

        # Parse tool call arguments (primary path)
        parsed_output = None
        if args_chunks:
            try:
                # DEBUG: Log the raw JSON
                raw_json = "".join(args_chunks)
                print(f"DEBUG CAPTURED JSON: {raw_json}", file=sys.stderr)
                # Validate with Pydantic first
                validated = ExtractorOutputModel.model_validate_json(raw_json)
                # Convert Pydantic → dataclass (nested Citation structure)
                claims = [
                    ExtractedClaim(
                        dataset_name=c.dataset_name,
                        split=c.split,
                        metric_name=c.metric_name,
                        metric_value=c.metric_value,
                        units=c.units,
                        method_snippet=c.method_snippet,
                        citation=Citation(
                            source_citation=c.citation.source_citation,
                            confidence=c.citation.confidence
                        ),
                    )
                    for c in validated.claims
                ]
                parsed_output = ExtractorOutput(claims=claims)
                logger.info(
                    "extractor.tool_call.success paper_id=%s claims=%d",
                    paper.id,
                    len(parsed_output.claims),
                )
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning(
                    "extractor.tool_call.parse_failed paper_id=%s error=%s",
                    paper.id,
                    str(exc),
                )

        # Fallback: JSONizer rescue (Plan B)
        if parsed_output is None and token_buffer:
            raw_text = "".join(token_buffer)
            try:
                logger.info(
                    "extractor.jsonizer.attempting paper_id=%s text_len=%d",
                    paper.id,
                    len(raw_text),
                )
                repaired_dict = jsonize_or_raise(
                    client=client,
                    raw_text=raw_text,
                    schema=ExtractorOutputModel.model_json_schema(),
                    name="extractor_output",
                    model="gpt-4o-mini",
                )
                # Convert repaired dict → Pydantic → dataclass
                validated = ExtractorOutputModel.model_validate(repaired_dict)
                claims = [
                    ExtractedClaim(
                        dataset_name=c.dataset_name,
                        split=c.split,
                        metric_name=c.metric_name,
                        metric_value=c.metric_value,
                        units=c.units,
                        method_snippet=c.method_snippet,
                        citation=Citation(
                            source_citation=c.citation.source_citation,
                            confidence=c.citation.confidence
                        ),
                    )
                    for c in validated.claims
                ]
                parsed_output = ExtractorOutput(claims=claims)
                logger.info(
                    "extractor.jsonizer.success paper_id=%s claims=%d",
                    paper.id,
                    len(parsed_output.claims),
                )
            except Exception as exc:
                logger.exception(
                    "extractor.jsonizer.failed paper_id=%s",
                    paper.id,
                )

        # Fail-closed: no valid output
        if parsed_output is None:
            logger.error(
                "extractor.no_valid_output paper_id=%s args_chunks=%d tokens=%d",
                paper.id,
                len(args_chunks),
                len(token_buffer),
            )
            record_trace("failed", ERROR_NO_OUTPUT)
            yield _sse_event(
                "error",
                {
                    "agent": "extractor",
                    "code": ERROR_NO_OUTPUT,
                    "message": "Extractor failed to produce structured output; JSONizer repair failed.",
                    "remediation": "Check extractor prompt & schema; try higher-tier model.",
                },
            )
            return

        try:
            with traced_subspan(span, "p2n.extractor.guardrail.enforce"):
                agent.output_guardrail.enforce(parsed_output)
        except OutputGuardrailTripwireTriggered as exc:
            logger.warning(
                "extractor.guardrail.failed paper_id=%s vector_store_id=%s reason=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
                exc,
            )
            record_trace("failed", ERROR_LOW_CONFIDENCE)
            yield _sse_event(
                "error",
                {
                    "code": ERROR_LOW_CONFIDENCE,
                    "message": "Extractor guardrail rejected the claims",
                    "remediation": "Use manual claim editor to supply citations or boost confidence",
                },
            )
            return

        guardrail_status = "passed"
        with traced_subspan(span, "p2n.extractor.validation.output"):
            claims_payload = [
                {
                    "dataset": claim.dataset_name,
                    "split": claim.split,
                    "metric": claim.metric_name,
                    "value": claim.metric_value,
                    "units": claim.units,
                    "citation": claim.citation.source_citation,
                    "confidence": claim.citation.confidence,
                }
                for claim in parsed_output.claims
            ]

        # Save claims to database (replace policy: delete old claims first)
        try:
            from ..data.models import ClaimCreate

            yield _sse_event("stage_update", {"stage": "persist_start", "count": len(parsed_output.claims)})

            # Delete existing claims for this paper (replace policy)
            deleted_count = db.delete_claims_by_paper(paper.id)
            if deleted_count > 0:
                logger.info(
                    "extractor.claims.deleted paper_id=%s count=%d",
                    paper.id,
                    deleted_count,
                )

            # Insert new claims
            claim_records = [
                ClaimCreate(
                    paper_id=paper.id,
                    dataset_name=claim.dataset_name,
                    split=claim.split,
                    metric_name=claim.metric_name,
                    metric_value=claim.metric_value,
                    units=claim.units,
                    method_snippet=claim.method_snippet,
                    source_citation=claim.citation.source_citation,
                    confidence=claim.citation.confidence,
                    created_by=None,  # TODO: get from context when auth is implemented,
                    created_at=datetime.now(timezone.utc),
                )
                for claim in parsed_output.claims
            ]
            inserted_claims = db.insert_claims(claim_records)
            logger.info(
                "extractor.claims.saved paper_id=%s count=%d",
                paper.id,
                len(inserted_claims),
            )

            yield _sse_event("stage_update", {"stage": "persist_done", "count": len(inserted_claims)})
        except Exception as exc:
            logger.exception(
                "extractor.claims.save_failed paper_id=%s error=%s",
                paper.id,
                str(exc),
            )
            # Continue - claims were extracted successfully even if save failed
            yield _sse_event("log_line", {"message": f"Warning: Claims extracted but failed to save to database: {str(exc)}"})

        logger.info(
            "extractor.run.complete paper_id=%s vector_store_id=%s claims=%s",
            paper.id,
            redact_vector_store_id(paper.vector_store_id),
            len(claims_payload),
        )
        record_trace(guardrail_status)
        yield _sse_event("stage_update", {"stage": "extract_complete"})
        yield _sse_event("result", {"claims": claims_payload})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{paper_id}/claims")
async def get_paper_claims(
    paper_id: str,
    db=Depends(get_supabase_db),
):
    """
    Get all claims for a paper.

    Returns the claims that were extracted and saved to the database.
    """
    claims = db.get_claims_by_paper(paper_id)
    return {
        "paper_id": paper_id,
        "claims_count": len(claims),
        "claims": [
            {
                "id": claim.id,
                "dataset_name": claim.dataset_name,
                "split": claim.split,
                "metric_name": claim.metric_name,
                "metric_value": claim.metric_value,
                "units": claim.units,
                "source_citation": claim.source_citation,
                "confidence": claim.confidence,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
            for claim in claims
        ],
    }







