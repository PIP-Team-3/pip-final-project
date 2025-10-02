from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class PaperCreate(BaseModel):
    id: str
    title: str
    source_url: Optional[HttpUrl] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pdf_storage_path: str
    vector_store_id: str
    pdf_sha256: str
    status: str
    created_by: str
    is_public: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {
        "extra": "ignore",
    }


class PaperRecord(PaperCreate):
    model_config = {
        "extra": "ignore",
    }


class StorageArtifact(BaseModel):
    bucket: str
    path: str
    signed_url: Optional[str] = None
    expires_at: Optional[datetime] = None


__all__ = ["PaperCreate", "PaperRecord", "StorageArtifact"]
