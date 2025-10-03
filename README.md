# P2N Monorepo

The Paper-to-Notebook (P2N) project turns a research paper PDF into a deterministic reproduction plan, notebook, and run pipeline. The current implementation covers the first three stages of the roadmap—ingest ? extract ? plan/materialize—and exposes deterministic stubs for notebook execution.

## What’s Implemented Today

| Stage | Description | Key Endpoints | Artifacts |
|-------|-------------|---------------|-----------|
| Ingest | Upload a PDF, store it in Supabase Storage, attach it to an OpenAI File Search vector store, and persist paper metadata. | `POST /api/v1/papers/ingest`  | Supabase storage path, vector store id |
| Verify | Confirm the paper’s storage/vector store references without exposing secrets. | `GET /api/v1/papers/{paper_id}/verify` | Boolean status report |
| Extract | Stream claim extraction via SSE. The extractor agent uses File Search, enforces tool caps, and emits structured `claims[]{dataset, split, metric, value, units, citation, confidence}`. | `POST /api/v1/papers/{paper_id}/extract` | SSE stages, typed errors (e.g., `E_EXTRACT_LOW_CONFIDENCE`) |
| Plan | Planner agent returns a Plan JSON v1.1 document with dataset/model/config/metrics/visualizations/explain/justifications. Stored in the `plans` table (schema v0: only `PRIMARY KEY(id)`). | `POST /api/v1/papers/{paper_id}/plan` | Plan JSON persisted with logical `paper_id` reference |
| Materialize | Convert a stored plan into a deterministic notebook + requirements set. Notebook cells seed RNGs, log SSE-style events, and produce `metrics.json` when executed. | `POST /api/v1/plans/{plan_id}/materialize` | Supabase assets under `plans/{plan_id}/` |
| Verify Plan Assets | Issue short-lived signed URLs for the notebook and requirements artifacts. | `GET /api/v1/plans/{plan_id}/assets` | Signed URLs (120 s TTL) with tokens redacted in logs |
| Run Stub | Launch a simulated run, stream SSE via `/api/v1/runs/{run_id}/events`, and persist metrics/events/log artifacts. This will be replaced by a sandbox worker in C-RUN-01. | `POST /api/v1/plans/{plan_id}/run` | `runs/{run_id}/metrics.json`, `events.jsonl`, `logs.txt` |

All persistence adheres to the “No-Rules v0” posture: tables define `PRIMARY KEY(id)` only, no foreign keys, defaults, RLS, or advanced constraints. Application code supplies every value explicitly (including timestamps and UUIDs).

## Directory Map

- `api/` – FastAPI service housing agents, routes, Supabase wrappers, and SSE streaming utilities.
  - `app/materialize/` – Notebook/env generation utilities (Plan JSON ? notebook.ipynb + requirements.txt).
  - `app/runs/` – In-memory SSE manager for run streaming.
  - `app/routers/` – Public HTTP surface (`papers`, `plans`, `runs`, `internal`).
  - `app/data/` – Typed Supabase wrappers and pydantic models (`PaperCreate`, `PlanCreate`, `RunCreate`, etc.).
  - `tests/` – Pytest suites for ingest, extract, plan, materialize, and run stubs.
- `worker/` – Placeholder for the future sandbox runner (to be filled in during C-RUN-01).
- `web/` – Placeholder React client.
- `sql/` – Schema v0 reference files and reset scripts (documentation only; no migrations applied automatically).
- `infra/` – Skeleton for IaC and deployment workflows.

## Environment & Dependencies

1. Create `.env` from `.env.example` and populate:
   ```dotenv
   OPENAI_API_KEY=sk-...
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=...
   SUPABASE_ANON_KEY=...
   FILE_SEARCH_PER_RUN=10
   WEB_SEARCH_PER_RUN=5
   OPENAI_TRACING_ENABLED=true
   ```
2. Install API requirements (Python 3.12.5):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r api/requirements.txt
   ```
3. Optional developer extras (`nbformat` already pinned for notebook work).

## Running the Services

```powershell
# start API with deterministic SSE (reload disabled keeps streams stable)
python -m uvicorn app.main:app --app-dir api --log-level info

# run worker stub (currently no-op)
make worker

# serve example web client shell
make web
```

## End-to-End Manual Flow (PowerShell)

```powershell
# 1. Ingest a paper PDF
$PDF = "C:\path\to\paper.pdf"
$ingest = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Demo Paper" `
  -F ("file=@`"$PDF`";type=application/pdf")
$paper_id = ($ingest | ConvertFrom-Json).paper_id

# 2. Verify storage / vector store references (no secrets returned)
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/$paper_id/verify"

# 3. Stream extractor SSE (claims + guardrails)
curl.exe -N "http://127.0.0.1:8000/api/v1/papers/$paper_id/extract"

# 4. Generate a Plan JSON v1.1
touch plan.json  # optional local capture
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/papers/$paper_id/plan" `
  -H "Content-Type: application/json" `
  -d '{"claims":[{"dataset":"demo","split":"test","metric":"accuracy","value":0.8,"units":"fraction","citation":"p.2","confidence":0.9}]}'

# 5. Materialize notebook + requirements
$plan_id = <plan uuid from previous response>
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/materialize"

# 6. Fetch signed asset URLs (120-second TTL)
curl.exe -sS "http://127.0.0.1:8000/api/v1/plans/$plan_id/assets"

# 7. Kick off the run stub and watch SSE
t$run = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/run" | ConvertFrom-Json
curl.exe -N "http://127.0.0.1:8000/api/v1/runs/$($run.run_id)/events"
```

All SSE streams follow the vocabulary: `stage_update`, `log_line`, `token` (delta output), `metric_update`, `sample_pred`, and final `result` payloads. Typed errors (e.g., `E_POLICY_CAP_EXCEEDED`, `E_PLAN_NOT_FOUND`, `E_RUN_TIMEOUT`) surface structured remediation messages.

## Testing & Quality Gates

- Run the full API suite: `.\.venv\Scripts\python.exe -m pytest -q`
- Key targeted tests:
  - `test_papers_ingest.py` – ingest / verify flows and negative paths.
  - `test_papers_extract.py` – SSE, guardrail enforcement, policy caps.
  - `test_plans_materialize.py` – notebook/env generation and signed URL verification.
  - `test_runs_stub.py` – run initiation + SSE stub behaviours.

CI expectations for every PR:
1. Provide a diff summary of files touched.
2. Include happy-path + at least one negative-path test.
3. Document manual verification steps in the PR body.
4. Never leak secrets in logs or responses (vector_store IDs must be redacted to `abcd1234***`).

## Observability & Tracing

- `app/config/llm.py` wraps OpenAI client calls with `traced_run` / `traced_subspan`. Spans currently used:
  - `p2n.extractor.run`
  - `p2n.planner.run`
  - `p2n.materialize.codegen`
  - `p2n.materialize.persist`
  - Run stub spans will evolve in C-RUN-01 (`p2n.run.*`).
- Disable tracing by setting `OPENAI_TRACING_ENABLED=false` in `.env` if necessary.

## Data & Storage Layout

- Supabase Storage keys:
  - `papers/dev/YYYY/MM/DD/{paper_id}.pdf`
  - `plans/{plan_id}/notebook.ipynb`
  - `plans/{plan_id}/requirements.txt`
  - `runs/{run_id}/metrics.json`, `events.jsonl`, `logs.txt`
- Database (schema v0): tables such as `papers`, `plans`, `runs`, `run_events`, `run_series` only define `id` primary keys. No default values, no referential integrity – every field must be populated from the app.

## Roadmap Snapshot

Upcoming prompts (see `docs/FUTURE_CODEX_PROMPTS.md` for full detail):
1. C-RUN-01 – turn the run stub into a deterministic sandbox executor with artifact persistence.
2. C-RUN-02 – enforce deterministic seeds, CPU-only execution, and policy caps.
3. C-REPORT-01 – compute reproduction gap reports per paper.
4. C-KID-01 – generate/update Kid-Mode storybooks alongside run completion.

## Reference Commands

```powershell
# OpenAI config doctor
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor

# Health checks
curl.exe -sS http://127.0.0.1:8000/health
curl.exe -sS http://127.0.0.1:8000/health/live
```

Remember: stay on `openai==1.109.1` / `openai-agents==0.3.3` until the dedicated migration prompt lands, and keep the database in “No-Rules v0” until the Schema Hardening milestone explicitly authorizes upgrades.
