from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from uuid import UUID

try:  # pragma: no cover - optional dependency for runtime environments
    from supabase import Client, create_client
except Exception:  # pragma: no cover
    Client = Any  # type: ignore[assignment]

    def create_client(url: str, key: str) -> Any:  # type: ignore[override]
        raise RuntimeError(
            "The 'supabase' package is required to use SupabaseStorage/SupabaseDatabase"
        )

from .models import (
    PaperCreate,
    PaperRecord,
    PlanCreate,
    PlanRecord,
    RunCreate,
    RunEventCreate,
    RunRecord,
    StorageArtifact,
)

logger = logging.getLogger(__name__)


def sanitize_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return a header dict with string-only values, dropping Nones."""

    if not headers:
        return {}
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if value is None:
            continue
        sanitized[key] = str(value)
    return sanitized


def is_valid_uuid(value: Optional[str]) -> bool:
    """Return True when value is a valid RFC4122 UUID string."""

    if not value:
        return False
    try:
        UUID(value)
    except (ValueError, TypeError):
        return False
    return True


class SupabaseClientFactory:
    """Creates Supabase clients while keeping service role usage server-side."""

    def __init__(self, url: str, service_role_key: str) -> None:
        if not url or not service_role_key:
            raise ValueError("Supabase URL and service role key are required")
        self._url = url
        self._service_role_key = service_role_key

    def build(self) -> Client:
        return create_client(self._url, self._service_role_key)


class SupabaseDatabase:
    """Thin wrapper over Supabase PostgREST endpoint."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def insert_paper(self, payload: PaperCreate) -> PaperRecord:
        data = payload.model_dump(mode="json", exclude_none=False)
        created_by = data.get("created_by")
        if not is_valid_uuid(created_by):
            data.pop("created_by", None)
        response = self._client.table("papers").insert(data).execute()
        result = getattr(response, "data", None)
        if isinstance(result, list):
            result = result[0] if result else None
        if not result:
            raise RuntimeError("Failed to insert paper record")
        return PaperRecord.model_validate(result)
    def insert_plan(self, payload: PlanCreate) -> PlanRecord:
        data = payload.model_dump(mode="json", exclude_none=False)
        created_by = data.get("created_by")
        if not is_valid_uuid(created_by):
            data.pop("created_by", None)
        response = self._client.table("plans").insert(data).execute()
        result = getattr(response, "data", None)
        if isinstance(result, list):
            result = result[0] if result else None
        if not result:
            raise RuntimeError("Failed to insert plan record")
        return PlanRecord.model_validate(result)



    def get_paper(self, paper_id: str) -> Optional[PaperRecord]:
        response = (
            self._client.table("papers")
            .select("*")
            .eq("id", paper_id)
            .single()
            .execute()
        )
        data = getattr(response, "data", None)
        if not data:
            return None
        return PaperRecord.model_validate(data)

    def get_paper_by_checksum(self, checksum: str) -> Optional[PaperRecord]:
        response = (
            self._client.table("papers")
            .select("*")
            .eq("pdf_sha256", checksum)
            .limit(1)
            .execute()
        )
        data = getattr(response, "data", None) or []
        if not data:
            return None
        return PaperRecord.model_validate(data[0])


    def get_plan(self, plan_id: str) -> Optional[PlanRecord]:
        try:
            response = (
                self._client.table("plans")
                .select("*")
                .eq("id", plan_id)
                .single()
                .execute()
            )
        except Exception:
            return None
        data = getattr(response, "data", None)
        if not data:
            return None
        return PlanRecord.model_validate(data)

    def set_plan_env_hash(self, plan_id: str, env_hash: str) -> PlanRecord:
        payload = {
            "env_hash": env_hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        response = (
            self._client.table("plans")
            .update(payload)
            .eq("id", plan_id)
            .select("*")
            .single()
            .execute()
        )
        data = getattr(response, "data", None)
        if not data:
            raise RuntimeError("Failed to update plan record with env hash")
        return PlanRecord.model_validate(data)

def insert_run(self, payload: RunCreate) -> RunRecord:
    data = payload.model_dump(mode="json", exclude_none=False)
    response = (
        self._client.table("runs")
        .insert(data)
        .select("*")
        .single()
        .execute()
    )
    record = getattr(response, "data", None)
    if not record:
        raise RuntimeError("Failed to insert run record")
    return RunRecord.model_validate(record)

def update_run(self, run_id: str, *, status: str, finished_at: datetime | None = None, env_hash: str | None = None) -> RunRecord:
    update_payload: dict[str, Any] = {"status": status}
    if finished_at:
        update_payload["finished_at"] = finished_at.isoformat()
    if env_hash:
        update_payload["env_hash"] = env_hash
    response = (
        self._client.table("runs")
        .update(update_payload)
        .eq("id", run_id)
        .select("*")
        .single()
        .execute()
    )
    record = getattr(response, "data", None)
    if not record:
        raise RuntimeError("Failed to update run record")
    return RunRecord.model_validate(record)

def insert_run_event(self, payload: RunEventCreate) -> None:
    data = payload.model_dump(mode="json")
    self._client.table("run_events").insert(data).execute()

def insert_run_series(self, run_id: str, metric: str, step: int, value: float) -> None:
    data = {
        "run_id": run_id,
        "metric": metric,
        "step": step,
        "value": value,
    }
    self._client.table("run_series").insert(data).execute()

    def delete_paper(self, paper_id: str) -> int:
        response = (
            self._client.table("papers")
            .delete()
            .eq("id", paper_id)
            .execute()
        )
        deleted = getattr(response, "count", None)
        if deleted is not None:
            return deleted
        return 1

    def update_paper_vector_store(
        self, paper_id: str, vector_store_id: str, storage_path: Optional[str]
    ) -> PaperRecord:
        update_payload: dict[str, Any] = {"vector_store_id": vector_store_id}
        if storage_path:
            update_payload["pdf_storage_path"] = storage_path
        response = (
            self._client.table("papers")
            .update(update_payload)
            .eq("id", paper_id)
            .select("*")
            .single()
            .execute()
        )
        data = getattr(response, "data", None)
        if not data:
            raise RuntimeError("Unable to update paper vector store metadata")
        return PaperRecord.model_validate(data)


class SupabaseStorage:
    """Uploads artifacts to Supabase Storage and returns signed URLs."""

    def __init__(self, client: Client, bucket: str) -> None:
        self._bucket_name = bucket
        self._storage = client.storage.from_(bucket)

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def store_asset(self, key: str, data: bytes, content_type: str) -> StorageArtifact:
        headers = sanitize_headers({"contentType": content_type})
        self._storage.upload(path=key, file=data, file_options=headers)
        return StorageArtifact(bucket=self._bucket_name, path=key)

    def store_text(self, key: str, text: str, content_type: str = "text/plain") -> StorageArtifact:
        return self.store_asset(key, text.encode("utf-8"), content_type)

    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:
        return self.store_asset(key, data, "application/pdf")

    def create_signed_url(self, key: str, expires_in: int = 3600) -> StorageArtifact:
        response = self._storage.create_signed_url(key, expires_in)
        signed_url = response.get("signedURL") if isinstance(response, dict) else None
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return StorageArtifact(bucket=self._bucket_name, path=key, signed_url=signed_url, expires_at=expires_at)

    def object_exists(self, key: str) -> bool:
        if not key:
            return False
        parts = key.rsplit("/", 1)
        folder = parts[0] if len(parts) > 1 else ""
        filename = parts[-1]
        result = self._storage.list(folder)
        items = result if isinstance(result, list) else result.get("data", [])
        return any(item.get("name") == filename for item in items)


__all__ = [
    "SupabaseClientFactory",
    "SupabaseDatabase",
    "SupabaseStorage",
    "sanitize_headers",
    "is_valid_uuid",
]

