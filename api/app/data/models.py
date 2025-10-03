from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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
    created_by: Optional[str] = None
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



class PlanCreate(BaseModel):
    id: str
    paper_id: str
    version: str
    plan_json: dict[str, Any]
    env_hash: Optional[str] = None
    compute_budget_minutes: Optional[int] = None
    status: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "extra": "ignore",
    }


class PlanRecord(PlanCreate):
    model_config = {
        "extra": "ignore",
    }


class RunCreate(BaseModel):
    id: str
    plan_id: str
    status: str
    env_hash: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {
        "extra": "ignore",
    }


class RunRecord(RunCreate):
    model_config = {
        "extra": "ignore",
    }


class RunEventCreate(BaseModel):
    id: str
    run_id: str
    ts: datetime
    type: str
    payload: dict[str, Any]

    model_config = {
        "extra": "ignore",
    }

__all__ = ["PaperCreate", "PaperRecord", "PlanCreate", "PlanRecord", "RunCreate", "RunRecord", "RunEventCreate", "StorageArtifact"]



