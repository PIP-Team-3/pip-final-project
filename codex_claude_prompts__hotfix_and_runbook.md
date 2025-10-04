
# Codex/Claude Prompts — **Hotfix & Runbook** (Responses + File Search, Planner, Tests)
_Last updated: 2025-10-04_

> **How to use this file**  
> Copy a single **prompt block** into a fresh Codex/Claude chat (start with the **Context Hydration** prompt once per new chat). Each block contains scope, files, acceptance, and “done when” checks. Work through them in order.

---

## 0) **Context Hydration** (paste at the top of a fresh chat)

**Project:** P2N (Paper-to-Notebook Reproducer)  
**Goal:** Ingest a paper -> extract claims w/ citations -> plan -> materialize a notebook & env -> run sandbox -> stream SSE -> compute reproduction gap -> (Kid-Mode Storybook).

**Stack (server):** FastAPI, Supabase (DB + Storage), OpenAI Python **1.109.1** in **Responses mode** (tools: `file_search`), Windows dev (PowerShell).  
**Schema posture:** v0 (no FKs/RLS/CHECK/UNIQUE/defaults). App supplies all values.  
**Key constraints:**
- Supabase buckets are **private**; expose signed URLs via API only.
- **File Search**: upload PDFs with `purpose="assistants"`, then attach to a **vector store**; for Responses, pass **`attachments` inside the user message** and **`tools=[{"type":"file_search"}]`** at the top level.
- **Streaming vocabulary:** `stage_update`, `log_line`, token deltas; final JSON payload.
- **Tool caps:** file_search per run <= 10; exceeding -> `policy.cap.exceeded`.
- **Error taxonomy:** typed errors w/ remediation (e.g., `E_FILESEARCH_INDEX_FAILED`, `E_DB_INSERT_FAILED`, `E_POLICY_CAP_EXCEEDED`, `E_RUN_TIMEOUT`).
- **Windows dev:** provide PowerShell-friendly commands; server run with `--workers 1` for stable SSE.

**Current status (green):**
- Ingest endpoint works; vectors created; storage writes ok.
- Planner v1.1 implemented with strict schema, materialize routes exist; tests pass (~45), 2 SSE tests skipped for integration.

**Priority hotfix:** Some routes still use `client.responses.stream(..., attachments=...)` (invalid). Must move `attachments` **into the message** and declare tools at the call site.

---

## 1) Prompt — **Fix Responses API usage** (planner + extractor)

**Intent:** Move `attachments` into the user message and set `tools=[{"type":"file_search"}]` at the top level. Keep File Search upload flow (`purpose="assistants"`) as-is.

**Files to edit:**
- `api/app/routers/plans.py` (planner route `POST /api/v1/papers/{paper_id}/plan`)
- `api/app/routers/papers.py` (extract route `GET /api/v1/papers/{paper_id}/extract` or `POST` if implemented)
- (If present) any helper that incorrectly forwards `attachments` to the top level

**What to change (sketch):**
```python
from openai import OpenAI
client = OpenAI(api_key=settings.openai_api_key)

messages = [
    {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
    {
        "role": "user",
        "content": [{"type": "input_text", "text": user_text}],
        "attachments": [
            {
                "vector_store_id": paper.vector_store_id,
                "tools": [{"type": "file_search"}],
            }
        ],
    },
]
tools = [{"type": "file_search"}]

with client.responses.stream(
    model=settings.openai_model,    # e.g. "gpt-4.1-mini"
    input=messages,
    tools=tools,
) as stream:
    # existing SSE bridge, caps, guardrails, final parse
    final = stream.get_final_response()
```

**Acceptance:**
- Planner and extractor no longer pass `attachments` at the top level.
- Manual run: planner returns HTTP 201 with `{plan_id, ...}` when provided a valid JSON body and `X-Actor-Id` header (UUID).
- Doctor endpoint still shows Responses-mode enabled and `file_search: true`.
- Logs show redacted IDs; no token leakage.

**Done when:**
- `uvicorn` shows `201 Created` for `/plan` on a valid payload.  
- Manual steps (see end of this file) succeed end-to-end: **ingest -> plan -> materialize -> assets**.

---

## 2) Prompt — **Dotenv integration (optional permanent fix)**

**Intent:** Automatically load `.env` at app startup on Windows so developers don’t have to export env vars manually.

**Files:**
- `api/app/main.py` **or** `api/app/config/settings.py`

**Tasks:**
1. Add `python-dotenv` to `api/requirements.txt`.
2. At the very top of app boot (before config validation), call:
   ```python
   from dotenv import load_dotenv; load_dotenv(override=False)
   ```
3. Keep the doctor snapshot redaction as-is; never print actual secrets.

**Acceptance:**
- Fresh shell + `uvicorn` starts without manual env export if `.env` is present.
- CI runs unchanged (tests already inject dummy env in `conftest.py`).

---

## 3) Prompt — **Planner request contract** (422 fixes & docs)

**Intent:** Make the planner route accept `created_by` in body and also respect optional `X-Actor-Id` header as an override for audit/tracing (validated as UUID). Keep `claims[]` required.

**Files:**
- `api/app/routers/plans.py`
- `api/app/schemas/plan_v1_1.py` (request model if you have one)

**Tasks:**
- Validate `created_by` (UUID string); if header present and valid, use it for auditing but persist the body value as the owner (v0 schema choice).
- Ensure 422s return the first 3 validation messages in a structured field `errors` for DX.
- Update docstrings with a minimal working `Invoke-RestMethod` example (PowerShell).

**Acceptance:**
- `Invoke-RestMethod … -Body ($obj|ConvertTo-Json)` creates a plan when `claims[]` present.
- 422 errors are human-readable with top 3 validation issues.

---

## 4) Prompt — **Tests: keep unit suite fast & deterministic**

**Intent:** Mock `execute_notebook` in unit tests; keep live SSE tests behind an `integration` marker (skipped by default).

**Files:**
- `api/tests/test_runs_stub.py`
- `api/tests/test_runs_sse.py`
- `api/tests/conftest.py`

**Tasks:**
- Patch at the **import site** used in `app/routers/runs.py` (e.g., `app.routers.runs.execute_notebook`) with an **async** stub returning tiny strings for metrics/events/logs.
- In `conftest.py`, ensure dummy env vars are set:
  ```python
  import os; os.environ.setdefault("OPENAI_API_KEY","sk-test"); os.environ.setdefault("SUPABASE_URL","http://localhost"); os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY","test")
  ```
- Add `@pytest.mark.integration` + `@pytest.mark.skip` to long-running SSE tests; separate quick checks remain in the default suite.

**Acceptance:**
- `..\.venv\Scripts\python.exe -m pytest -q` finishes in seconds with green results.
- Optional: `pytest -m integration` runs the real SSE path locally only.

---

## 5) Prompt — **Operator runbook snippets (docs inline)**

**Intent:** Provide clean Windows commands for devs to run the pipeline end-to-end.

**Files:**
- `README.md` (operator quick start section)
- `docs/PLAYBOOK_MA.md`

**Insert the block below:**

```powershell
# Doctor
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor

# Ingest
$PDF="C:\path	o\paper.pdf"
$ing = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Deep Residual Learning (CVPR 2016)" `
  -F ("file=@`"" + $PDF + "`";type=application/pdf") | ConvertFrom-Json
$paper_id = $ing.paper_id

# Plan
$actor=[guid]::NewGuid().Guid
$planObj=@{ created_by=$actor; budget_minutes=5; claims=@(@{dataset="ImageNet";split="val";metric="top-1 accuracy";value=75.3;units="percent";citation="He16 T1";confidence=0.9}) }
$plan = Invoke-RestMethod -Method POST -Uri ("http://127.0.0.1:8000/api/v1/papers/{0}/plan" -f $paper_id) -Headers @{ "X-Actor-Id"=$actor } -ContentType "application/json" -Body ($planObj|ConvertTo-Json -Depth 10)
$plan_id = $plan.plan_id

# Materialize
curl.exe -sS -X POST ("http://127.0.0.1:8000/api/v1/plans/{0}/materialize" -f $plan_id)

# Assets (signed URLs)
curl.exe -sS ("http://127.0.0.1:8000/api/v1/plans/{0}/assets" -f $plan_id)
```

**Acceptance:**
- New hires can run the above exactly as-is on Windows.
- No secrets printed; doctor output redacted & boolean-only.

---

## 6) Prompt — **Minimal docs patch**

**Intent:** Update README and DB v0 notes to reflect the planner/materialize/assets routes and usage.

**Files:**
- `README.md`
- `docs/db-schema-v0.md`

**Tasks:**
- Add route list: `/api/v1/papers/{paper_id}/plan`, `/api/v1/plans/{plan_id}/materialize`, `/api/v1/plans/{plan_id}/assets` (+ example I/O).
- Clarify v0: tables used by plan/materialize/run, timestamps supplied by app, no RLS/FKs.

**Acceptance:**
- CI lints/format passes; docs render clean; examples are copy-pastable.
