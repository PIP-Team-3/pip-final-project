
# Claude Test Suite — vNext after C‑REP‑01
_Last updated: 2025-10-04 03:26_

## Baseline
- **Platform:** Windows / Python **3.12.5** / venv at `.venv`
- **Repo status:** **51 passed, 2 skipped, 1 warning**
- **Pipeline:** Ingest → Extractor (SSE) → Planner v1.1 → **Materialize** → **Run (deterministic, CPU‑only, caps)** → **Report (C‑REP‑01)** ✅
- **Responses mode:** **ON**; OpenAI Python pinned **1.109.1**; `file_search` configured via **top‑level** `tools=[{{"type":"file_search","max_num_results":N}}]` (no `attachments=`).
- **DB posture:** Schema **v0** only (no FKs/RLS/CHECK/UNIQUE). App supplies all ids/timestamps.
- **SSE vocabulary:** `stage_update`, `progress`, `log_line`, `metric_update` (optional), `sample_pred` (optional).

---

## What’s already covered by current tests
- Planner/Extractor Responses usage and policy caps
- Materialization (notebook + env) persistence and signed URLs
- Run determinism (`seed_check`), CPU‑only guardrail (`E_GPU_REQUESTED`), artifact truncation
- **New (C‑REP‑01):** report success, no runs, no successful runs, missing/wrong metric, negative gap

---

## New/Complementary Tests to Add (drop‑in specs)

> **Note:** these complement your current test set and focus on edge‑cases and regressions introduced by **C‑REP‑01**. Copy the snippets below into new test modules under `api/tests/` or fold into existing files as you prefer.

### 1) Report selects **latest successful** run
File: `api/tests/test_reports_latest.py`
```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app import dependencies
from app.main import app

def _override(db, storage):
    app.dependency_overrides[dependencies.get_supabase_db] = lambda: db
    app.dependency_overrides[dependencies.get_supabase_storage] = lambda: storage

def test_report_picks_latest_successful_run(monkeypatch):
    from typing import Any, Dict, List
    import json

    class P:  # Plan
        def __init__(self, id, paper_id):
            self.id = id; self.paper_id = paper_id
            self.plan_json = { "metrics": [{{"name":"accuracy","goal":0.80}}], "justifications":{} }

    class R:  # Run
        def __init__(self, id, plan_id, status, dt):
            self.id=id; self.plan_id=plan_id; self.status=status
            self.created_at=dt; self.completed_at=dt

    class DB:
        def __init__(self, plans, runs): self.plans={{p.id:p for p in plans}}; self.runs=runs
        def get_plan(self, pid): return self.plans.get(pid)
        def get_runs_by_paper(self, paper_id):
            return [r for r in self.runs if self.plans.get(r.plan_id) and self.plans[r.plan_id].paper_id==paper_id]

    class Storage:
        def __init__(self, metrics_by_run):
            self._data=metrics_by_run
        def object_exists(self, key): return key in self._data or key.endswith("logs.txt")
        def download(self, key): 
            if key.endswith("metrics.json"): return json.dumps(self._data[key]).encode("utf-8")
            return b''
        def create_signed_url(self, key, expires_in=3600):
            return type("X", (), {{"signed_url": f"https://example.com/{key}"}})

    t0 = datetime.now(timezone.utc)
    plan = P("plan-1", "paper-1")
    older = R("run-old", "plan-1", "succeeded", t0 - timedelta(minutes=5))
    newer = R("run-new", "plan-1", "succeeded", t0)

    db = DB([plan], [older, newer])
    storage = Storage({{
        "runs/run-old/metrics.json": {{"accuracy": 0.81}},
        "runs/run-new/metrics.json": {{"accuracy": 0.90}},
    }})

    _override(db, storage)
    client = TestClient(app)
    try:
        res = client.get("/api/v1/papers/paper-1/report")
        assert res.status_code==200
        payload=res.json()
        assert payload["run_id"]=="run-new"
        assert abs(payload["observed"]-0.90)<1e-6
    finally:
        app.dependency_overrides.clear()
```

### 2) Report artifacts: `events_url` optional, `logs_url` required
File: `api/tests/test_reports_artifacts.py`
```python
from __future__ import annotations
from fastapi.testclient import TestClient
from app import dependencies
from app.main import app
import json

def test_events_url_optional_logs_required():
    class Plan: 
        def __init__(self): 
            self.id="p"; self.paper_id="paper"
            self.plan_json={{"metrics":[{{"name":"accuracy","goal":0.5}}], "justifications":{}}}
    class Run:
        def __init__(self): 
            self.id="r"; self.plan_id="p"; self.status="succeeded"
            from datetime import datetime, timezone
            self.created_at=self.completed_at=datetime.now(timezone.utc)

    class DB:
        def get_plan(self, pid): return Plan()
        def get_runs_by_paper(self, paper_id): return [Run()]

    class Storage:
        def object_exists(self, key): 
            # Provide metrics + logs only, omit events.jsonl
            return key.endswith("metrics.json") or key.endswith("logs.txt")
        def download(self, key): return json.dumps({{"accuracy":0.55}}).encode("utf-8")
        def create_signed_url(self, key, expires_in=3600):
            return type("X", (), {{"signed_url": f"https://example.com/{key}"}})

    app.dependency_overrides[dependencies.get_supabase_db]=lambda: DB()
    app.dependency_overrides[dependencies.get_supabase_storage]=lambda: Storage()
    client=TestClient(app)
    try:
        res=client.get("/api/v1/papers/paper/report")
        assert res.status_code==200
        data=res.json()
        assert data["artifacts"]["metrics_url"].startswith("https://")
        assert data["artifacts"]["logs_url"].startswith("https://")
        assert data["artifacts"]["events_url"] in (None, "")  # optional
    finally:
        app.dependency_overrides.clear()
```

### 3) Observability Prep (C‑OBS‑01): doctor exposes last run snapshot
> Write after implementing the feature. Test spec scaffold below.

File: `api/tests/test_config_doctor_obs.py`
```python
def test_doctor_includes_runner_posture_and_last_run_snapshot():
    # Expect fields (names TBD by implementation):
    # - "runner": { "cpu_only": true, "seed_policy": "deterministic", "artifact_caps": { "logs_mib": 2, "events_mib": 5 } }
    # - "last_run": { "id": "...", "status": "succeeded", "completed_at": "...", "env_hash": "..." }
    # - "caps": { "file_search_per_run": ..., "web_search_per_run": ... }
    # Ensure no tokens/keys present and URLs (if any) are redacted.
    pass
```

### 4) Kid‑Mode Prep (C‑KID‑01): storyboard validator
> After KID‑01 lands, add:
- JSON schema check: pages[5–7], each page has `title`, `body` (grade‑3 language), `alt_text` (non‑empty).
- Update test: after a run completes, final page updates with “ours vs claim” scoreboard.

---

## How to run
```powershell
# From repo root
cd api
../.venv/Scripts/python.exe -m pytest tests/ -v

# Single file
../.venv/Scripts/python.exe -m pytest tests/test_reports_latest.py -v
```

## Troubleshooting
- If a test **hangs**, ensure any notebook execution is **mocked** by patching at the import site:
  `monkeypatch.setattr("app.routers.runs.execute_notebook", async_stub)`
- For JSON schema failures, print the offending payload with `-s -vv` and assert stepwise.
- Keep **OpenAI Python 1.109.1**; top‑level `tools` only (`file_search`), no `attachments=`.
