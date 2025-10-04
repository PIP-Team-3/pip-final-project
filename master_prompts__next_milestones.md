
# MASTER PROMPTS — Next Milestones (Runner → Report → Kid‑Mode → Observability)
_Last updated: 2025‑10‑04_

## 0) Paste This “Context Hydration” at the Top of a Fresh Chat
**Project:** P2N (Paper‑to‑Notebook Reproducer)  
**Goal:** Ingest paper → extract claims → plan → materialize notebook + env → run in sandbox + stream SSE → compute reproduction gap → (Kid‑Mode Storybook).

**Stack:** FastAPI, Supabase (DB + Storage), OpenAI Python **1.109.1** (Responses mode), Windows dev (PowerShell).  
**Schema posture:** **v0** (no FKs/RLS/CHECK/UNIQUE/defaults). The app supplies all values.

**Non‑negotiables / Gotchas**
- **Responses + File Search (OpenAI 1.109.1):** put `attachments` **on the user message**; pass `tools=[{"type":"file_search"}]` top‑level.  
  _Never_ pass an `attachments=` kwarg to `client.responses.stream(...)`.
- **SSE vocabulary:** `stage_update`, `log_line`, `progress`, `metric_update`, `sample_pred` + final JSON payload.
- **Caps & guardrails:** enforce file_search caps (per‑run ≤ 10), typed errors, and trace labels (e.g., `policy.cap.exceeded`).
- **Windows:** PowerShell examples, `--workers 1` for stable SSE.
- **No schema changes (v0):** Use app‑level validation; no DB constraints.
- **Secrets:** No tokens in logs; redact vector_store_id, signed URL query strings, etc.

**Current state**
- Ingest + vector store + storage ✔
- Planner v1.1 ✔ (validated & persisted)
- Materialize + assets ✔ (signed URLs, TTL 120s)
- Unit tests ≈ **45 pass**, 2 integration SSE tests skipped by default
- Next milestones: **Runner** (C‑RUN‑01/02), **Report** (C‑REP‑01), **Kid‑Mode** (C‑KID‑01), **Observability** (C‑OBS‑01)

---

## MASTER PROMPT A — C‑RUN‑01: Sandbox Runner (Local Stub) + SSE Bridge

**Intent**
Execute the materialized notebook deterministically (local stub first), stream SSE (`stage_update`, `progress`, `log_line`, and any JSONL coming from the notebook as `metric_update`/`sample_pred`), and persist artifacts.

**Constraints**
- Use a **local runner stub** (no Docker yet): `nbclient` or `papermill` off‑line execution.
- Enforce wall clock timeout from the plan (`timeouts.wall_minutes`) with a firm kill.
- Persist artifacts in private Storage; mint signed URLs via verify route.
- **No GPUs** and **no internet** during execution.

**Touch points (edit/add)**
- `api/app/routers/runs.py` → `POST /api/v1/plans/{plan_id}/run`, `GET /api/v1/runs/{run_id}/events`
- `api/app/run/runner_local.py` → `async def execute_notebook(...) -> NotebookRunResult`
- `api/app/runs/manager.py` → simple per‑run event queue w/ history replay; `.send(run_id, event, data)` and `.close(run_id)`
- `api/app/data/supabase.py` → storage helpers: `upload_text`, `upload_bytes`, `sign_url`
- `api/app/data/models.py` → v0 run structs (no schema migration)
- `api/app/schemas/events.py` → JSON schema for `metric_update`, `sample_pred`, `progress`
- `api/tests/test_runs_stub.py`, `api/tests/test_runs_sse.py` → unit & (skipped) integration

**Implementation outline**
1. **Start endpoint**
   - Validate `plan_id`, fetch plan JSON + `env_hash` from DB; 404 → `E_PLAN_NOT_FOUND`.
   - Create `run_id` (UUID), insert run row with `status="queued"`, `env_hash`.
   - Spawn background task `_run_plan(...)` (async), return `202 { run_id }`.

2. **Background `_run_plan`**
   - `stage_update: run_start`
   - Download notebook (`plans/{plan_id}/notebook.ipynb`) to temp dir.
   - Execute notebook with **CPU only**, using `nbclient` (or papermill), hard timeout.
   - While running, pipe stdout/stderr into SSE `log_line`. If notebook writes `events.jsonl`, forward each line as SSE:
     - `metric_update` (schema: `{ name, value, split, step? }`)
     - `sample_pred` (schema: `{ id?, inputs?, outputs, refs? }`)
     - `progress` (`{ pct: 0..100, note? }`)
   - On success: write `metrics.json`, `events.jsonl`, `logs.txt` into `runs/{run_id}/` in Storage.
   - Update DB run row: `status="succeeded"`, `finished_at=now()`.
   - `stage_update: run_complete`, then `manager.close(run_id)` in finally.

3. **SSE endpoint**
   - On connect, replay any `history` buffered (first‑writer wins), then tail the queue until `close` sentinel.
   - Content‑Type `text/event-stream`; heartbeat every 15s to keep connections alive.

**Typed errors**
- `E_PLAN_NOT_FOUND` → 404
- `E_RUNNER_START_FAILED` → 500 (cannot spawn)
- `E_RUN_TIMEOUT` → 504 (kill run, persist partial logs)
- `E_ARTIFACT_WRITE_FAILED` → 502 (Storage down)

**Tests**
- Unit (fast): patch `app.routers.runs.execute_notebook` with **async stub** returning small `metrics_text`, `events_text`, `logs_text`. Assert:
  - POST returns `202` with `run_id`
  - SSE emits `run_start` then `run_complete`
  - Storage has `metrics.json` and `logs.txt`
  - DB row becomes `succeeded`
- Integration (skipped by default): exercise a tiny real notebook, tolerate 30–60 s.
- Negative: nonexistent `plan_id` → 404 typed error.

**Manual verification (PowerShell)**
```powershell
$plan_id = "<your plan id>"
$run = curl.exe -sS -X POST ("http://127.0.0.1:8000/api/v1/plans/{0}/run" -f $plan_id) | ConvertFrom-Json
$run_id = $run.run_id

# Stream events
curl.exe -N --http1.1 -H "Accept: text/event-stream" ("http://127.0.0.1:8000/api/v1/runs/{0}/events" -f $run_id)
```

**Acceptance**
- `202` on start; SSE shows `run_start` → (zero or more logs/progress) → `run_complete`
- `runs/{run_id}/metrics.json`, `runs/{run_id}/logs.txt`, optional `events.jsonl` in Storage
- Run row `status="succeeded"`; `finished_at` set

---

## MASTER PROMPT B — C‑RUN‑02: Determinism, CPU‑only, & Policy Enforcement

**Intent**
Guarantee deterministic runs, enforce CPU‑only, cap artifact sizes, and surface typed errors with clean trace labels.

**Constraints**
- Seeds must be set for `random`, `numpy`, **and** `torch` if present.
- CPU‑only: if GPU requested (torch.cuda.is_available() or env), raise `E_GPU_REQUESTED`.
- Cap final artifact sizes (e.g., logs ≤ 2 MiB, events ≤ 5 MiB); truncate with warning.

**Touch points**
- `api/app/run/runner_local.py` → seed setup & CPU enforcement
- `api/app/routers/runs.py` → pipeline stages and error mapping
- `api/app/schemas/events.py` → progress + metric formats
- `api/tests/test_runs_policy.py` → new tests

**Implementation outline**
1. `stage_update: seed_check` before execution; print versions in logs.
2. Verify CPU‑only; if GPU detected or requested, abort with typed error `E_GPU_REQUESTED`.
3. Enforce **artifact caps**; if exceeded, truncate and append `"__TRUNCATED__"` marker.
4. Attach `env_hash` to the run row for repro tracking.

**Typed errors**
- `E_GPU_REQUESTED`
- `E_ARTIFACT_TOO_LARGE`
- `E_RUN_TIMEOUT`

**Tests**
- Seeds present + notebook records same metric deterministically in back‑to‑back runs.
- Artificially large logs → stored file is truncated; SSE includes warning.
- GPU request mocked → `E_GPU_REQUESTED` returned, run marked `failed`.

**Acceptance**
- Deterministic metrics in `metrics.json` match SSE
- CPU‑only run verified; attempts to use GPU trip guardrail
- Oversized artifact truncated with warning

---

## MASTER PROMPT C — C‑REP‑01: Pro‑Mode Report (Reproduction Gap)

**Intent**
Compute gap vs the paper’s primary claim (from planner targets[0]) and expose a compact JSON report.

**Formula**
`gap_percent = (observed - claimed) / max(|claimed|, ε) * 100`

**Endpoint & touch points**
- `GET /api/v1/papers/{paper_id}/report`
- `api/app/routers/reports.py`, `api/app/services/reports.py`
- `api/app/data/supabase.py` → read runs + metrics; sign artifact URLs

**Implementation outline**
1. Locate the **latest successful run** for this paper (join via plan → paper link or store `paper_id` on run row in v0).
2. Read `metrics.json`; choose the primary metric from the plan or planner’s `targets[0]`.
3. Compute `gap_percent`; compose `{ claimed, observed, gap_percent, citations[], artifacts: {metrics_url, events_url} }`.
4. Persist a light `evals` row for history.

**Tests**
- Happy path with mock `metrics.json` and claimed; numeric stability around ε.
- No runs → 404 typed `E_REPORT_NO_RUNS`.
- Missing claimed value in plan → `E_REPORT_NO_CLAIM`.

**Acceptance**
- JSON response is stable and links to **signed** artifact URLs with short TTL
- Handles multiple runs, picking latest success

---

## MASTER PROMPT D — C‑KID‑01: Kid‑Mode Storybook (Static First)

**Intent**
Generate a 5–7 page storyboard JSON at grade‑3 reading level with alt‑text; update the final scoreboard page after run completes.

**Endpoints & touch points**
- `POST /api/v1/explain/kid` → returns `{ storyboard_id, pages:[], glossary:[] }`
- Persist `storyboards` in DB (v0) and Storage (`storyboards/{id}.json`)
- Update hook after run success to refresh the final scoreboard

**Constraints**
- Alt‑text mandatory; no personal images; neutral, encouraging tone.
- Two‑bar score on the final page: paper claim vs our run metric.

**Tests**
- Storyboard schema validation (pages, alt‑text present, glossary not empty)
- Update path after run completion updates last page with observed metric

**Acceptance**
- Endpoint returns valid storyboard JSON; Storage object exists
- After a successful run, final page is updated with the observed metric

---

## MASTER PROMPT E — C‑OBS‑01: Observability (Traces + Caps + Doctor)

**Intent**
Standardize traces, label policy cap trips, and reflect live environment in the doctor snapshot.

**Touch points**
- `api/app/config/llm.py` → `traced_subspan` utility; propagate trace ids
- `api/app/config/doctor.py` → clear caches; display: responses mode, tools enabled, client version, selected model
- Propagate `trace_id` on SSE headers if available

**Implementation outline**
- Span names: `p2n.run.start`, `p2n.run.exec`, `p2n.run.persist`, `p2n.report.compute`
- On caps: label `policy.cap.exceeded` and include a small **redacted** context object

**Tests**
- Doctor endpoint includes expected fields; booleans only, secrets redacted
- Cap trip writes the label; no tokens/ids in text logs

**Acceptance**
- Logs + traces show consistent naming and policy labels
- Doctor returns **live** settings (not cached) and version strings

---

## MASTER PROMPT F — Documentation Sweep (Public & Local Private)

**Intent**
Bring docs in sync and add a local private runbook (git‑ignored).

**Do**
- **Public** updates (`README.md`, `/docs/PLAYBOOK_MA.md`): endpoints, request/response examples, SSE usage, typed errors, manual Windows commands.
- **Local private runbook** (git‑ignored `LOCAL_RUNBOOK.md`): venv creation, `.env` loading, start server, doctor, ingest → plan → materialize → assets → run → report; common failures with exact remediation.

**Acceptance**
- Public docs do not leak secrets or signed URLs
- Private `LOCAL_RUNBOOK.md` is `.gitignore`d and contains exact step‑by‑step commands

---

## One‑liners to paste for each task

- **A (Runner stub + SSE):**  
  “Implement C‑RUN‑01: add `/api/v1/plans/{plan_id}/run` and `/api/v1/runs/{run_id}/events` using a local notebook runner with SSE bridge and artifact persistence. Enforce timeout, map events to `stage_update|log_line|progress|metric_update|sample_pred`, persist `metrics.json|events.jsonl|logs.txt`, return 202 with run_id, close SSE stream properly, add fast unit tests by mocking `app.routers.runs.execute_notebook`.”

- **B (Determinism/caps):**  
  “Implement C‑RUN‑02: add seed check for `random|numpy|torch`, enforce CPU‑only (raise `E_GPU_REQUESTED`), cap artifact sizes with truncation warnings, attach `env_hash` to run record. Add tests for deterministic metrics, GPU denial, log truncation.”

- **C (Report):**  
  “Implement C‑REP‑01: `GET /api/v1/papers/{paper_id}/report` computes gap vs claim using latest successful run’s `metrics.json`; return `{ claimed, observed, gap_percent, citations, artifacts }` with signed URLs. Add tests for happy, no runs, no claim.”

- **D (Kid‑Mode):**  
  “Implement C‑KID‑01: `POST /api/v1/explain/kid` creates a 5–7 page storyboard JSON (grade‑3 vocabulary, alt‑text); persist to Storage + DB; update final page after run completion with claim vs observed two‑bar score. Add schema tests.”

- **E (Observability):**  
  “Implement C‑OBS‑01: add `traced_subspan` spans for run pipeline, label `policy.cap.exceeded`, and expand doctor with live Responses mode flags, tools, client version, model. Redact secrets. Add tests.”

- **F (Docs):**  
  “Documentation sweep: public README + PLAYBOOK_MA with endpoint examples and typed errors; local `LOCAL_RUNBOOK.md` (git‑ignored) with Windows commands and troubleshooting. Ensure no secret leakage.”

---

## Guardrails & Risk Notes (do not skip)

- **OpenAI client pinned to 1.109.1** for Responses + Agents SDK 0.3.3 compatibility.
- **Responses usage**: attachments on user message; tools top‑level; file_search cap accounted.
- **Supabase Storage**: keep buckets private; sign URLs server‑side; never log query strings.
- **DB (v0)**: no constraints/migrations; hold integrity in code; typed errors everywhere.
- **SSE**: always close stream; heartbeat; map errors to final SSE then close.
- **Tests**: mock runners for speed; mark slow SSE as `@pytest.mark.integration`.
