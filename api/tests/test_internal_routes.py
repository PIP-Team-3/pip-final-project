from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from app.data.models import StorageArtifact
from app.main import app


class FakeStorage:
    def __init__(self) -> None:
        self.bucket_name = "papers"
        self.calls: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, expires_in: int = 3600) -> StorageArtifact:
        self.calls.append((path, expires_in))
        return StorageArtifact(
            bucket=self.bucket_name,
            path=path,
            signed_url=f"https://supabase.local/{path}?token=fake",
            expires_at=datetime.now(timezone.utc),
        )


class FakeDb:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def insert_paper(self, payload) -> Any:  # type: ignore[override]
        data = payload.model_dump()
        self._records[data["id"]] = data
        return SimpleNamespace(**data)

    def get_paper(self, paper_id: str) -> Optional[Any]:
        record = self._records.get(paper_id)
        if not record:
            return None
        return SimpleNamespace(**record)

    def delete_paper(self, paper_id: str) -> int:
        if paper_id in self._records:
            del self._records[paper_id]
            return 1
        return 0


@pytest.fixture(autouse=True)
def override_internal_dependencies():
    storage = FakeStorage()
    db = FakeDb()

    from app import dependencies

    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: storage
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: db
    yield storage, db
    app.dependency_overrides.clear()


def test_signed_url_endpoint():
    client = TestClient(app)
    payload = {"bucket": "papers", "path": "dev/test.pdf", "ttl_seconds": 120}
    response = client.post("/internal/storage/signed-url", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["signed_url"].startswith("https://supabase.local/dev/test.pdf")


def test_db_smoke_endpoint():
    client = TestClient(app)
    response = client.post("/internal/db/smoke")
    assert response.status_code == 200
    data = response.json()
    assert data == {"inserted": 1, "read": 1, "deleted": 1}
