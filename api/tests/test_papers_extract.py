from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterator, List

import pytest
from fastapi.testclient import TestClient

from app.agents.tooling import ToolUsageTracker
from app.agents.types import Citation, ExtractedClaim, ExtractorOutput
from app.data.models import PaperRecord
from app.main import app
from app.tools.errors import ToolUsagePolicyError
from app.routers.papers import (
    COMPLETED_EVENT_TYPE,
    FILE_SEARCH_STAGE_EVENT,
    START_EVENT_TYPE,
    TOKEN_EVENT_TYPE,
)


class FakePaperDB:
    def __init__(self, paper: PaperRecord) -> None:
        self._paper = paper

    def get_paper(self, paper_id: str) -> PaperRecord | None:
        if paper_id == self._paper.id:
            return self._paper
        return None


class FakeEvent:
    def __init__(self, event_type: str, **kwargs: Any) -> None:
        self.type = event_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeResponseWrapper:
    def __init__(self, parsed: ExtractorOutput) -> None:
        self.output_parsed = parsed


class FakeStream:
    def __init__(self, events: List[FakeEvent], final: FakeResponseWrapper) -> None:
        self._events = events
        self._final = final

    def __iter__(self) -> Iterator[FakeEvent]:
        return iter(self._events)

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get_final_response(self) -> FakeResponseWrapper:
        return self._final


class FakeResponses:
    def __init__(self, events: List[FakeEvent], final: FakeResponseWrapper) -> None:
        self._events = events
        self._final = final
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs: Any) -> FakeStream:
        self.last_kwargs = kwargs
        return FakeStream(self._events, self._final)


class FakeClient:
    def __init__(self, events: List[FakeEvent], final: FakeResponseWrapper) -> None:
        self.responses = FakeResponses(events, final)


def _make_paper_record() -> PaperRecord:
    now = datetime.now(timezone.utc)
    return PaperRecord(
        id="paper-1",
        title="Test Paper",
        source_url=None,
        pdf_storage_path="papers/dev/test.pdf",
        vector_store_id="vs_test",
        pdf_sha256="checksum",
        status="ingested",
        created_by="tester",
        is_public=False,
        created_at=now,
        updated_at=now,
    )


def _collect_sse_events(response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for chunk in response.iter_lines():
        if isinstance(chunk, bytes):
            line = chunk.decode()
        else:
            line = chunk
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["event"] = line[7:]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[6:])
    if current:
        events.append(current)
    return events


@pytest.fixture
def extractor_setup(monkeypatch):
    paper = _make_paper_record()
    fake_db = FakePaperDB(paper)

    from app import dependencies

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_tool_tracker] = lambda: ToolUsageTracker()

    yield {"paper": paper, "db": fake_db}

    app.dependency_overrides.clear()


def test_extractor_stream_happy_path(extractor_setup, monkeypatch):
    output = ExtractorOutput(
        claims=[
            ExtractedClaim(
                dataset_name="imagenet",
                split="validation",
                metric_name="top1",
                metric_value=0.76,
                units="accuracy",
                method_snippet=None,
                citation=Citation(source_citation="Page 3", confidence=0.9),
            )
        ]
    )
    events = [
        FakeEvent(START_EVENT_TYPE),
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(TOKEN_EVENT_TYPE, delta=" token"),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(output))
    monkeypatch.setattr("app.routers.papers.get_client", lambda: fake_client)

    client = TestClient(app)
    with client.stream("POST", f"/api/v1/papers/{extractor_setup['paper'].id}/extract") as response:
        assert response.status_code == 200
        sse_events = _collect_sse_events(response)

    assert [event["event"] for event in sse_events[:3]] == ["stage_update", "stage_update", "token"]
    assert sse_events[0]["data"]["stage"] == "extract_start"
    assert sse_events[1]["data"]["stage"] == "file_search_call"
    assert sse_events[2]["data"]["delta"].strip() == "token"
    assert sse_events[-2]["data"]["stage"] == "extract_complete"
    result_event = sse_events[-1]
    assert result_event["event"] == "result"
    claims = result_event["data"]["claims"]
    assert len(claims) == 1
    assert claims[0]["citation"] == "Page 3"
    assert claims[0]["confidence"] == 0.9
    assert fake_client.responses.last_kwargs
    payload = fake_client.responses.last_kwargs
    tools = payload.get("tools", [])
    fs_tool = next(
        (tool for tool in tools if isinstance(tool, dict) and tool.get("type") == "file_search"),
        None,
    )
    assert fs_tool is not None
    assert "vector_store_ids" not in fs_tool

    messages = payload.get("input", [])
    assert messages
    system_message = next((msg for msg in messages if msg.get("role") == "system"), None)
    assert system_message is not None
    system_content = system_message.get("content", [])
    assert system_content and system_content[0].get("type") == "input_text"

    user_message = next((msg for msg in messages if msg.get("role") == "user"), None)
    assert user_message is not None
    attachments = user_message.get("attachments", [])
    assert attachments
    assert attachments[0]["vector_store_id"] == extractor_setup["paper"].vector_store_id
    attachment_tools = attachments[0].get("tools", [])
    assert attachment_tools and attachment_tools[0]["type"] == "file_search"
    # max_num_results should be in top-level tools, not attachment tools (Responses API spec)
    assert fs_tool.get("max_num_results") == 8
    assert "attachments" not in payload


def test_extractor_guardrail_low_confidence(extractor_setup, monkeypatch):
    output = ExtractorOutput(
        claims=[
            ExtractedClaim(
                dataset_name="imagenet",
                split="validation",
                metric_name="top1",
                metric_value=0.76,
                units="accuracy",
                method_snippet=None,
                citation=Citation(source_citation="Page 3", confidence=0.1),
            )
        ]
    )
    events = [
        FakeEvent(START_EVENT_TYPE),
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(output))
    monkeypatch.setattr("app.routers.papers.get_client", lambda: fake_client)

    client = TestClient(app)
    with client.stream("POST", f"/api/v1/papers/{extractor_setup['paper'].id}/extract") as response:
        sse_events = _collect_sse_events(response)

    assert sse_events[-1]["event"] == "error"
    assert sse_events[-1]["data"]["code"] == "E_EXTRACT_LOW_CONFIDENCE"
    stages = [event for event in sse_events if event["event"] == "stage_update"]
    assert any(stage["data"].get("stage") == "extract_start" for stage in stages)
    assert not any(stage["data"].get("stage") == "extract_complete" for stage in stages)


def test_extractor_policy_cap_error(monkeypatch):
    output = ExtractorOutput(
        claims=[
            ExtractedClaim(
                dataset_name="imagenet",
                split="validation",
                metric_name="top1",
                metric_value=0.76,
                units="accuracy",
                method_snippet=None,
                citation=Citation(source_citation="Page 3", confidence=0.9),
            )
        ]
    )
    events = [
        FakeEvent(START_EVENT_TYPE),
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(output))
    monkeypatch.setattr("app.routers.papers.get_client", lambda: fake_client)

    class ExplodingTracker(ToolUsageTracker):
        def record_call(self, tool_name: str, seconds: float | None = None) -> None:
            raise ToolUsagePolicyError("file_search exceeded per-run cap of 10 invocations")

    from app import dependencies

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: FakePaperDB(_make_paper_record())
    app.dependency_overrides[dependencies.get_tool_tracker] = lambda: ExplodingTracker()

    client = TestClient(app)
    with client.stream("POST", "/api/v1/papers/paper-1/extract") as response:
        sse_events = _collect_sse_events(response)

    app.dependency_overrides.clear()

    assert sse_events[-1]["event"] == "error"
    assert sse_events[-1]["data"]["code"] == "E_POLICY_CAP_EXCEEDED"
    assert not any(event["data"].get("stage") == "extract_complete" for event in sse_events if event["event"] == "stage_update")
