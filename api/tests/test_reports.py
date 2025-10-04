from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


class FakePlan:
    def __init__(self, plan_id: str, paper_id: str) -> None:
        self.id = plan_id
        self.paper_id = paper_id
        self.plan_json: Dict[str, Any] = {
            "version": "1.1",
            "metrics": [
                {"name": "accuracy", "split": "test", "goal": 0.80, "tolerance": 0.05, "direction": "maximize"}
            ],
            "justifications": {
                "dataset": {"quote": "Use demo dataset", "citation": "p.1"},
                "model": {"quote": "Use logistic", "citation": "p.2"},
                "config": {"quote": "Use epochs", "citation": "p.3"},
            },
        }


class FakeRun:
    def __init__(self, run_id: str, plan_id: str, status: str, completed_at: datetime | None = None) -> None:
        self.id = run_id
        self.plan_id = plan_id
        self.status = status
        self.created_at = datetime.now(timezone.utc)
        self.completed_at = completed_at or datetime.now(timezone.utc)


class FakeReportDB:
    def __init__(self, plans: List[FakePlan], runs: List[FakeRun]) -> None:
        self.plans = {p.id: p for p in plans}
        self.runs = runs

    def get_plan(self, plan_id: str) -> FakePlan | None:
        return self.plans.get(plan_id)

    def get_runs_by_paper(self, paper_id: str) -> List[FakeRun]:
        # Filter runs by matching plan paper_id
        return [r for r in self.runs if self.plans.get(r.plan_id) and self.plans[r.plan_id].paper_id == paper_id]


class FakeReportStorage:
    def __init__(self) -> None:
        self.records: Dict[str, bytes] = {}

    def download(self, key: str) -> bytes:
        return self.records.get(key, b"{}")

    def create_signed_url(self, key: str, expires_in: int = 3600):
        return type("Artifact", (), {"signed_url": f"https://example.com/{key}", "expires_at": datetime.now(timezone.utc)})

    def object_exists(self, key: str) -> bool:
        return key in self.records


def _override_deps(db: FakeReportDB, storage: FakeReportStorage):
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: storage


@pytest.fixture
def client():
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_report_success(client):
    plan = FakePlan("plan-report-1", "paper-123")
    run = FakeRun("run-report-1", "plan-report-1", "succeeded", datetime.now(timezone.utc))
    db = FakeReportDB([plan], [run])
    storage = FakeReportStorage()

    # Store metrics.json with observed value
    storage.records["runs/run-report-1/metrics.json"] = json.dumps({"accuracy": 0.88}).encode("utf-8")
    storage.records["runs/run-report-1/logs.txt"] = b"test logs"
    storage.records["runs/run-report-1/events.jsonl"] = b'{"type": "log_line", "message": "test"}\n'

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-123/report")
    assert response.status_code == 200

    data = response.json()
    assert data["paper_id"] == "paper-123"
    assert data["run_id"] == "run-report-1"
    assert data["metric_name"] == "accuracy"
    assert data["claimed"] == 0.80
    assert data["observed"] == 0.88
    # gap_percent = (0.88 - 0.80) / 0.80 * 100 = 10.0
    assert abs(data["gap_percent"] - 10.0) < 0.01
    assert len(data["citations"]) == 3
    assert data["artifacts"]["metrics_url"].startswith("https://example.com/")
    assert data["artifacts"]["logs_url"].startswith("https://example.com/")


def test_report_no_runs(client):
    plan = FakePlan("plan-no-runs", "paper-no-runs")
    db = FakeReportDB([plan], [])
    storage = FakeReportStorage()

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-no-runs/report")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "E_REPORT_NO_RUNS"


def test_report_no_successful_runs(client):
    plan = FakePlan("plan-failed", "paper-failed")
    run = FakeRun("run-failed", "plan-failed", "failed", None)
    db = FakeReportDB([plan], [run])
    storage = FakeReportStorage()

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-failed/report")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "E_REPORT_NO_RUNS"


def test_report_missing_metrics_json(client):
    plan = FakePlan("plan-no-metrics", "paper-no-metrics")
    run = FakeRun("run-no-metrics", "plan-no-metrics", "succeeded", datetime.now(timezone.utc))
    db = FakeReportDB([plan], [run])
    storage = FakeReportStorage()

    # Do NOT store metrics.json
    storage.records["runs/run-no-metrics/logs.txt"] = b"test logs"

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-no-metrics/report")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "E_REPORT_METRIC_NOT_FOUND"


def test_report_metric_not_in_metrics_json(client):
    plan = FakePlan("plan-wrong-metric", "paper-wrong-metric")
    run = FakeRun("run-wrong-metric", "plan-wrong-metric", "succeeded", datetime.now(timezone.utc))
    db = FakeReportDB([plan], [run])
    storage = FakeReportStorage()

    # Store metrics.json but with wrong metric name
    storage.records["runs/run-wrong-metric/metrics.json"] = json.dumps({"precision": 0.75}).encode("utf-8")
    storage.records["runs/run-wrong-metric/logs.txt"] = b"test logs"

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-wrong-metric/report")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "E_REPORT_METRIC_NOT_FOUND"


def test_report_negative_gap(client):
    """Test that gap is negative when observed < claimed."""
    plan = FakePlan("plan-negative", "paper-negative")
    run = FakeRun("run-negative", "plan-negative", "succeeded", datetime.now(timezone.utc))
    db = FakeReportDB([plan], [run])
    storage = FakeReportStorage()

    # Observed (0.75) < claimed (0.80) => negative gap
    storage.records["runs/run-negative/metrics.json"] = json.dumps({"accuracy": 0.75}).encode("utf-8")
    storage.records["runs/run-negative/logs.txt"] = b"test logs"

    _override_deps(db, storage)

    response = client.get("/api/v1/papers/paper-negative/report")
    assert response.status_code == 200

    data = response.json()
    assert data["claimed"] == 0.80
    assert data["observed"] == 0.75
    # gap_percent = (0.75 - 0.80) / 0.80 * 100 = -6.25
    assert abs(data["gap_percent"] - (-6.25)) < 0.01
