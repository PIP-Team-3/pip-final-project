from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class PaperCreate(BaseModel):
    id: Optional[str] = Field(None, description="Primary key value; required for schema v0")
    title: str = Field(..., description="Paper title or filename fallback")
    url: Optional[HttpUrl] = Field(None, description="Source URL when provided")
    checksum: str = Field(..., description="SHA256 checksum of the uploaded PDF")
    created_by: str = Field(..., description="User identifier for RLS scoping")
    storage_path: str = Field(..., description="Supabase Storage path for the PDF")
    vector_store_id: Optional[str] = Field(None, description="OpenAI File Search vector store id")
    file_name: Optional[str] = Field(None, description="Original filename if available")


class PaperRecord(PaperCreate):
    id: str
    created_at: datetime


class StorageArtifact(BaseModel):
    bucket: str
    path: str
    signed_url: Optional[str] = None
    expires_at: Optional[datetime] = None


__all__ = ["PaperCreate", "PaperRecord", "StorageArtifact"]
