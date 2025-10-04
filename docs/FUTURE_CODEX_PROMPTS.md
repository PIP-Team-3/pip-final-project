
# FUTURE_CODEX_PROMPTS.md
_Last updated: 2025-10-03 20:38:51_

## 0) Context Hydration (Paste this block at the top of any **fresh Codex chat**)

**Project:** P2N — Paper → Plan → Notebook → Run → Report (Kid‑Mode later)  
**Backend:** FastAPI + OpenAI Responses (Agents SDK compatible), Supabase (Postgres + Storage)  
**Status:** ✅ Ingest, ✅ Extractor (SSE + caps), ✅ Planner v1.1 persisted, ✅ Materialize (notebook + env), ✅ Assets (signed URLs).  
**Next:** Run (sandbox + SSE) → Determinism/policy → Report (gap) → Kid‑Mode.

**Non‑negotiable constraints (do not violate):**
- **Schema v0 posture:** Only `PRIMARY KEY(id)` in tables. **No** FK/RLS/CHECK/UNIQUE/defaults. App supplies all values (timestamps, logical refs).
- **Responses mode:** Use OpenAI **Python SDK 1.109.1** (Agents SDK 0.3.3 compatible). Upload PDFs with `purpose="assistants"`, then **attach** to Vector Stores for File Search.
- **Streaming vocabulary:** SSE events are **`stage_update`**, **`log_line`**, **`token`** (and in run phase, **`progress`**, **`metric_update`**, **`sample_pred`**).
- **Tool caps:** Enforce per‑run caps. If exceeded → typed error and **trace label** `policy.cap.exceeded`.
- **Secrets:** Never log secrets or signed URL tokens. Redact vector store IDs to 8 chars + `***`.
- **Versions:** `openai==1.109.1`, `openai-agents==0.3.3`, `httpx==0.28.x`, `supabase==2.20.x`, `storage3==2.20.x`. **Do not** upgrade to OpenAI 2.x on this branch.

**PR return format:**  
- Files changed (paths) + concise diff summary.  
- Tests (happy + one negative).  
- Manual verification commands (PowerShell + bash).  
- No schema changes unless explicitly asked.  

---

## 1) Execution Order (next 10 prompts)

1. **C‑RUN‑01** — Sandbox runner (local nbclient) + SSE bridge.  
2. **C‑RUN‑02** — Deterministic seeds, CPU‑only, timeouts, caps & artifacts policy.  
3. **C‑RUN‑EVT‑01** — Event schema + DB persistence (runs, run_events, run_series).  
4. **C‑RUN‑OBS‑01** — Tracing & logs polish for runs (p2n.run.*).  
5. **C‑RUN‑CTRL‑01** — Cancel/abort route & cleanup.  
6. **C‑REP‑01** — Reproduction gap report endpoint.  
7. **C‑REP‑02** — Report persistence + history.  
8. **C‑KID‑01** — Kid‑Mode storybook (generate/persist; update on run done).  
9. **C‑DOCS‑SYNC‑02** — Docs update for run/report/kid endpoints.  
10. **C‑SEC‑NEG‑02** — Negative tests sweep for runner & signed URLs.

> Optional queue (after the above): Docker worker, caching, retry, FE log pane, leaderboard, RLS prep migration, deploy scripts.

---

## 2) DETAILED PROMPTS

### C‑RUN‑01 | Sandbox runner (local) + SSE bridge
**Intent**  
Execute a materialized notebook deterministically **in‑process** using `nbclient` (no Docker yet) and stream SSE events to the client.

**Files to edit**  
- `api/app/routers/runs.py` — New routes:
  - `POST /api/v1/plans/{{plan_id}}/run` → starts a run, returns `{{ run_id }}`
  - `GET  /api/v1/runs/{{run_id}}/events` → SSE stream
- `api/app/run/runner_local.py` — The nbclient runner.
- `api/app/data/supabase.py` — Helpers to persist run rows & upload artifacts.
- `api/app/schemas/events.py` — JSONL event schema.
- `api/tests/test_runs_stub.py`, `api/tests/test_runs_sse.py` — Tests.

**Tasks**  
1. **Create run record**: generate `run_id` (UUID), insert into `runs` (schema v0). Fields: `id`, `plan_id`, `paper_id`, `status="pending"`, `env_hash`, `created_at`, `started_at` (nullable).  
2. **Runner** (`runner_local.py`):  
   - Load the materialized notebook (`plans/{{plan_id}}/notebook.ipynb`) via Supabase Storage (use a signed URL or server‑side fetch).  
   - Execute with `nbclient.NotebookClient`, timeout=plan.timeouts.wall_minutes × 60 (max cap 25 min).  
   - Capture **stdout/stderr** → forward to SSE as `log_line`.  
   - Capture notebook‑emitted JSONL events (if the notebook writes to `events.jsonl`, tail and forward).  
   - On finish, write `metrics.json` and `logs.txt` to `runs/{{run_id}}/` in Storage.
3. **SSE bridge**:  
   - Emit `stage_update: run_start`, periodic `progress` events (0–100), `log_line` lines, `stage_update: run_complete`.  
   - On exceptions: `stage_update: run_error` then close.
4. **Artifacts**: Persist to Storage under `runs/{{run_id}}/`:
   - `metrics.json`, `events.jsonl` (optional if notebook wrote them), `logs.txt`.  
   - Update run row `status="succeeded"/"failed"`, `completed_at`.
5. **Tracing**: use spans `p2n.run.exec`, with sub‑spans `p2n.run.nbclient.start`, `p2n.run.nbclient.finish`, `p2n.run.artifacts.persist`.

**Tests**  
- **Happy path**: mock a tiny notebook that prints two lines and writes a minimal `metrics.json`. Assert SSE contains `run_start` → `run_complete`; artifacts saved.  
- **Error path**: introduce an exception cell → SSE `run_error`; run status `failed`; artifacts include `logs.txt`.  
- **API**: `POST /plans/{{plan_id}}/run` returns a `run_id`; `GET /runs/{{run_id}}/events` streams events.

**Manual (PowerShell)**  
```powershell
$plan = "<your plan id>"
$run = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/plans/$plan/run | ConvertFrom-Json
$run_id = $run.run_id
curl.exe -N http://127.0.0.1:8000/api/v1/runs/$run_id/events
```

**Acceptance**  
- SSE shows `stage_update` + `log_line` + `progress`; notebook executed; artifacts exist in Storage.  
- Run row updated to succeeded/failed; trace visible with p2n.run.* spans.


---

### C‑RUN‑02 | Determinism, CPU‑only, timeouts & artifacts policy
**Intent**  
Enforce deterministic behavior and policy controls during run.

**Files**  
- `api/app/run/runner_local.py`  
- `api/app/routers/runs.py` (enforce caps)  
- `api/app/agents/definitions.py` (if planner/executor asks for GPU, block it)  
- `api/tests/test_runs_policy.py`

**Tasks**  
1. **Seeds**: Ensure notebook’s first cell sets seeds for `random`, `numpy`, and (if used) `torch`, `torch.cuda.manual_seed_all(0)` guarded; force CPU by setting env `CUDA_VISIBLE_DEVICES=""`.  
2. **CPU‑only**: If planner/env mentions CUDA/GPU, emit typed error `E_GPU_REQUESTED` and abort.  
3. **Timeout**: Enforce wall time from plan (`timeouts.wall_minutes`) with a hard cap (e.g., ≤25). On breach, kill execution and return `E_RUN_TIMEOUT`.  
4. **Artifacts policy**: Max sizes: `logs.txt ≤ 5 MB`, `events.jsonl ≤ 5 MB`. If exceeded → truncate tail and emit warning `E_ARTIFACT_TOO_LARGE (truncated)`.  
5. **Attach `env_hash`**: Persist `env_hash` from plan to the run row.

**Tests**  
- `test_seed_check_event` — SSE includes `stage_update: seed_check` and logs deterministic seed values.  
- `test_timeout_trips` — runner exceeds timeout → `E_RUN_TIMEOUT`, `status=failed`.  
- `test_gpu_request_blocked` — mock plan requests GPU → `400` with `E_GPU_REQUESTED`.  
- `test_artifact_truncate` — oversized logs truncated with warning banner.

**Acceptance**  
- Deterministic seeds logged; policy errors typed; artifacts truncated when too large.


---

### C‑RUN‑EVT‑01 | Event schema + DB persistence
**Intent**  
Define and persist structured run events and series points to DB during run.

**Files**  
- `api/app/schemas/events.py` — Define Pydantic models for events.  
- `api/app/routers/runs.py` — Hook persistence calls.  
- `api/app/data/supabase.py` — Insert helpers for `run_events` and `run_series`.  
- `api/tests/test_run_events_persist.py`

**Event JSONL schema**  
```json
{"type":"metric_update","ts":"<iso>","metric":"accuracy","value":0.71,"split":"val"}
{"type":"progress","ts":"<iso>","percent":42}
{"type":"sample_pred","ts":"<iso>","text":"it is positive"}
```

**Tasks**  
1. **Parse JSONL**: The runner tails `events.jsonl` if present and forwards each line to SSE while also writing to DB (schema v0).  
2. **DB writes**:  
   - `run_events`: raw event envelope (type, ts, payload, run_id).  
   - `run_series`: for `metric_update` events, store `(run_id, ts, metric, split, value, step)`; step is a monotonic counter.  
3. **Idempotency**: Accept duplicates but de‑dupe by `(run_id, ts, metric, split, value)` in memory for the session. (No DB constraints in v0.)

**Tests**  
- `test_metric_events_persisted` — After a run, query DB helper (mocked) shows event rows and series rows count > 0.  
- `test_replay_stable` — Replaying the SSE transcript results in the same set of DB writes (no duplicates beyond session).

**Acceptance**  
- SSE and DB reflect the same events; series points visible via a helper endpoint (optional).


---

### C‑RUN‑OBS‑01 | Tracing & logs polish
**Intent**  
Unify tracing labels and log redaction for the run phase.

**Files**  
- `api/app/config/llm.py` — add `traced_subspan` helpers if missing.  
- Logging config (if present) — ensure no secrets.  
- `api/tests/test_tracing_labels.py`

**Tasks**  
- Use spans `p2n.run.start`, `p2n.run.nbclient`, `p2n.run.persist`, `p2n.run.finish`.  
- Redact any vector store IDs in run logs with the existing `redact_vector_store_id`.  
- Include run_id, plan_id in structured logs.

**Acceptance**  
- Traces appear in OpenAI dashboard (for LLM invocations around plan context if any); server logs have consistent fields and no secrets.


---

### C‑RUN‑CTRL‑01 | Cancel/abort
**Intent**  
Allow an in‑flight run to be cancelled gracefully.

**Files**  
- `api/app/routers/runs.py` — `POST /api/v1/runs/{{run_id}}/cancel`  
- `api/app/run/runner_local.py` — add cooperative cancel support  
- `api/tests/test_runs_cancel.py`

**Tasks**  
- Maintain a map of `run_id → task handle`. On cancel, signal runner to stop at next safe boundary; update status `cancelled`.  
- SSE emits `stage_update: run_cancelled`.  
- Persist partial artifacts and logs.

**Acceptance**  
- Cancel request returns 202; SSE shows cancellation; status becomes `cancelled`.


---

### C‑REP‑01 | Reproduction gap report
**Intent**  
Compute the gap between the paper’s primary claim and the latest successful run.

**Files**  
- `api/app/routers/reports.py` — `GET /api/v1/papers/{{paper_id}}/report`  
- `api/app/services/reports.py`  
- `api/tests/test_report.py`

**Tasks**  
1. From planner `targets[0]` read the **primary metric** and claimed value (with citation).  
2. Read the latest successful run’s `metrics.json` → observed metric.  
3. Compute `gap = (observed - claimed) / max(|claimed|, 1e-9) * 100`.  
4. Return JSON: `{{ claimed, observed, gap_percent, citations, artifacts: {{metrics, events}} }}`.  
5. Optionally write an `evals` row (schema v0).

**Manual**  
```powershell
curl.exe -sS http://127.0.0.1:8000/api/v1/papers/$paper/report
```

**Acceptance**  
- Numbers match `metrics.json`; citations come from the extractor claim; signed URLs to artifacts included.


---

### C‑REP‑02 | Report persistence + history
**Intent**  
Store report snapshots and expose run history.

**Files**  
- `api/app/routers/reports.py` — `GET /api/v1/papers/{{paper_id}}/runs`  
- `api/app/data/supabase.py` — helpers to read last N runs  
- `api/tests/test_report_history.py`

**Tasks**  
- Return list of runs with key metrics, timestamps, env_hash.  
- (Optional) Persist computed gaps to a `reports`/`evals` table for later leaderboards.

**Acceptance**  
- Endpoint returns ordered history; FE can render quickly.


---

### C‑KID‑01 | Kid‑Mode storybook
**Intent**  
Create a 5–7 page storyboard JSON (grade‑3 voice, alt‑text required), then update last page after run completion.

**Files**  
- `api/app/routers/explain.py` — `POST /api/v1/explain/kid`  
- `api/app/services/explain_kid.py`  
- `api/tests/test_explain_kid.py`

**Tasks**  
- Prompt LLM to produce pages with `{{title, body, alt_text, visual_hint}}`; glossary terms list.  
- Persist storyboard JSON to Storage and a `storyboards` row (schema v0).  
- After run finishes, write a small updater that amends the final page with our score vs paper’s claim (two‑bar chart description).

**Acceptance**  
- Endpoint returns `storyboard_id` and signed URL to JSON; alt‑text present for every visual.


---

### C‑DOCS‑SYNC‑02 | Docs update for run/report/kid
**Intent**  
Refresh docs to include the new endpoints and manual flows.

**Files**  
- `README.md`, `docs/API.md` (or `api/README.md`), `docs/PLAYBOOK_MA.md`, `docs/FUTURE_CODEX_PROMPTS.md`

**Tasks**  
- Add new routes, example curls, SSE transcripts.  
- Update Quickstart to include run → report chain.  
- Troubleshooting for timeouts, cancel, oversized artifacts.

**Acceptance**  
- Docs match live responses and paths; copy‑paste works.


---

### C‑SEC‑NEG‑02 | Negative tests & redaction sweep
**Intent**  
Broaden negative coverage and ensure redaction consistency across run/report.

**Files**  
- `api/tests/test_runs_negative.py`, `api/tests/test_signed_urls.py`  
- `api/app/utils/redaction.py`

**Tasks**  
- Bad plan_id / missing assets → typed errors.  
- Signed URL TTL expiry case documented; tokens never logged.  
- Redaction helper used in all new logs.

**Acceptance**  
- All tests green; grep logs show no secrets or token query strings.


---

## 3) SSE Event Shapes (for reference)

```text
event: stage_update
data: {"stage":"run_start","run_id":"<uuid>"}

event: progress
data: {"percent": 42, "msg": "epoch 1/3"}

event: log_line
data: "Downloading dataset..."

event: metric_update
data: {"metric":"accuracy","split":"val","value":0.71,"ts":"<iso>"}

event: sample_pred
data: {"text":"resnet predicts 'cat' with 0.91"}

event: stage_update
data: {"stage":"run_complete","run_id":"<uuid>"}
```

---

## 4) PR Checklist (Codex must validate before “done”)

- [ ] Routes respond with documented shapes; SSE uses correct event names.  
- [ ] Tests: happy + at least one negative per endpoint.  
- [ ] Manual commands (PowerShell + bash) verified locally.  
- [ ] Traces use `p2n.run.*` labels.  
- [ ] No schema rules added (v0 posture maintained).  
- [ ] No secrets or tokens in logs or docs.  
- [ ] Vector store IDs redacted.  
