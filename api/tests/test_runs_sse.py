from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import nbformat
import pytest
from fastapi.testclient import TestClient
from nbformat.v4 import new_code_cell, new_notebook

from app import dependencies
from app.main import app
from app.run.runner_local import NotebookRunResult


def build_plan(plan_id: str, paper_id: str = "paper-1") -> Dict[str, Any]:
    return {
        "version": "1.1",
        "dataset": {"name": "demo", "split": "test", "filters": [], "notes": None},
        "model": {
            "name": "linear",
            "variant": "tiny",
            "parameters": {},
            "size_category": "tiny",
        },
        "config": {
            "framework": "sklearn",
            "seed": 1,
            "epochs": 2,
            "batch_size": 8,
            "learning_rate": 0.001,
            "optimizer": "adam",
        },
        "metrics": [
            {
                "name": "accuracy",
                "split": "test",
                "goal": 0.8,
                "tolerance": 0.05,
                "direction": "maximize",
            }
        ],
        "visualizations": ["confusion_matrix"],
        "explain": ["explain the results"],
        "justifications": {
            "dataset": {"quote": "Use demo", "citation": "p.1"},
            "model": {"quote": "Use linear", "citation": "p.2"},
            "config": {"quote": "Parameters", "citation": "p.3"},
        },
        "estimated_runtime_minutes": 1.0,
        "license_compliant": True,
        "policy": {"budget_minutes": 2, "max_retries": 1},
    }


def build_notebook(cells: List[str]) -> bytes:
    notebook = new_notebook(cells=[new_code_cell(source=src) for src in cells])
    return nbformat.writes(notebook).encode("utf-8")


class FakePlanRecord:
    def __init__(self, plan_id: str, notebook_bytes: bytes) -> None:
        self.id = plan_id
        self.paper_id = "paper-1"
        self.env_hash = "env-abc"
        self.plan_json = build_plan(plan_id)
        self._notebook_bytes = notebook_bytes


class FakeRunDB:
    def __init__(self, plan: FakePlanRecord) -> None:
        self.plan = plan
        self.inserted_runs: List[Dict[str, Any]] = []
        self.updated_runs: List[Dict[str, Any]] = []
        self.events: List[Any] = []

    def get_plan(self, plan_id: str) -> Optional[FakePlanRecord]:
        if self.plan and plan_id == self.plan.id:
            return self.plan
        return None

    def insert_run(self, payload):
        data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        self.inserted_runs.append(data)
        return data

    def update_run(
        self,
        run_id: str,
        *,
        status: Optional[str] = None,
        started_at = None,
        completed_at = None,
        env_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        update = {
            "id": run_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "env_hash": env_hash,
        }
        self.updated_runs.append(update)
        return update

    def insert_run_event(self, payload):
        self.events.append(payload)


class FakeStorage:
    def __init__(self, notebook_bytes: bytes) -> None:
        self._notebook_bytes = notebook_bytes
        self.stored: Dict[str, Dict[str, Any]] = {}

    def download(self, key: str) -> bytes:
        return self._notebook_bytes

    def store_text(self, key: str, text: str, content_type: str = "text/plain"):
        self.stored[key] = {"text": text, "content_type": content_type}
        return key


def _override_dependencies(plan_record: FakePlanRecord, storage: FakeStorage, db: FakeRunDB) -> None:
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: storage


def _collect_events(client: TestClient, run_id: str) -> List[Dict[str, Any]]:
    import time
    events: List[Dict[str, Any]] = []

    # Wait a moment for async task to complete
    time.sleep(0.5)

    with client.stream("GET", f"/api/v1/runs/{run_id}/events") as stream:
        current_event: Optional[str] = None
        for chunk in stream.iter_lines():
            if not chunk:
                continue
            line = chunk.decode() if isinstance(chunk, bytes) else chunk
            if line.startswith("event: "):
                current_event = line.split(": ", 1)[1]
            elif line.startswith("data: ") and current_event:
                payload = json.loads(line[6:])
                events.append({"event": current_event, "data": payload})
                # Stop after seeing run completion
                if payload.get("stage") == "run_complete":
                    break
                if payload.get("stage") == "run_error":
                    break
    return events


@pytest.fixture(autouse=True)
def clear_overrides():
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skip(reason="SSE streaming with TestClient is flaky - covered by integration tests")
def test_run_happy_path_streams_events_and_artifacts(monkeypatch):
    # Mock execute_notebook to avoid real notebook execution
    async def _stub_execute_notebook(notebook_bytes, emit, timeout_minutes, seed=42):
        emit("progress", {"percent": 0})
        emit("log_line", {"message": "first log line"})
        emit("log_line", {"message": "second log line"})
        emit("metric_update", {"metric": "accuracy", "value": 0.88, "split": "test"})
        emit("progress", {"percent": 100})
        return NotebookRunResult(
            metrics_text='{"accuracy": 0.88}',
            events_text='{"type": "metric_update", "metric": "accuracy", "value": 0.88, "split": "test"}\n',
            logs_text="first log line\nsecond log line\ncaptured log\n",
        )

    monkeypatch.setattr("app.routers.runs.execute_notebook", _stub_execute_notebook)

    notebook_bytes = build_notebook(
        [
            "from pathlib import Path\nimport json\n\nPath('metrics.json').write_text(json.dumps({'accuracy': 0.88}))\nwith open('events.jsonl', 'w', encoding='utf-8') as fh:\n    fh.write(json.dumps({'type': 'metric_update', 'metric': 'accuracy', 'value': 0.88, 'split': 'test'}) + '\\n')\nprint('first log line')\nprint('second log line')",
            "with open('logs.txt', 'w', encoding='utf-8') as fh:\n    fh.write('captured log\\n')",
        ]
    )
    plan_record = FakePlanRecord("plan-happy", notebook_bytes)
    storage = FakeStorage(notebook_bytes)
    db = FakeRunDB(plan_record)
    _override_dependencies(plan_record, storage, db)

    client = TestClient(app)
    try:
        response = client.post("/api/v1/plans/plan-happy/run")
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        events = _collect_events(client, run_id)

        assert any(evt["event"] == "stage_update" and evt["data"]["stage"] == "run_start" for evt in events)
        assert any(evt["event"] == "stage_update" and evt["data"]["stage"] == "run_complete" for evt in events)
        assert any(evt["event"] == "log_line" and "first log line" in evt["data"].get("message", "") for evt in events)
        assert any(evt["event"] == "metric_update" and evt["data"].get("metric") == "accuracy" for evt in events)

        stored_keys = storage.stored.keys()
        assert any(key.endswith("metrics.json") for key in stored_keys)
        assert any(key.endswith("events.jsonl") for key in stored_keys)
        assert any(key.endswith("logs.txt") for key in stored_keys)

        assert any(update["status"] == "succeeded" for update in db.updated_runs)
    finally:
        client.close()


@pytest.mark.skip(reason="SSE streaming with TestClient is flaky - covered by integration tests")
def test_run_error_path_emits_error_and_logs(monkeypatch):
    # Mock execute_notebook to simulate failure
    from app.run.runner_local import NotebookExecutionError

    async def _stub_execute_notebook_error(notebook_bytes, emit, timeout_minutes, seed=42):
        emit("progress", {"percent": 0})
        emit("log_line", {"message": "about to fail"})
        raise NotebookExecutionError("RuntimeError: boom")

    monkeypatch.setattr("app.routers.runs.execute_notebook", _stub_execute_notebook_error)

    notebook_bytes = build_notebook(
        [
            "print('about to fail')\nraise RuntimeError('boom')",
        ]
    )
    plan_record = FakePlanRecord("plan-fail", notebook_bytes)
    storage = FakeStorage(notebook_bytes)
    db = FakeRunDB(plan_record)
    _override_dependencies(plan_record, storage, db)

    client = TestClient(app)
    try:
        response = client.post("/api/v1/plans/plan-fail/run")
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        events = _collect_events(client, run_id)

        assert any(evt["event"] == "stage_update" and evt["data"]["stage"] == "run_error" for evt in events)
        assert any(evt["event"] == "error" and evt["data"].get("code") == "E_RUN_FAILED" for evt in events)

        stored_keys = storage.stored.keys()
        assert any(key.endswith("logs.txt") for key in stored_keys)
        assert any(update["status"] == "failed" for update in db.updated_runs)
    finally:
        client.close()


