from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.data.models import PaperCreate
from app.data.supabase import SupabaseDatabase, is_valid_uuid


_VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _paper_payload(created_by: str | None = _VALID_UUID) -> PaperCreate:
    now = datetime.now(timezone.utc)
    return PaperCreate(
        id="paper-123",
        title="Test Paper",
        source_url=None,
        pdf_storage_path="papers/dev/test.pdf",
        vector_store_id="vs_test",
        pdf_sha256="checksum",
        status="ingested",
        created_by=created_by,
        is_public=False,
        created_at=now,
        updated_at=now,
    )


class _FakeInsertQuery:
    def __init__(self, response_data: object) -> None:
        self._response_data = response_data
        self.last_payload = None

    def insert(self, payload: dict[str, object]) -> "_FakeInsertQuery":
        self.last_payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._response_data)


class _FakeClient:
    def __init__(self, response_data: object) -> None:
        self._response_data = response_data
        self.last_table: str | None = None
        self.last_query: _FakeInsertQuery | None = None

    def table(self, table_name: str) -> _FakeInsertQuery:
        self.last_table = table_name
        self.last_query = _FakeInsertQuery(self._response_data)
        return self.last_query


def test_insert_paper_handles_list_response():
    payload = _paper_payload()
    response_row = payload.model_dump(mode="json")
    client = _FakeClient([response_row])
    db = SupabaseDatabase(client)  # type: ignore[arg-type]

    record = db.insert_paper(payload)

    assert client.last_table == "papers"
    assert client.last_query is not None
    assert client.last_query.last_payload["created_by"] == _VALID_UUID
    assert record.id == payload.id


def test_insert_paper_handles_dict_response():
    payload = _paper_payload()
    response_row = payload.model_dump(mode="json")
    client = _FakeClient(response_row)
    db = SupabaseDatabase(client)  # type: ignore[arg-type]

    record = db.insert_paper(payload)

    assert record.vector_store_id == payload.vector_store_id


def test_insert_paper_omits_invalid_created_by():
    invalid_payload = _paper_payload(created_by="system")
    response_row = invalid_payload.model_dump(mode="json")
    client = _FakeClient(response_row)
    db = SupabaseDatabase(client)  # type: ignore[arg-type]

    record = db.insert_paper(invalid_payload)

    assert client.last_query is not None
    assert "created_by" not in client.last_query.last_payload
    assert not is_valid_uuid(record.created_by)
