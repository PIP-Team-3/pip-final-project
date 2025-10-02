from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..config.doctor import ConfigHealth, config_snapshot
from ..data import PaperCreate
from ..dependencies import (
    get_supabase_db,
    get_supabase_storage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/config/doctor", response_model=ConfigHealth)
async def config_doctor() -> ConfigHealth:
    """Return a redacted snapshot of critical environment configuration."""

    return config_snapshot()


class SignedUrlRequest(BaseModel):
    bucket: str = Field(..., description="Supabase Storage bucket name")
    path: str = Field(..., description="Object path within the bucket")
    ttl_seconds: int = Field(300, ge=30, le=3600, description="Expiration in seconds")


class SignedUrlResponse(BaseModel):
    signed_url: str
    expires_at: datetime | None = None


@router.post("/storage/signed-url", response_model=SignedUrlResponse, status_code=status.HTTP_200_OK)
async def create_signed_url(
    payload: SignedUrlRequest = Body(...),
    storage=Depends(get_supabase_storage),
) -> SignedUrlResponse:
    """Mint a short-lived signed URL for manual testing (dev only)."""

    if payload.bucket != storage.bucket_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bucket '{payload.bucket}' is not configured for this environment",
        )
    logger.info("storage.signed_url.request bucket=%s path=%s", payload.bucket, payload.path)
    artifact = storage.create_signed_url(payload.path, expires_in=payload.ttl_seconds)
    if not artifact.signed_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate signed URL",
        )
    return SignedUrlResponse(signed_url=artifact.signed_url, expires_at=artifact.expires_at)


class DbSmokeResponse(BaseModel):
    inserted: int
    read: int
    deleted: int


@router.post("/db/smoke", response_model=DbSmokeResponse, status_code=status.HTTP_200_OK)
async def db_smoke_test(db=Depends(get_supabase_db)) -> DbSmokeResponse:
    """Perform a dev-only papers CRUD smoke test."""

    paper_id = str(uuid4())
    now = datetime.now(timezone.utc)
    title = f"SMOKE-TEST-{now.isoformat()}"
    created = db.insert_paper(
        PaperCreate(
            id=paper_id,
            title=title,
            source_url=None,
            pdf_storage_path=f"papers/dev/smoke/{paper_id}.pdf",
            vector_store_id="vs-smoke",
            pdf_sha256="smoke-checksum",
            status="smoke",
            created_by="dev-smoke",
            is_public=False,
            created_at=now,
            updated_at=now,
        )
    )
    retrieved = db.get_paper(created.id)
    deleted = db.delete_paper(created.id)
    return DbSmokeResponse(
        inserted=1,
        read=1 if retrieved else 0,
        deleted=deleted,
    )
