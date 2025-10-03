from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


class FakePlan:
    def __init__(self, plan_id: str, env_hash: str | None = None) -> None:
        self.id = plan_id
        self.plan_json: Dict[str, Any] = {
            "version": "1.1",
            "dataset": {"name": "demo", "split": "test", "filters": [], "notes": None},
            "model": {"name": "logistic", "variant": "tiny", "parameters": {}, "size_category": "tiny"},
            "config": {
                "framework": "sklearn",
                "seed": 7,
                "epochs": 5,
                "batch_size": 16,
                "learning_rate": 0.001,
                "optimizer": "adam",
            },
            "metrics": [
                {"name": "accuracy", "split": "test", "goal": 0.8, "tolerance": 0.05, "direction": "maximize"}
            ],
            "visualizations": ["confusion_matrix"],
            "explain": ["Explain results"],
            "justifications": {
                "dataset": {"quote": "Use demo dataset", "citation": "p.1"},
                "model": {"quote": "Use logistic", "citation": "p.2"},
                "config": {"quote": "Use epochs", "citation": "p.3"},
            },
            "estimated_runtime_minutes": 1.0,
            "license_compliant": True,
            "policy": {"budget_minutes": 1, "max_retries": 1},
        }
        self.env_hash = env_hash


class FakeRunDB:
    def __init__(self, plan: FakePlan | None) -> None:
        self.plan = plan
        self.inserted_runs: List[Dict[str, Any]] = []
        self.updated_runs: List[Dict[str, Any]] = []

    def get_plan(self, plan_id: str) -> FakePlan | None:
        if self.plan and plan_id == self.plan.id:
            return self.plan
        return None

    def insert_run(self, payload):
        data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        self.inserted_runs.append(data)
        return data

    def update_run(self, run_id: str, *, status: str, finished_at: datetime | None = None, env_hash: str | None = None):
        update = {"id": run_id, "status": status, "finished_at": finished_at, "env_hash": env_hash}
        self.updated_runs.append(update)
        return update

    def set_plan_env_hash(self, plan_id: str, env_hash: str):
        if self.plan and plan_id == self.plan.id:
            self.plan.env_hash = env_hash
        return self.plan

    def insert_run_event(self, payload):
        pass

    def insert_run_series(self, *args, **kwargs):
        pass


class FakeStorage:
    def __init__(self) -> None:
        self.records: Dict[str, Dict[str, Any]] = {}

    def store_asset(self, key: str, data: bytes, content_type: str):
        self.records[key] = {"data": data, "content_type": content_type}
        return key

    def store_text(self, key: str, text: str, content_type: str = "text/plain"):
        return self.store_asset(key, text.encode("utf-8"), content_type)

    def create_signed_url(self, key: str, expires_in: int = 60):
        return type("Artifact", (), {"signed_url": f"https://example.com/{key}", "expires_at": datetime.now(timezone.utc)})

    def object_exists(self, key: str) -> bool:
        return key in self.records


def _override(plan: FakePlan | None = None) -> None:
    fake_db = FakeRunDB(plan)
    fake_storage = FakeStorage()
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: fake_storage
    return fake_db, fake_storage


@pytest.fixture
def client():
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_start_run_success(client):
    plan = FakePlan("plan-1")
    fake_db, fake_storage = _override(plan)

    response = client.post("/api/v1/plans/plan-1/run")
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert fake_db.inserted_runs
    assert any(record["id"] == run_id for record in fake_db.inserted_runs)

    assets = fake_storage.records.keys()
    assert any(key.endswith("metrics.json") for key in assets)


def test_start_run_missing_plan_returns_404(client):
    _override(None)
    response = client.post("/api/v1/plans/unknown/run")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "E_PLAN_NOT_FOUND"


def test_stream_events_sequence(client):
    plan = FakePlan("plan-stream")
    fake_db, _ = _override(plan)

    run_response = client.post("/api/v1/plans/plan-stream/run")
    assert run_response.status_code == 202
    run_id = run_response.json()["run_id"]

    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as stream:
        chunks = list(stream.iter_lines())

    assert any("stage_update" in line for line in chunks)
    assert any("metric_update" in line for line in chunks)


