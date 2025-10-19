
# P2N (Paper‑to‑Notebook) — Soup‑to‑Nuts Overview (Clean Branch)

**Audience:** New and existing engineers, PMs, and the parallel Front‑End team  
**Branch:** `clean/phase2-working`  
**Status:** Phase 1 ✅ (Extractor), Phase 2 Micro‑Milestone 1 ✅ (Smart dataset selection + materialize), next up: Phase 2 M2 & Phase 3

---

## TL;DR (Executive Summary)

- **What P2N is:** A backend service that turns a research **paper + claim** into a runnable, deterministic **Jupyter notebook** that approximates the paper’s experiment under a **20‑minute CPU budget**.  
- **Why:** To *test* claims quickly, show where reproduction gaps might be, and make results accessible (and explorable) by others.  
- **How:** 
  - **Agents (LLMs) for reasoning:** Extract the claim(s) and plan a reproduction.  
  - **Generators (code templates) for reliability:** Deterministically produce runnable notebooks + requirements from the plan.  
- **What works now:** End‑to‑end pipeline on our clean branch:
  - Ingest PDF → index with OpenAI File Search.
  - Extract claims (**Agent: Extractor**) → **saved to DB** (idempotent).
  - **Plan** via two‑stage (**o3-mini** for reasoning, **gpt‑4o** for schema‑correct JSON).  
  - **Materialize** a notebook using **smart dataset selection** (HuggingFace/Torchvision/sklearn) with **lazy loading and caching**.
  - Store artifacts in Supabase Storage (buckets: `papers`, `plans/assets`, `storyboards`).  
- **What’s next:** Expand datasets (Phase 2 M2), add smart models (Phase 3: TextCNN/ResNet), build the sandbox **executor** (Phase 4), then **gap analysis** and **kid‑mode summaries** (Phase 5).  
- **Front‑End:** Can work *in parallel* today using the REST + SSE contract; no need to wait for backend milestones.

---

## The Problem P2N Solves

Research papers report results like *“CNN‑multichannel achieves **88.1%** on **SST‑2 (test)**.”*  
**Reality:** reproducing the exact setup is hard—data variants, splits, pre‑processing, models, and training tricks vary; hardware differs.  
**Our solution:** produce a **bounded, standardized reproduction**:
- Uses **datasets the paper mentions** when possible.
- Keeps **runs ≤ 20 minutes (CPU)** for practicality.
- **Logs metrics** and **emits traces** so we can explain differences.
- Stays **deterministic**: same random seed, reproducible environment.
- Returned assets: **notebook**, **requirements**, **metrics**, **logs**.  

We’re not claiming perfect, line‑by‑line replication. We aim for a *faithful sanity check* and a **consistent apples‑to‑apples** comparison.

---

## The End‑to‑End Pipeline

### 1) Ingest (no agent)

- Upload a PDF to Supabase Storage (`papers` bucket), create an **OpenAI vector store**, and index the PDF for **File Search**.  
- Create a **papers** row with `vector_store_id`, file hash, and metadata.  
- *Artifacts:* Paper in Storage; vector store id in DB.

### 2) Extract (Agent: **Extractor**, model: gpt‑4o)

- Uses **File Search** to scan tables/sections.  
- Emits **structured claims** with dataset name, metric name/value, split, citation, and confidence.  
- **Saves claims to DB** (idempotent “replace” policy; shows `persist_start`/`persist_done` over SSE).  
- *Artifacts:* `claims` rows in DB.

### 3) Plan (Agent: **Planner**, two‑stage)

- **Stage 1 (Reasoning):** `o3-mini` reads paper via File Search, writes a detailed NL plan + justifications (quotes + citations).  
- **Stage 2 (Schema Fixer):** `gpt‑4o` converts Stage 1 output to **Plan JSON v1.1** (using structured outputs) with typed fields.  
- **Validates:** Pydantic schema; saves plan in `plans`.  
- *Artifacts:* Plan JSON in DB (`plans.plan_json`, versioned).

### 4) Materialize (Generators)

- **GeneratorFactory** picks dataset + model generators:
  - **Datasets:** HuggingFace (`load_dataset`), Torchvision (`MNIST`, `CIFAR10`), sklearn (`load_digits`), or **Synthetic fallback**.  
  - **Models:** Currently **sklearn LogisticRegression** (Phase 2 baseline); Phase 3 adds TextCNN/ResNet.  
- Produces **notebook code** + **requirements.txt** with **lazy loading** & **cache** (`DATASET_CACHE_DIR`, `OFFLINE_MODE`, `MAX_TRAIN_SAMPLES`).  
- Uploads to Supabase **plans/assets** bucket; records in `assets`.  
- *Artifacts:* `notebook.ipynb`, `requirements.txt` in Storage; `assets` rows.

### 5) (Upcoming) Run & Evaluate

- **Phase 4:** A sandbox executor will run notebooks deterministically (CPU), stream **run_events** (SSE), log **metrics**, and produce `run_series`.  
- **Phase 5:** Compare observed vs claimed (gap analysis), generate a **kid‑mode storyboard**.

---

## Why **Agents** for Reasoning and **Generators** for Code?

- **Agents** (Extractor, Planner) need deep reading, synthesis, judgment → LLMs shine here.  
- **Generators** produce working code repeatedly → deterministic templates are safer, faster, testable.  
- We switched away from “agent writes code” to **generators** to avoid brittle, non‑deterministic notebooks.

**Two‑Stage Planner** was key: o3‑mini does the deep read; gpt‑4o enforces strict JSON schema — fixed earlier failures where numeric fields came back as strings.

---

## What’s Working Today (Clean Branch)

- **Phase 1** (Extractor): End‑to‑end, claims persisted; **idempotent**.  
- **Phase 2, Micro‑Milestone 1** (Dataset selection + materialization):  
  - Plan → Notebook for **SST‑2** uses **HuggingFace** with `cache_dir`, `reuse_dataset_if_exists`, `OFFLINE_MODE`.  
  - **No synthetic fallback** when dataset is recognized.  
  - Storage fixes: correct bucket (`plans`), correct MIME types; duplicate upload handled.  
- **Supabase SDK compatibility** fix in DB helper; **storage path** duplication removed.  
- **CI tests** passing for generators + materialization path.  

---

## Repo Layout (what matters now)

```
clean/phase2-working/
├── api/
│   ├── app/
│   │   ├── agents/                 # Extractor + Planner (two-stage)
│   │   ├── config/                 # Settings, model names, feature flags
│   │   ├── data/                   # Supabase client, DB/storage helpers
│   │   ├── materialize/
│   │   │   └── generators/         # dataset/model factories & code gens
│   │   ├── routers/                # FastAPI endpoints (ingest, extract, plan, materialize)
│   │   ├── runs/                   # SSE streaming utilities
│   │   ├── schemas/                # Pydantic models (Plan v1.1, Claims, etc.)
│   │   ├── services/               # file_search, reports, kid explainer (stubs)
│   │   └── utils/                  # redaction, helpers
│   └── tests/                      # Unit/integration tests
├── sql/
│   ├── schema_v1_nuclear_with_grants.sql  # DB schema + grants + buckets
├── scripts/
│   └── reingest_paper_set_v1.py    # Batch ingest helper
├── docs/Claudedocs/                # Working logs, roadmaps, status
├── assets/papers/                  # Local PDFs for ingest
└── manage.py, Makefile, README.md, etc.
```

**DB tables** (quick view): `papers`, `claims`, `plans`, `assets` (today). Upcoming: `runs`, `run_events`, `run_series`, `evals`, `storyboards`.

**Storage buckets** (created by schema script):
- `papers` → only **`application/pdf`** (strict by design).  
- `storyboards` → JSON, text (for kid‑mode later).  
- `assets` (aka `plans` in code) → notebooks/requirements/logs/metrics with `application/json`, `text/plain`, `application/x-ipynb+json`, etc.

---

## Environment & Configuration

**Required env vars (server side, not exposed to FE):**
```
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_ANON_KEY=...
OPENAI_API_KEY=...
```

**Model selection (current):**
- Extractor: `gpt-4o` (tool + function‑calling friendly).  
- Planner Stage 1: `o3-mini` (reasoning), **web_search filtered out**.  
- Planner Stage 2: `gpt-4o` with **structured outputs** (Responses API).  

**Determinism & resource caps (recommended in `.env`):**
```
SEED=42
OMP_NUM_THREADS=8
OPENBLAS_NUM_THREADS=8
MKL_NUM_THREADS=8
NUMEXPR_NUM_THREADS=8
DATASET_CACHE_DIR=./data/cache
OFFLINE_MODE=false
MAX_TRAIN_SAMPLES=8000
CUDA_VISIBLE_DEVICES=      # (empty for CPU-only default)
```

---

## How to Run Locally (Developer Quickstart)

1) **Setup**
```bash
py -m venv .venv
.\.venv\Scripts\pip install -U pip
.\.venv\Scripts\pip install -r requirements.txt  # from repo
# Ensure SUPABASE + OPENAI env vars are set
# Apply DB schema once to your Supabase project:
#   sql/schema_v1_nuclear_with_grants.sql
```

2) **Start the API**
```bash
# Windows PowerShell
$env:OMP_NUM_THREADS="8"; $env:OPENBLAS_NUM_THREADS="8"; $env:MKL_NUM_THREADS="8"; `
$env:NUMEXPR_NUM_THREADS="8"; $env:DATASET_CACHE_DIR="./data/cache"; `
$env:MAX_TRAIN_SAMPLES="8000"; $env:OFFLINE_MODE="false"; $env:CUDA_VISIBLE_DEVICES=""; `
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info
```

3) **Health checks**
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/internal/config/doctor
```

4) **Ingest a paper**
- Put PDFs under `assets/papers/` (e.g., TextCNN, ResNet, fastText).  
- Use the script (adjust flags if needed):
```bash
.\.venv\Scripts\python.exe scripts/reingest_paper_set_v1.py --folder assets/papers
```
- Or, if you prefer API, use the ingest endpoint (see API docs if enabled).

5) **Extract claims**
```bash
# Replace PAPER_ID with the returned UUID
curl -N -X POST "http://127.0.0.1:8000/api/v1/papers/PAPER_ID/extract"
# Look for SSE events: extract_start → persist_start → persist_done → extract_complete
# Verify saved claims:
curl "http://127.0.0.1:8000/api/v1/papers/PAPER_ID/claims"
```

6) **Plan**
```bash
# Provide a small list of the claims you want to reproduce (or let server fetch by paper_id)
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/PAPER_ID/plan" \
  -H "Content-Type: application/json" \
  -d "{\"claims\": [{\"dataset\":\"SST-2\",\"split\":\"test\",\"metric\":\"accuracy\",\"value\":88.1,\"units\":\"%\",\"citation\":\"Table 2\",\"confidence\":0.9}]}"
# Response includes: plan_id
```

7) **Materialize**
```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/plans/PLAN_ID/materialize"
# On success: notebook + requirements stored in Supabase (`plans/assets` bucket)
```

> **Note:** The “Run” step is stubbed for now (Phase 4). You can download the notebook and run it locally or inside your own Jupyter.

---

## API Contract (for the Front‑End Team)

> The FE team can build **today** against these endpoints. No DB/Storage direct access required; everything is via the API.

**Health & Config**
- `GET /health` → `{ "status": "ok", "tracing_enabled": true }`  
- `GET /internal/config/doctor` → sanity & capabilities (for a diagnostics screen).

**Papers & Claims**
- `POST /api/v1/papers/ingest` *(if enabled)* → create a paper (otherwise use script).  
- `POST /api/v1/papers/{paper_id}/extract` *(SSE)* → emits `stage_update`, then returns `{ claims: [...] }`.  
- `GET  /api/v1/papers/{paper_id}/claims` → `{ claims_count, claims: [...] }`

**Planning**
- `POST /api/v1/papers/{paper_id}/plan` → returns `{ plan_id, plan_version, ... }`  
  - Handles two‑stage planner internally; returns **validated** Plan v1.1.

**Materialization**
- `POST /api/v1/plans/{plan_id}/materialize` → creates notebook + requirements assets.  
  - Returns storage paths (or a signed URL in later versions).

**(Future) Runs & Metrics**
- `POST /api/v1/plans/{plan_id}/run` *(SSE)* → will stream `run_events`.  
- `GET  /api/v1/runs/{run_id}/metrics` → will return observed metrics.  
- `GET  /api/v1/runs/{run_id}/events` → will return event log.  

**SSE (consumption in FE)**
```ts
const sse = new EventSource(`/api/v1/papers/${paperId}/extract`);
sse.onmessage = (ev) => { /* handle 'result' */ };
sse.addEventListener('stage_update', (ev) => {
  const data = JSON.parse(ev.data);
  // stages: extract_start, file_search_call, persist_start, persist_done, extract_complete
});
sse.onerror = () => sse.close();
```

**Auth note:** The backend holds the Supabase service role + OpenAI keys; FE should **not** use them directly. Use backend endpoints only.

---

## What Changed Recently (so you don’t trip on old docs)

- **Structured outputs** for Planner Stage 2 (Responses API) to fix numeric type issues.  
- **Supabase SDK fix:** removed `select()` after `update().eq()` chain to match current client behavior.  
- **Storage paths:** removed double `plans/` prefix; now correct bucket + path structure.  
- **Claims persistence:** added explicit `persist_start`/`persist_done` events; **replace** policy (delete → insert) for idempotency.

---

## Roadmap (Next Milestones)

### Phase 2 — Micro‑Milestone 2: **Datasets++**
- **Add registry entries:** CoLA, MNLI, SQuAD (HF); CIFAR‑100, SVHN (Torchvision); sklearn toy datasets.  
- **Acceptance:** Materialize a plan for each new dataset; notebooks show correct loader code; no synthetic fallback for known datasets.  
- **Tests:** Unit tests for registry lookup + generator selection; “no download” unit tests; smoke notebooks for tiny datasets.

### Phase 3 — **Smart Models**
- **Generators:** `TorchCNNGenerator` (TextCNN), `TorchResNetGenerator` (ResNet‑18/34), `SklearnModelGenerator` (SVM, RF).  
- **Factory logic:** map plan.model → correct generator; fallbacks.  
- **Acceptance:** Materialize working notebooks for TextCNN (SST‑2) & ResNet (CIFAR10).  
- **Determinism:** fixed seeds; capped epochs; subsampling gate via `MAX_TRAIN_SAMPLES`.

### Phase 4 — **Executor (Sandbox)**
- **CPU‑only runner:** execute notebook in container/worker; stream `run_events`; persist `metrics` and `run_series`.  
- **Time budget:** enforce 20‑minute cap; graceful cancellation; logs.  
- **Acceptance:** Reproducible results across runs; metrics stored & viewable.

### Phase 5 — **Gap Analysis & Storyboards**
- **Gap analyzer:** compare observed vs claimed; compute % gap; include confidence bounds.  
- **Kid‑mode storyboard:** generate 5–7 pages explaining the experiment; store in `storyboards`.  
- **Acceptance:** End‑to‑end: ingest → extract → plan → materialize → run → scoreboard + kid‑mode PDF.

**Always‑on tasks:** hardening, retry policies, telemetry, doc polish, FE contract additions (list endpoints for papers/plans).

---

## Parallel Workstreams (How FE Can Move Now)

- **Contract‑first UI:** Build pages that call:
  1) **Ingest** screen → upload PDF (or pick existing).  
  2) **Claims** screen → run extraction (SSE), show list with citations.  
  3) **Plan** screen → pick claim(s), run planner, show justifications with quotes.  
  4) **Materialize** screen → render links to notebook + requirements; allow download.  
  5) **(Future) Run** screen → stream training/metrics; show final accuracy vs claim.  

- **SSE Helpers:** a small wrapper to consume `stage_update`, `log_line`, `metric_update` events.  
- **Mock Mode:** Use saved JSON responses in FE to build UI states; switch to live API later.  
- **OpenAPI/Docs:** FastAPI `/docs` is live for self‑serve; we can add a minimal typed client for TS if desired.

**Backend BFF stays private:** FE never touches Supabase Storage or DB directly; backend will mint signed URLs later if needed.

---

## Troubleshooting (Known Issues & Fixes)

- **400 “web_search not supported with o3-mini”:** we filter web_search for Stage 1.  
- **422 Plan schema invalid (numbers as strings):** fixed by structured outputs in Stage 2.  
- **409 Duplicate on storage upload:** handled with correct update/upsert logic.  
- **MIME type rejected:** keep PDFs in `papers` bucket; notebooks/reqs in `plans/assets` bucket.  
- **Empty DB on new machine:** re‑ingest PDFs (`scripts/reingest_paper_set_v1.py`) — vector stores are not portable across machines unless re‑created.  

---

## Appendices

### A) Event Types (Extractor today; Runner later)
- `stage_update` → `{ stage: "extract_start" | "file_search_call" | "persist_start" | "persist_done" | "extract_complete" }`
- `result` → `{ claims: [...] }`
- *(Runner later: `progress`, `metric_update`, `sample_pred`, `error`)*

### B) Plan v1.1 (shape excerpt)
```json
{
  "version": "1.1",
  "dataset": { "name": "sst-2", "split": "train/test", "filters": [] },
  "model": { "name": "cnn", "variant": "multichannel", "parameters": { "filter_widths": 3, "feature_maps": 100, "dropout_rate": 0.5 } },
  "config": { "framework": "pytorch", "epochs": 10, "batch_size": 50, "optimizer": "Adadelta" },
  "metrics": [{ "name": "accuracy", "split": "test" }],
  "justifications": {
    "dataset": { "quote": "...", "citation": "Section X" },
    "model": { "quote": "...", "citation": "Table Y" },
    "config": { "quote": "...", "citation": "Appendix Z" }
  },
  "runtime": { "budget_minutes": 20, "cpu_only": true }
}
```

### C) Laptop profile (recommended)
```bash
OMP_NUM_THREADS=8
OPENBLAS_NUM_THREADS=8
MKL_NUM_THREADS=8
NUMEXPR_NUM_THREADS=8
DATASET_CACHE_DIR=./data/cache
MAX_TRAIN_SAMPLES=8000
OFFLINE_MODE=false
CUDA_VISIBLE_DEVICES=
```

---

## Closing Thought

P2N gives us a repeatable **claim‑testing factory**: from a PDF to a runnable notebook in minutes, with the right trade‑offs (speed, determinism, and clarity). Agents do the **thinking**; generators do the **building**. From here, we add dataset breadth (Phase 2 M2), model depth (Phase 3), a real executor (Phase 4), and impactful, human‑readable outputs (Phase 5).
