from __future__ import annotations

from typing import Dict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openai import OpenAIError

from app.agents.tooling import ToolUsageTracker
from app.data import PaperCreate, PaperRecord, StorageArtifact
from app.main import app
import app.routers.papers as papers_router


class FakeSupabaseDB:
    def __init__(self) -> None:
        self.records: Dict[str, PaperRecord] = {}
        self.by_checksum: Dict[str, PaperRecord] = {}
        self.raise_on_insert = False

    def insert_paper(self, payload: PaperCreate) -> PaperRecord:
        if self.raise_on_insert:
            raise RuntimeError("DB insert failed")
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
        self.deleted: list[str] = []

    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:
        self.objects.add(key)
        return StorageArtifact(bucket=self.bucket_name, path=key)

    def delete_object(self, key: str) -> bool:
        self.deleted.append(key)
        self.objects.discard(key)
        return True

    def object_exists(self, key: str) -> bool:
        return key in self.objects


class FakeFileSearch:
    def __init__(self) -> None:
        self.vector_stores: set[str] = set()
        self.fail_create = False
        self.fail_add = False

    def create_vector_store(self, name: str) -> str:
        if self.fail_create:
            raise OpenAIError("vector store failure")
        identifier = f"vs_{len(self.vector_stores) + 1}"
        self.vector_stores.add(identifier)
        return identifier

    def add_pdf(self, vector_store_id: str, filename: str, data: bytes) -> str:
        if self.fail_add:
            raise OpenAIError("add pdf failure")
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

    yield {"db": fake_db, "storage": fake_storage, "search": fake_search}

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


def test_ingest_bad_url_returns_typed_error(monkeypatch):
    class DummyResponse:
        def __init__(self, status_code: int = 404) -> None:
            self.status_code = status_code
            self.headers = {"content-type": "text/html"}
            self.content = b""

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "DummyClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str) -> DummyResponse:
            return DummyResponse()

    monkeypatch.setattr(papers_router.httpx, "AsyncClient", DummyClient)

    client = TestClient(app)
    response = client.post(
        "/api/v1/papers/ingest",
        params={"url": "https://example.com/missing.pdf"},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "E_FETCH_FAILED"
    assert detail["remediation"]


def test_ingest_filesearch_failure_returns_typed_error(override_dependencies):
    override_dependencies["search"].fail_create = True
    client = TestClient(app)
    payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    response = client.post("/api/v1/papers/ingest", files=payload)
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "E_FILESEARCH_INDEX_FAILED"
    assert len(override_dependencies["storage"].deleted) == 1


def test_ingest_database_failure_triggers_cleanup(override_dependencies):
    override_dependencies["db"].raise_on_insert = True
    client = TestClient(app, raise_server_exceptions=False)
    payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    response = client.post("/api/v1/papers/ingest", files=payload)
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "E_DB_INSERT_FAILED"
    assert len(override_dependencies["storage"].deleted) == 1
    assert override_dependencies["storage"].deleted[0].endswith(".pdf")


def test_ingest_created_by_invalid_omitted(override_dependencies):
    client = TestClient(app)
    payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    response = client.post(
        "/api/v1/papers/ingest",
        files=payload,
        data={"created_by": "system"},
    )
    assert response.status_code == 201
    paper_id = response.json()["paper_id"]
    record = override_dependencies["db"].records[paper_id]
    assert record.created_by is None


def test_ingest_created_by_good_uuid(override_dependencies):
    client = TestClient(app)
    payload = {"file": ("paper.pdf", b"%PDF-1.4 mock", "application/pdf")}
    created_by = str(uuid4())
    response = client.post(
        "/api/v1/papers/ingest",
        files=payload,
        data={"created_by": created_by},
    )
    assert response.status_code == 201
    paper_id = response.json()["paper_id"]
    record = override_dependencies["db"].records[paper_id]
    assert record.created_by == created_by
