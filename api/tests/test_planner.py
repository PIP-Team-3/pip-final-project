from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator, List
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.agents.tooling import ToolUsageTracker
from app.agents.types import (
    PlanConfig,
    PlanDataset,
    PlanJustification,
    PlanMetric,
    PlanModel,
    PlanPolicy,
    PlannerOutput,
)
from app.data.models import PaperRecord, PlanCreate, PlanRecord
from app.main import app
from app.routers import plans as plans_router
from app.routers.plans import (
    COMPLETED_EVENT_TYPE,
    ERROR_PLAN_SCHEMA_INVALID,
    FILE_SEARCH_STAGE_EVENT,
    PLAN_FILE_SEARCH_RESULTS,
    POLICY_CAP_CODE,
)
from app.tools.errors import ToolUsagePolicyError


class FakePaperDB:
    def __init__(self, paper: PaperRecord) -> None:
        self._paper = paper
        self.inserted_plan: PlanCreate | None = None

    def get_paper(self, paper_id: str) -> PaperRecord | None:
        if paper_id == self._paper.id:
            return self._paper
        return None

    def insert_plan(self, payload: PlanCreate) -> PlanRecord:
        self.inserted_plan = payload
        return PlanRecord.model_validate(payload.model_dump(mode="json"))


class FakeEvent:
    def __init__(self, event_type: str, **kwargs: Any) -> None:
        self.type = event_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeResponseWrapper:
    def __init__(self, parsed: PlannerOutput) -> None:
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


def _paper_record() -> PaperRecord:
    now = datetime.now(timezone.utc)
    return PaperRecord(
        id="paper-1",
        title="Test Plan",
        source_url=None,
        pdf_storage_path="papers/dev/test.pdf",
        vector_store_id="vs_test",
        pdf_sha256="checksum",
        status="extracted",
        created_by="tester",
        is_public=False,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def planner_setup(monkeypatch):
    paper = _paper_record()
    fake_db = FakePaperDB(paper)

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_tool_tracker] = lambda: ToolUsageTracker()

    yield {"paper": paper, "db": fake_db}

    app.dependency_overrides.clear()


def _planner_output() -> PlannerOutput:
    return PlannerOutput(
        version="1.1",
        dataset=PlanDataset(name="CIFAR-10", split="test"),
        model=PlanModel(name="resnet18", variant="tiny"),
        config=PlanConfig(
            framework="torch",
            seed=42,
            epochs=12,
            batch_size=32,
            learning_rate=0.001,
            optimizer="adam",
        ),
        metrics=[
            PlanMetric(name="accuracy", split="test", goal=0.9, tolerance=0.02),
        ],
        visualizations=["confusion_matrix"],
        explain=["Summarize findings for engineers"],
        justifications={
            "dataset": PlanJustification(quote="We evaluate on CIFAR-10.", citation="p.3"),
            "model": PlanJustification(quote="We fine-tune ResNet-18.", citation="p.4"),
            "config": PlanJustification(quote="Training uses batch size 32.", citation="p.5"),
        },
        estimated_runtime_minutes=12.0,
        license_compliant=True,
        policy=PlanPolicy(budget_minutes=15, max_retries=1),
    )


def test_planner_creates_plan(monkeypatch, planner_setup):
    plan_output = _planner_output()
    events = [
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(plan_output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(plan_output))
    monkeypatch.setattr(plans_router, "get_client", lambda: fake_client)

    client = TestClient(app)
    request_body = {
        "claims": [
            {
                "dataset": "CIFAR-10",
                "split": "test",
                "metric": "accuracy",
                "value": 0.85,
                "units": "percent",
                "citation": "p.3",
                "confidence": 0.9,
            }
        ],
        "budget_minutes": 15,
    }
    response = client.post(f"/api/v1/papers/{planner_setup['paper'].id}/plan", json=request_body)
    assert response.status_code == 200

    payload = response.json()
    UUID(payload["plan_id"])  # validates UUID format
    assert payload["plan_version"] == "1.1"
    plan_json = payload["plan_json"]
    assert plan_json["dataset"]["name"] == "CIFAR-10"
    assert plan_json["policy"]["budget_minutes"] == 15

    # Ensure vector store attachments propagated
    assert fake_client.responses.last_kwargs is not None
    tools = fake_client.responses.last_kwargs.get("tools", [])
    assert tools and tools[0]["type"] == "file_search"
    assert tools[0]["vector_store_ids"] == [planner_setup["paper"].vector_store_id]
    assert tools[0]["max_num_results"] == PLAN_FILE_SEARCH_RESULTS
    attachments = fake_client.responses.last_kwargs.get("attachments", [])
    assert attachments and attachments[0]["file_search"]["vector_store_ids"] == [
        planner_setup["paper"].vector_store_id
    ]

    # Plan persisted
    inserted = planner_setup["db"].inserted_plan
    assert inserted is not None
    assert inserted.compute_budget_minutes == 15


def test_planner_schema_validation_error(monkeypatch, planner_setup):
    invalid_output = _planner_output()
    invalid_output.visualizations = [""]  # triggers schema validation error
    events = [
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(invalid_output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(invalid_output))
    monkeypatch.setattr(plans_router, "get_client", lambda: fake_client)

    client = TestClient(app)
    request_body = {
        "claims": [
            {
                "dataset": "CIFAR-10",
                "split": "test",
                "metric": "accuracy",
                "value": 0.85,
                "units": "percent",
                "citation": "p.3",
                "confidence": 0.9,
            }
        ],
        "budget_minutes": 15,
    }
    response = client.post(f"/api/v1/papers/{planner_setup['paper'].id}/plan", json=request_body)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == ERROR_PLAN_SCHEMA_INVALID
    assert "Visualization entries" in detail["errors"]
    assert planner_setup["db"].inserted_plan is None


class ExplodingTracker(ToolUsageTracker):
    def record_call(self, tool_name: str, seconds: float | None = None) -> None:
        raise ToolUsagePolicyError("file_search exceeded per-run cap of 10 invocations")


def test_planner_policy_cap_error(monkeypatch, planner_setup):
    plan_output = _planner_output()
    events = [
        FakeEvent(FILE_SEARCH_STAGE_EVENT),
        FakeEvent(COMPLETED_EVENT_TYPE, response=FakeResponseWrapper(plan_output)),
    ]
    fake_client = FakeClient(events, FakeResponseWrapper(plan_output))
    monkeypatch.setattr(plans_router, "get_client", lambda: fake_client)

    app.dependency_overrides[dependencies.get_tool_tracker] = lambda: ExplodingTracker()

    client = TestClient(app)
    request_body = {
        "claims": [
            {
                "dataset": "CIFAR-10",
                "split": "test",
                "metric": "accuracy",
                "value": 0.85,
                "units": "percent",
                "citation": "p.3",
                "confidence": 0.9,
            }
        ],
        "budget_minutes": 15,
    }
    response = client.post(f"/api/v1/papers/{planner_setup['paper'].id}/plan", json=request_body)
    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["code"] == POLICY_CAP_CODE

    app.dependency_overrides.pop(dependencies.get_tool_tracker, None)

