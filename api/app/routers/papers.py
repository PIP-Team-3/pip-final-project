from __future__ import annotations

import hashlib
import json
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

MAX_PAPER_BYTES = 15 * 1024 * 1024  # 15 MiB limit for uploads

router = APIRouter(prefix="/api/v1/papers", tags=["papers"])


class IngestResponse(BaseModel):
    paper_id: str
    vector_store_id: str
    storage_path: str


class VerifyResponse(BaseModel):
    paper_id: str
    query: str
    results: list[dict[str, str]]


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
    return hashlib.sha256(data).hexdigest()


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
    storage_key = f"{checksum}/{filename}"

    try:
        artifact = storage.store_pdf(storage_key, data)
    except Exception as exc:  # pragma: no cover - network call
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "E_STORAGE_UPLOAD_FAILED",
                "message": "Failed to persist PDF to storage",
                "remediation": "Retry later or verify Supabase configuration",
            },
        ) from exc

    try:
        vector_store_id = file_search.create_vector_store(name=title or filename)
        file_search.add_pdf(vector_store_id, filename=filename, data=data)
    except Exception as exc:  # pragma: no cover - network call
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "E_VECTOR_STORE_FAILED",
                "message": "Failed to create File Search index",
                "remediation": "Retry after verifying OpenAI credentials",
            },
        ) from exc

    paper = db.insert_paper(
        PaperCreate(
            title=title or filename,
            url=str(url) if url else None,
            checksum=checksum,
            created_by=created_by,
            storage_path=artifact.path,
            vector_store_id=vector_store_id,
            file_name=filename,
        )
    )

    return IngestResponse(
        paper_id=paper.id,
        vector_store_id=vector_store_id,
        storage_path=artifact.path,
    )


@router.get("/{paper_id}/verify", response_model=VerifyResponse)
async def verify_citations(
    paper_id: str,
    q: str,
    db=Depends(get_supabase_db),
    file_search: FileSearchService = Depends(get_file_search_service),
):
    paper = db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    if not paper.vector_store_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paper is not indexed for search",
        )
    results = file_search.search(paper.vector_store_id, query=q, max_results=3)
    formatted = []
    for item in results:
        if isinstance(item, dict):
            text = item.get("text") or ""
        else:
            text = getattr(item, "text", "")
        formatted.append({"text": text, "source": paper.vector_store_id})
    return VerifyResponse(paper_id=paper_id, query=q, results=formatted)


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
