from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:  # pragma: no cover - optional dependency for runtime environments
    from supabase import Client, create_client
except Exception:  # pragma: no cover
    Client = Any  # type: ignore[assignment]

    def create_client(url: str, key: str) -> Any:  # type: ignore[override]
        raise RuntimeError(
            "The 'supabase' package is required to use SupabaseStorage/SupabaseDatabase"
        )

from .models import PaperCreate, PaperRecord, StorageArtifact


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
    """Thin wrapper over Supabase PostgREST endpoint with RLS awareness."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def insert_paper(self, payload: PaperCreate) -> PaperRecord:
        data = payload.model_dump()
        if not data.get("id"):
            raise ValueError("PaperCreate.id is required for schema v0")
        response = (
            self._client.table("papers")
            .insert(data)
            .select("*")
            .execute()
        )
        result = getattr(response, "data", None) or []
        if not result:
            raise RuntimeError("Failed to insert paper record")
        return PaperRecord.model_validate(result[0])

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

    def get_paper_by_title(self, title: str) -> Optional[PaperRecord]:
        response = (
            self._client.table("papers")
            .select("*")
            .eq("title", title)
            .limit(1)
            .execute()
        )
        data = getattr(response, "data", None) or []
        if not data:
            return None
        return PaperRecord.model_validate(data[0])

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
            update_payload["storage_path"] = storage_path
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

    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:
        self._storage.upload(
            path=key,
            file=data,
            options={"contentType": "application/pdf", "upsert": False},
        )
        return StorageArtifact(bucket=self._bucket_name, path=key)

    def create_signed_url(self, key: str, expires_in: int = 3600) -> StorageArtifact:
        response = self._storage.create_signed_url(key, expires_in)
        signed_url = response.get("signedURL") if isinstance(response, dict) else None
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return StorageArtifact(bucket=self._bucket_name, path=key, signed_url=signed_url, expires_at=expires_at)


__all__ = [
    "SupabaseClientFactory",
    "SupabaseDatabase",
    "SupabaseStorage",
]
