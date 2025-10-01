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

    def insert_paper(self, payload: PaperCreate) -> PaperRecord:
        paper_id = f"paper_{len(self.records) + 1}"
        record = PaperRecord(
            id=paper_id,
            title=payload.title,
            url=payload.url,
            checksum=payload.checksum,
            created_by=payload.created_by,
            storage_path=payload.storage_path,
            vector_store_id=payload.vector_store_id,
            file_name=payload.file_name,
            created_at=datetime.now(UTC),
        )
        self.records[paper_id] = record
        return record

    def get_paper(self, paper_id: str) -> PaperRecord | None:
        return self.records.get(paper_id)


class FakeStorage:
    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:
        return StorageArtifact(bucket="papers", path=key)


class FakeFileSearch:
    def __init__(self) -> None:
        self.vector_store_counter = 0
        self.search_log: list[str] = []

    def create_vector_store(self, name: str) -> str:
        self.vector_store_counter += 1
        return f"vs_{self.vector_store_counter}"

    def add_pdf(self, vector_store_id: str, filename: str, data: bytes) -> str:
        return f"file_{vector_store_id}"

    def search(self, vector_store_id: str, query: str, max_results: int = 3):
        self.search_log.append(query)
        return [{"text": "A cited passage"}]


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
    assert "paper_id" in body
    assert body["vector_store_id"].startswith("vs_")


def test_ingest_rejects_non_pdf():
    client = TestClient(app)
    payload = {"file": ("notes.txt", b"hello", "text/plain")}
    response = client.post("/api/v1/papers/ingest", files=payload)
    assert response.status_code == 415


def test_verify_citations_endpoint():
    client = TestClient(app)
    pdf_payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    ingest = client.post("/api/v1/papers/ingest", files=pdf_payload)
    paper_id = ingest.json()["paper_id"]
    verify = client.get(f"/api/v1/papers/{paper_id}/verify", params={"q": "test"})
    assert verify.status_code == 200
    body = verify.json()
    assert body["results"][0]["text"] == "A cited passage"
