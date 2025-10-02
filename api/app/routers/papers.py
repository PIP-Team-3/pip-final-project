from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from ..agents import AgentRole, get_agent
from ..agents.runtime import build_tool_payloads
from ..agents.tooling import ToolUsageTracker
from ..config.llm import agent_defaults, get_client, traced_run
from ..data import PaperCreate
from ..dependencies import (
    get_file_search_service,
    get_supabase_db,
    get_supabase_storage,
    get_tool_tracker,
)
from ..services import FileSearchService

logger = logging.getLogger(__name__)

MAX_PAPER_BYTES = 15 * 1024 * 1024  # 15 MiB limit for uploads

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


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_paper(
    file: Optional[UploadFile] = File(None),
    url: Optional[HttpUrl] = None,
    title: Optional[str] = None,
    created_by: str = "system",
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
    file_search: FileSearchService = Depends(get_file_search_service),
):
    if not file and not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "E_NO_INPUT",
                "message": "Provide either a PDF upload or a URL",
                "remediation": "Attach a PDF or include a URL parameter",
            },
        )

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
                "remediation": "Upload a smaller file or compress the PDF",
            },
        )

    checksum = _compute_checksum(data)
    existing = db.get_paper_by_checksum(checksum)
    if existing:
        logger.info(
            "ingest.idempotent paper_id=%s storage_path=%s vector_store_id=%s***",
            existing.id,
            existing.pdf_storage_path,
            (existing.vector_store_id or "")[:8],
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

    logger.info("ingest.file_search.index paper_id=%s", paper_id)
    with traced_run("p2n.ingest.file_search.index"):
        vector_store_id = file_search.create_vector_store(name=f"paper-{paper_id}")
        file_search.add_pdf(vector_store_id, filename=filename, data=data)

    paper = db.insert_paper(
        PaperCreate(
            id=paper_id,
            title=title or filename,
            source_url=url,
            pdf_storage_path=storage_path,
            vector_store_id=vector_store_id,
            pdf_sha256=checksum,
            status="ingested",
            created_by=created_by,
            is_public=False,
            created_at=now,
            updated_at=now,
        )
    )

    logger.info(
        "ingest.completed paper_id=%s storage_path=%s vector_store_id=%s***",
        paper.id,
        paper.pdf_storage_path,
        vector_store_id[:8],
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

    agent = get_agent(AgentRole.EXTRACTOR)
    client = get_client()
    tool_payloads = build_tool_payloads(agent)

    attachments = [
        {
            "file_search": {
                "vector_store_ids": [paper.vector_store_id],
            }
        }
    ]

    system_content = {
        "role": "system",
        "content": [{"type": "text", "text": agent.system_prompt}],
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
    }

    def _track_tool(event_type: str) -> None:
        if event_type.startswith("response.file_search"):
            tracker.record_call("file_search")

    def event_stream():
        with traced_run("extractor-run"):
            with client.responses.stream(
                model=agent_defaults.model,
                input=[system_content, user_payload],
                tools=tool_payloads,
                attachments=attachments,
                temperature=agent_defaults.temperature,
                max_output_tokens=agent_defaults.max_output_tokens,
            ) as stream:
                for event in stream:
                    event_type = getattr(event, "type", "message")
                    _track_tool(event_type)
                    yield f"event: {event_type}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
