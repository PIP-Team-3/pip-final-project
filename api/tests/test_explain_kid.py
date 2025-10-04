from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app import dependencies
from app.main import app


class FakePaper:
    def __init__(self, paper_id: str, title: str) -> None:
        self.id = paper_id
        self.title = title
        self.status = "ready"


class FakePlan:
    def __init__(self, plan_id: str, paper_id: str) -> None:
        self.id = plan_id
        self.paper_id = paper_id
        self.plan_json = {
            "version": "1.1",
            "metrics": [{"name": "accuracy", "goal": 0.85, "split": "test"}],
            "justifications": {},
        }


class FakeRun:
    def __init__(self, run_id: str, plan_id: str, status: str) -> None:
        self.id = run_id
        self.plan_id = plan_id
        self.status = status
        self.created_at = datetime.now(timezone.utc)
        self.completed_at = datetime.now(timezone.utc) if status == "succeeded" else None


class FakeStoryboard:
    def __init__(self, storyboard_id: str, paper_id: str, storyboard_json: Dict[str, Any]) -> None:
        self.id = storyboard_id
        self.paper_id = paper_id
        self.run_id = None
        self.storyboard_json = storyboard_json
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeKidDB:
    def __init__(self) -> None:
        self.papers: Dict[str, FakePaper] = {}
        self.plans: Dict[str, FakePlan] = {}
        self.runs: list[FakeRun] = []
        self.storyboards: Dict[str, FakeStoryboard] = {}

    def get_paper(self, paper_id: str) -> FakePaper | None:
        return self.papers.get(paper_id)

    def get_plan(self, plan_id: str) -> FakePlan | None:
        return self.plans.get(plan_id)

    def get_runs_by_paper(self, paper_id: str) -> list[FakeRun]:
        # Match runs via plan paper_id
        return [r for r in self.runs if self.plans.get(r.plan_id) and self.plans[r.plan_id].paper_id == paper_id]

    def insert_storyboard(self, payload) -> FakeStoryboard:
        story = FakeStoryboard(payload.id, payload.paper_id, payload.storyboard_json)
        self.storyboards[payload.id] = story
        return story

    def get_storyboard(self, storyboard_id: str) -> FakeStoryboard | None:
        return self.storyboards.get(storyboard_id)

    def update_storyboard(self, storyboard_id: str, **kwargs) -> FakeStoryboard | None:
        story = self.storyboards.get(storyboard_id)
        if not story:
            return None
        if "run_id" in kwargs and kwargs["run_id"] is not None:
            story.run_id = kwargs["run_id"]
        if "storyboard_json" in kwargs and kwargs["storyboard_json"] is not None:
            story.storyboard_json = kwargs["storyboard_json"]
        story.updated_at = datetime.now(timezone.utc)
        return story


class FakeKidStorage:
    def __init__(self) -> None:
        self.records: Dict[str, bytes] = {}

    def store_text(self, key: str, text: str, content_type: str):
        self.records[key] = text.encode("utf-8")

    def download(self, key: str) -> bytes:
        return self.records.get(key, b"{}")

    def create_signed_url(self, key: str, expires_in: int = 3600):
        return type(
            "Artifact",
            (),
            {"signed_url": f"https://example.com/{key}", "expires_at": datetime.now(timezone.utc)},
        )

    def object_exists(self, key: str) -> bool:
        return key in self.records


def _override_deps(db: FakeKidDB, storage: FakeKidStorage):
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: storage


@pytest.fixture
def client():
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_story_create_happy_returns_id_and_signed_url(client, monkeypatch):
    """Test successful storyboard creation with valid pages and alt-text."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    # Add paper
    db.papers["paper-1"] = FakePaper("paper-1", "Super Cool AI Paper")

    # Mock the kid-mode agent to return valid storyboard
    valid_storyboard = {
        "pages": [
            {
                "page_number": 1,
                "title": "The Amazing AI Adventure",
                "body": "Scientists made a robot brain. It learns like you do!",
                "alt_text": "A friendly robot with a glowing brain learning from books",
                "visual_hint": "robot reading books",
            },
            {
                "page_number": 2,
                "title": "Why This Matters",
                "body": "Robots can help doctors find sick people faster.",
                "alt_text": "A doctor and robot working together at a hospital",
            },
            {
                "page_number": 3,
                "title": "The Experiment",
                "body": "We tested if the robot brain really works. We gave it math problems.",
                "alt_text": "A robot solving math problems on a whiteboard",
            },
            {
                "page_number": 4,
                "title": "Our Test",
                "body": "We ran the same test at home. Let's see what happened!",
                "alt_text": "Kids watching a computer run tests with colorful progress bars",
            },
            {
                "page_number": 5,
                "title": "The Results",
                "body": "The robot got most answers right! More results coming soon.",
                "alt_text": "A scoreboard showing test results with happy faces",
            },
        ],
        "glossary": [{"term": "AI", "definition": "Artificial Intelligence - teaching computers to think"}],
    }

    async def mock_generate_storyboard(paper_id, paper_title, plan_summary):
        return valid_storyboard

    monkeypatch.setattr("app.routers.explain.explain_kid.generate_storyboard", mock_generate_storyboard)

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid", json={"paper_id": "paper-1"})

    assert response.status_code == 201
    data = response.json()
    assert "storyboard_id" in data
    assert data["paper_id"] == "paper-1"
    assert data["pages_count"] == 5
    assert data["signed_url"].startswith("https://example.com/")
    assert "expires_at" in data

    # Verify storage has the JSON
    story_id = data["storyboard_id"]
    storage_key = f"storyboards/{story_id}.json"
    assert storage_key in storage.records


def test_story_missing_alt_text_returns_typed_error(client, monkeypatch):
    """Test that missing alt_text triggers E_STORY_MISSING_ALT_TEXT."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    db.papers["paper-bad"] = FakePaper("paper-bad", "Bad Paper")

    # Mock returns storyboard with missing alt_text
    invalid_storyboard = {
        "pages": [
            {"page_number": 1, "title": "Page 1", "body": "Text", "alt_text": ""},  # Empty alt_text
            {"page_number": 2, "title": "Page 2", "body": "Text", "alt_text": "Valid alt text"},
        ],
        "glossary": [],
    }

    async def mock_generate_bad(paper_id, paper_title, plan_summary):
        # Simulate validation error
        raise ValueError("Page 1 missing required alt_text")

    monkeypatch.setattr("app.routers.explain.explain_kid.generate_storyboard", mock_generate_bad)

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid", json={"paper_id": "paper-bad"})

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["code"] == "E_STORY_MISSING_ALT_TEXT"


def test_story_min_pages_enforced(client, monkeypatch):
    """Test that storyboards with fewer than 5 pages are rejected."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    db.papers["paper-short"] = FakePaper("paper-short", "Short Paper")

    # Only 3 pages
    short_storyboard = {
        "pages": [
            {"page_number": 1, "title": "P1", "body": "B1", "alt_text": "A1"},
            {"page_number": 2, "title": "P2", "body": "B2", "alt_text": "A2"},
            {"page_number": 3, "title": "P3", "body": "B3", "alt_text": "A3"},
        ],
        "glossary": [],
    }

    async def mock_generate_short(paper_id, paper_title, plan_summary):
        raise ValueError("Storyboard has only 3 pages, need at least 5")

    monkeypatch.setattr("app.routers.explain.explain_kid.generate_storyboard", mock_generate_short)

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid", json={"paper_id": "paper-short"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "E_STORY_TOO_FEW_PAGES"


def test_story_refresh_updates_final_page_after_run(client, monkeypatch):
    """Test that refresh endpoint updates the final page with run results."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    # Setup paper, plan, run
    db.papers["paper-refresh"] = FakePaper("paper-refresh", "Test Paper")
    db.plans["plan-refresh"] = FakePlan("plan-refresh", "paper-refresh")
    db.runs.append(FakeRun("run-refresh", "plan-refresh", "succeeded"))

    # Add metrics.json to storage
    storage.records["runs/run-refresh/metrics.json"] = json.dumps({"accuracy": 0.90}).encode("utf-8")
    storage.records["runs/run-refresh/logs.txt"] = b"test logs"

    # Create initial storyboard
    initial_storyboard = {
        "pages": [
            {"page_number": 1, "title": "Page 1", "body": "Body 1", "alt_text": "Alt 1"},
            {"page_number": 2, "title": "Page 2", "body": "Body 2", "alt_text": "Alt 2"},
            {"page_number": 3, "title": "Page 3", "body": "Body 3", "alt_text": "Alt 3"},
            {"page_number": 4, "title": "Page 4", "body": "Body 4", "alt_text": "Alt 4"},
            {"page_number": 5, "title": "Results", "body": "Results pending", "alt_text": "Alt 5"},
        ],
        "glossary": [],
    }

    story = FakeStoryboard("story-refresh", "paper-refresh", initial_storyboard)
    db.storyboards["story-refresh"] = story

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid/story-refresh/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["storyboard_id"] == "story-refresh"
    assert data["run_id"] == "run-refresh"
    assert "scoreboard" in data
    assert data["scoreboard"]["metric_name"] == "accuracy"
    assert abs(data["scoreboard"]["claimed_value"] - 0.85) < 0.01
    assert abs(data["scoreboard"]["observed_value"] - 0.90) < 0.01
    # gap_percent = (0.90 - 0.85) / 0.85 * 100 ≈ 5.88
    assert abs(data["scoreboard"]["gap_percent"] - 5.88) < 0.1

    # Verify final page was updated
    updated_story = db.storyboards["story-refresh"]
    final_page = updated_story.storyboard_json["pages"][-1]
    assert "Scoreboard" in final_page["body"]
    assert "0.90" in final_page["body"]


def test_story_signed_urls_no_tokens_leak(client, monkeypatch):
    """Test that signed URLs don't expose tokens in logs or response."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    db.papers["paper-secure"] = FakePaper("paper-secure", "Secure Paper")

    valid_storyboard = {
        "pages": [
            {"page_number": i, "title": f"Page {i}", "body": f"Body {i}", "alt_text": f"Alt {i}"}
            for i in range(1, 6)
        ],
        "glossary": [],
    }

    async def mock_generate(paper_id, paper_title, plan_summary):
        return valid_storyboard

    monkeypatch.setattr("app.routers.explain.explain_kid.generate_storyboard", mock_generate)

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid", json={"paper_id": "paper-secure"})

    assert response.status_code == 201
    data = response.json()

    # Signed URL should NOT contain actual secrets/tokens (our fake returns clean URLs)
    signed_url = data["signed_url"]
    assert "sk-" not in signed_url  # No API keys
    assert "secret" not in signed_url.lower()
    assert "token" not in signed_url.lower()


def test_story_paper_not_found(client):
    """Test that creating storyboard for non-existent paper returns 404."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid", json={"paper_id": "nonexistent"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "E_PAPER_NOT_FOUND"


def test_story_refresh_no_successful_runs(client):
    """Test refresh when no successful runs exist."""
    db = FakeKidDB()
    storage = FakeKidStorage()

    db.papers["paper-norun"] = FakePaper("paper-norun", "No Run Paper")
    db.plans["plan-norun"] = FakePlan("plan-norun", "paper-norun")
    # Add a failed run
    db.runs.append(FakeRun("run-failed", "plan-norun", "failed"))

    story = FakeStoryboard(
        "story-norun",
        "paper-norun",
        {
            "pages": [
                {"page_number": i, "title": f"P{i}", "body": f"B{i}", "alt_text": f"A{i}"} for i in range(1, 6)
            ],
            "glossary": [],
        },
    )
    db.storyboards["story-norun"] = story

    _override_deps(db, storage)

    response = client.post("/api/v1/explain/kid/story-norun/refresh")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "E_STORY_NO_RUN"
