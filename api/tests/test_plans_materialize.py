from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import nbformat
import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.data.models import PlanCreate, PlanRecord, StorageArtifact
from app.main import app


def _plan_json() -> Dict[str, Any]:
    return {
        "version": "1.1",
        "dataset": {
            "name": "CIFAR-10",
            "split": "test",
            "filters": [],
            "notes": None,
        },
        "model": {
            "name": "ResNet-18",
            "variant": "tiny",
            "parameters": {"learning_rate": 0.001},
            "size_category": "tiny",
        },
        "config": {
            "framework": "torch",
            "seed": 42,
            "epochs": 5,
            "batch_size": 32,
            "learning_rate": 0.001,
            "optimizer": "adam",
        },
        "metrics": [
            {
                "name": "accuracy",
                "split": "test",
                "goal": 0.9,
                "tolerance": 0.02,
                "direction": "maximize",
            }
        ],
        "visualizations": ["confusion_matrix"],
        "explain": ["Summarize the experiment for engineers"],
        "justifications": {
            "dataset": {"quote": "We evaluate on CIFAR-10", "citation": "p.3"},
            "model": {"quote": "ResNet-18 baseline", "citation": "p.4"},
            "config": {"quote": "Batch size 32", "citation": "p.5"},
        },
        "estimated_runtime_minutes": 12.0,
        "license_compliant": True,
        "policy": {"budget_minutes": 15, "max_retries": 1},
    }


def _plan_record(plan_id: str) -> PlanRecord:
    payload = PlanCreate(
        id=plan_id,
        paper_id="paper-123",
        version="1.1",
        plan_json=_plan_json(),
        env_hash=None,
        compute_budget_minutes=15,
        status="draft",
        created_by=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return PlanRecord.model_validate(payload.model_dump(mode="json"))


class FakeStorage:
    def __init__(self) -> None:
        self.assets: Dict[str, Dict[str, Any]] = {}
        self.signed_count = 0

    def store_asset(self, key: str, data: bytes, content_type: str) -> StorageArtifact:
        self.assets[key] = {"data": data, "content_type": content_type}
        return StorageArtifact(bucket="plans", path=key)

    def store_text(self, key: str, text: str, content_type: str = "text/plain") -> StorageArtifact:
        return self.store_asset(key, text.encode("utf-8"), content_type)

    def store_pdf(self, key: str, data: bytes) -> StorageArtifact:  # pragma: no cover - compatibility
        return self.store_asset(key, data, "application/pdf")

    def create_signed_url(self, key: str, expires_in: int = 120) -> StorageArtifact:
        self.signed_count += 1
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return StorageArtifact(
            bucket="plans",
            path=key,
            signed_url=f"https://example.com/{key}?token=redacted",
            expires_at=expires_at,
        )

    def object_exists(self, key: str) -> bool:
        return key in self.assets


class FakePlanDB:
    def __init__(self, record: PlanRecord | None) -> None:
        self.record = record
        self.updated_hashes: list[str] = []

    def get_plan(self, plan_id: str) -> PlanRecord | None:
        if self.record and plan_id == self.record.id:
            return self.record
        return None

    def set_plan_env_hash(self, plan_id: str, env_hash: str) -> PlanRecord:
        self.updated_hashes.append(env_hash)
        if not self.record:
            raise RuntimeError("Plan not available")
        updated = self.record.model_copy(update={"env_hash": env_hash, "updated_at": datetime.now(timezone.utc)})
        self.record = updated
        return updated


@pytest.fixture
def test_client():
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_materialize_plan_persists_assets(test_client):
    plan_id = "plan-abc"
    plan_record = _plan_record(plan_id)
    fake_db = FakePlanDB(plan_record)
    fake_storage = FakeStorage()

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: fake_storage

    response = test_client.post(f"/api/v1/plans/{plan_id}/materialize")
    assert response.status_code == 200
    payload = response.json()

    notebook_key = f"plans/{plan_id}/notebook.ipynb"
    env_key = f"plans/{plan_id}/requirements.txt"
    assert payload["notebook_asset_path"] == notebook_key
    assert payload["env_asset_path"] == env_key

    assert notebook_key in fake_storage.assets
    assert env_key in fake_storage.assets

    notebook_bytes = fake_storage.assets[notebook_key]["data"]
    nb = nbformat.reads(notebook_bytes.decode("utf-8"), as_version=4)
    assert any("log_event" in cell.get("source", "") for cell in nb.cells if cell["cell_type"] == "code")

    requirements_bytes = fake_storage.assets[env_key]["data"]
    requirements_text = requirements_bytes.decode("utf-8").strip().splitlines()
    expected_hash = hashlib.sha256("\n".join(sorted(line.strip() for line in requirements_text if line)).encode("utf-8")).hexdigest()
    assert payload["env_hash"] == expected_hash
    assert fake_db.updated_hashes[-1] == expected_hash


def test_materialize_plan_missing_plan_returns_404(test_client):
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: FakePlanDB(None)
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: FakeStorage()

    response = test_client.post("/api/v1/plans/missing/materialize")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "E_PLAN_NOT_FOUND"


def test_plan_assets_returns_signed_urls(test_client):
    plan_id = "plan-assets"
    plan_record = _plan_record(plan_id)
    fake_db = FakePlanDB(plan_record)
    fake_storage = FakeStorage()

    # Pretend assets already exist
    fake_storage.store_asset(f"plans/{plan_id}/notebook.ipynb", b"nb", "application/json")
    fake_storage.store_text(f"plans/{plan_id}/requirements.txt", "numpy==1.26.4\n")

    app.dependency_overrides[dependencies.get_supabase_db] = lambda: fake_db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: fake_storage

    response = test_client.get(f"/api/v1/plans/{plan_id}/assets")
    assert response.status_code == 200
    body = response.json()
    assert body["notebook_signed_url"].startswith("https://example.com/plans/")
    assert body["env_signed_url"].startswith("https://example.com/plans/")


