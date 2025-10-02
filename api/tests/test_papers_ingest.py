from __future__ import annotations

from datetime import UTC, datetime
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app.agents.tooling import ToolUsageTracker
from app.data import PaperCreate, PaperRecord, StorageArtifact
from app.main import app


class FakeSupabaseDB:
    def __init__(self) -> None:
        self.records: Dict[str, PaperRecord] = {}
        self.by_checksum: Dict[str, PaperRecord] = {}

    def insert_paper(self, payload: PaperCreate) -> PaperRecord:
        record = PaperRecord.model_validate(payload.model_dump())
        self.records[record.id] = record
        self.by_checksum[record.pdf_sha256] = record
        return record

    def get_paper(self, paper_id: str) -> PaperRecord | None:
        return self.records.get(paper_id)

    def get_paper_by_checksum(self, checksum: str) -> PaperRecord | None:
        return self.by_checksum.get(checksum)


class FakeStorage:
    def __init__(self) -> None:
        self.bucket_name = "papers"
        self.objects: set[str] = set()

    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:
        self.objects.add(key)
        return StorageArtifact(bucket=self.bucket_name, path=key)

    def object_exists(self, key: str) -> bool:
        return key in self.objects


class FakeFileSearch:
    def __init__(self) -> None:
        self.vector_stores: set[str] = set()

    def create_vector_store(self, name: str) -> str:
        identifier = f"vs_{len(self.vector_stores) + 1}"
        self.vector_stores.add(identifier)
        return identifier

    def add_pdf(self, vector_store_id: str, filename: str, data: bytes) -> str:
        return f"file_{vector_store_id}"

    def vector_store_exists(self, vector_store_id: str) -> bool:
        return vector_store_id in self.vector_stores


@pytest.fixture(autouse=True)
def override_dependencies():
    fake_db = FakeSupabaseDB()
    fake_storage = FakeStorage()
    fake_search = FakeFileSearch()

    from app import dependencies

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: fake_storage
    app.dependency_overrides[dependencies.get_file_search_service] = lambda: fake_search
    app.dependency_overrides[dependencies.get_tool_tracker] = lambda: ToolUsageTracker()
    yield
    app.dependency_overrides.clear()


def test_ingest_paper_via_upload():
    client = TestClient(app)
    payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    response = client.post("/api/v1/papers/ingest", files=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["vector_store_id"].startswith("vs_")
    assert body["storage_path"].startswith("papers/dev/")


def test_ingest_rejects_non_pdf():
    client = TestClient(app)
    payload = {"file": ("notes.txt", b"hello", "text/plain")}
    response = client.post("/api/v1/papers/ingest", files=payload)
    assert response.status_code == 415


def test_verify_ingest_endpoint():
    client = TestClient(app)
    pdf_payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    ingest = client.post("/api/v1/papers/ingest", files=pdf_payload)
    paper_id = ingest.json()["paper_id"]
    verify = client.get(f"/api/v1/papers/{paper_id}/verify")
    assert verify.status_code == 200
    body = verify.json()
    assert body["storage_path_present"] is True
    assert body["vector_store_present"] is True


def test_ingest_idempotent_returns_same_paper_id():
    client = TestClient(app)
    pdf_payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    first = client.post("/api/v1/papers/ingest", files=pdf_payload)
    second = client.post("/api/v1/papers/ingest", files=pdf_payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["paper_id"] == second.json()["paper_id"]
