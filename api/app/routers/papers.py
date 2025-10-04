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
from openai import OpenAIError
from pydantic import BaseModel, HttpUrl

from ..agents import AgentRole, OutputGuardrailTripwireTriggered, get_agent
from ..agents.runtime import build_tool_payloads
from ..agents.tooling import ToolUsageTracker
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
FAILED_EVENT_TYPES = {"response.failed", "response.error"}

ERROR_LOW_CONFIDENCE = "E_EXTRACT_LOW_CONFIDENCE"
ERROR_RUN_FAILED = "E_EXTRACT_RUN_FAILED"
ERROR_NO_OUTPUT = "E_EXTRACT_NO_OUTPUT"
ERROR_OPENAI = "E_EXTRACT_OPENAI_ERROR"
POLICY_CAP_CODE = "E_POLICY_CAP_EXCEEDED"
FILE_SEARCH_MAX_RESULTS = 8

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
    async with httpx.AsyncClient(timeout=30) as client:
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
                status="ingested",
                created_by=effective_created_by,
                is_public=False,
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

    # Ensure file_search tool exists with max_num_results
    has_file_search = False
    for i, tool in enumerate(tools):
        if isinstance(tool, dict) and tool.get("type") == "file_search":
            tools[i] = {"type": "file_search", "max_num_results": FILE_SEARCH_MAX_RESULTS}
            has_file_search = True
            break

    if not has_file_search:
        tools.insert(0, {"type": "file_search", "max_num_results": FILE_SEARCH_MAX_RESULTS})

    system_content = {
        "role": "system",
        "content": [{"type": "input_text", "text": agent.system_prompt}],
    }
    user_payload = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "paper_id": paper.id,
                        "title": paper.title,
                        "vector_store_id": paper.vector_store_id,
                    }
                ),
            }
        ],
        "attachments": [
            {
                "vector_store_id": paper.vector_store_id,
                "tools": [{"type": "file_search"}],
            }
        ],
    }

    def event_stream() -> Iterator[str]:
        file_search_calls = 0
        guardrail_status = "pending"
        final_response: Any | None = None
        span: Any | None = None

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
                stream_manager = client.responses.stream(
                    model=agent_defaults.model,
                    input=[system_content, user_payload],
                    tools=tools,
                    temperature=agent_defaults.temperature,
                    max_output_tokens=agent_defaults.max_output_tokens,
                    text_format=agent.output_type,
                )
                with stream_manager as stream:
                    for event in stream:
                        event_type = getattr(event, "type", "")

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

                        if event_type == TOKEN_EVENT_TYPE:
                            delta = getattr(event, "delta", "")
                            if delta:
                                yield _sse_event("token", {"delta": delta})
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

                    if final_response is None:
                        try:
                            final_response = stream.get_final_response()
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.exception(
                                "extractor.final_response.error paper_id=%s vector_store_id=%s",
                                paper.id,
                                redact_vector_store_id(paper.vector_store_id),
                            )
                            record_trace("failed", ERROR_NO_OUTPUT)
                            yield _sse_event(
                                "error",
                                {
                                    "code": ERROR_NO_OUTPUT,
                                    "message": "Extractor did not return a structured payload",
                                    "remediation": "Retry extraction or inspect agent configuration",
                                },
                            )
                            return
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

        if not final_response:
            logger.warning(
                "extractor.run.no_output paper_id=%s vector_store_id=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
            )
            record_trace("failed", ERROR_NO_OUTPUT)
            yield _sse_event(
                "error",
                {
                    "code": ERROR_NO_OUTPUT,
                    "message": "Extractor did not produce any claims",
                    "remediation": "Retry extraction or update the paper inputs",
                },
            )
            return

        parsed_output = getattr(final_response, "output_parsed", None)
        if parsed_output is None:
            logger.warning(
                "extractor.run.output_unparsed paper_id=%s vector_store_id=%s",
                paper.id,
                redact_vector_store_id(paper.vector_store_id),
            )
            record_trace("failed", ERROR_NO_OUTPUT)
            yield _sse_event(
                "error",
                {
                    "code": ERROR_NO_OUTPUT,
                    "message": "Extractor output was not parseable",
                    "remediation": "Ensure the extractor schema matches agent output",
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









