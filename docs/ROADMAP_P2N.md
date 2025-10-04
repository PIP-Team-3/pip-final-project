# P2N (Paper‑to‑Notebook) — Roadmap & Execution Guide
_Last updated: 2025‑10‑02_

## 0) Executive Summary

P2N ingests a research paper (PDF), indexes it for retrieval, extracts experimental claims with citations, plans a minimal runnable reproduction, materializes a deterministic notebook and environment, executes it in a sandbox, streams live metrics/events (SSE), and reports the “reproduction gap.” A Kid‑Mode Storybook view translates the experiment into simple visuals.

**You are here (green):**  
- ✅ **Ingest** (Storage + Vector Store + DB) is **working** and returning `{ paper_id, vector_store_id, storage_path }`.
- 🔜 **Extractor SSE & Claims** (next): run the extractor on the ingested paper via Responses + File Search and stream structured claim results.

---

## 1) Current Status Snapshot

**Latest successful ingest response (example):**
```json
{"paper_id":"4960e4be-7a0c-47d5-aa89-837336ab6888","vector_store_id":"vs_68defc9746988191b477d99c962bba25","storage_path":"papers/dev/2025/10/02/4960e4be-7a0c-47d5-aa89-837336ab6888.pdf"}
```

**Doctor endpoint** shows:
- Env presence booleans (no secret values)
- Responses mode enabled
- Tools on: file_search ✅, web_search ✅
- Selected model (e.g., `gpt-4.1-mini`)
- Per‑run tool caps

**Working paths**
- Supabase Storage upload (private bucket, deterministic key)
- OpenAI Vector Store + file attachment (`purpose="assistants"`), then attach to vector store (Responses File Search)
- DB insert (schema v0, no FKs/RLS/defaults)
- Secret redaction in logs (vector_store_id truncated; signed URL tokens never logged)

**Known guards**
- “No‑Rules v0” schema: only `PRIMARY KEY(id)`; app supplies timestamps/foreign refs/values
- Per‑run caps (file_search ≤ 10 by default)
- Typed error taxonomy (e.g., `E_FILESEARCH_INDEX_FAILED`, `E_DB_INSERT_FAILED`)

---

## 2) Compatibility & Versions (lock this matrix for Milestone A)

> **Important:** _Do not mix incompatible OpenAI libs._ The Agents SDK version in use expects OpenAI Python **< 2.0**. Keep this matrix until we plan a deliberate migration.

| Component            | Version / Note         |
|---------------------|------------------------|
| Python              | 3.12.5                 |
| `openai`            | **1.109.1** (keep)     |
| `openai-agents`     | **0.3.3** (keep)       |
| `supabase`          | 2.20.0                 |
| `storage3`          | 2.20.0                 |
| `httpx`             | 0.28.1                 |
| `uvicorn`           | 0.37.0                 |

If you upgrade `openai` to 2.x, also upgrade to a compatible Agents SDK release. Until then: **stay on `openai==1.109.1`**.

---

## 3) Environment Keys (server‑only unless noted)

| Key                          | Purpose                                                | Scope        |
|------------------------------|--------------------------------------------------------|-------------|
| `OPENAI_API_KEY`             | Responses + File Search + Agents SDK                   | Server only |
| `SUPABASE_URL`               | Supabase project endpoint                              | Server only |
| `SUPABASE_SERVICE_ROLE_KEY`  | Supabase privileged key (Storage/DB server ops)        | Server only |
| `SUPABASE_ANON_KEY`          | Client‑side use only (front‑end). **Not needed** here. | Client only |
| `P2N_ENV`                    | `dev` / `stage` / `prod`                               | Server only |
| `P2N_DEV_USER_ID`            | A **UUID** for `created_by` in dev (optional)          | Server only |
| `P2N_BUCKET_PAPERS`          | Defaults to `papers` (private)                         | Server only |
| `P2N_BUCKET_RUNS`            | Defaults to `runs` (private)                           | Server only |
| `P2N_BUCKET_STORYBOARDS`     | Defaults to `storyboards` (private)                    | Server only |
| `FILE_SEARCH_PER_RUN`        | Tool cap (default 10)                                  | Server only |
| `WEB_SEARCH_PER_RUN`         | Tool cap (default 5)                                   | Server only |

**Windows PowerShell: load from `.env`**
```powershell
Get-Content .env | % {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    Set-Item -Path "Env:$($matches[1].Trim())" -Value $matches[2].Trim().Trim('\"')
  }
}
```

---

## 4) Data Model Posture (Schema v0)

- **Only** primary keys on `id` (UUID).
- No foreign keys, no RLS, no CHECK/UNIQUE/default constraints yet.
- `created_by` may be NULL (omit if you don’t have a valid UUID).
- App/agents provide **all** values (including timestamps).
- Logical refs (e.g., `paper_id`) are **not** enforced at DB level in v0.

### v1 hardening (later, when everyone is aligned)
- Add FKs (e.g., `created_by → profiles.id`), RLS policies, CHECK/ENUMs, UNIQUE, defaults, indexes, pgvector columns.
- Unique index on `pdf_sha256` to prevent duplicates under race.

---

## 5) Milestones & Quality Gates

### Milestone A — “No‑training slice”
- ✅ A1: Config/Doctor + internal tooling (env presence, caps, responses mode, versions)
- ✅ A2: Storage helper (signed URL) & private buckets
- ✅ A3: Supabase DB client smoke (insert/read/delete dev‑only)
- ✅ A4: Ingest end‑to‑end (Storage + Vector Store + DB)
- 🟡 A5: Extractor SSE run (File Search tool caps + guardrails + claims JSON)
- 🟡 A6: Docs: “No‑Rules v0” + Dev Identity (`P2N_DEV_USER_ID`) + runbook updates
- 🟨 A7: Negative tests & cleanup (OpenAI failures; bucket mismatch; redaction)

**Gate to finish Milestone A**  
- Extractor returns `claims[]` with `citation` & `confidence` and streams SSE (events + tokens).  
- Ingest verify route returns both `storage_path_present` and `vector_store_present: true`.  
- All negative tests green; logs redact secrets.

### Milestone B — Plan → Materialize (deterministic notebook & env)
- B1: Planner agent produces Plan JSON v1.1 (with viz & explain blocks)
- B2: Plan schema validation & justifications map (citations)
- B3: Materializer generates notebook + `requirements.txt`/lockfile (deterministic seeds)
- B4: Unit tests: smoke run notebook locally (no GPU), write `metrics.json`

**Gate:** `POST /api/v1/plans/{id}/materialize` returns notebook asset + env asset; notebooks run deterministically on CPU with seeds printed.

### Milestone C — Sandbox Execution & Live Events
- C1: Sandbox worker (Docker) executes notebooks with resource caps
- C2: Stream JSONL events (metric_update, sample_pred, progress, stage_update)
- C3: Store run events & series in DB (for later replay)
- C4: Simple Pro‑report: reproduction gap, artifacts, citations

**Gate:** `POST /api/v1/plans/{id}/run` streams live events and completes within budget; artifacts saved; report endpoint renders gap.

### Milestone D — Kid‑Mode Storybook & Evaluate‑Only Runner
- D1: Kid‑Explainer prompts generate Storybook JSON with alt‑text
- D2: Storybook UI (read‑only) + “Now Running…” ribbon live bar
- D3: Evaluate‑Only runner for eval‑heavy tasks (SQuAD, retrieval)
- D4: Docs & user‑facing demo path (Upload → Plan → Run → Storybook + Report)

**Gate:** Storybook final page updates on completion; evaluate‑only runs emit final metrics quickly.

### Milestone E — Schema v1 Hardening & Ops polish
- E1: RLS + FKs + CHECK/UNIQUE + defaults + indexes
- E2: Caching (datasets/env images), retries/resume, run history
- E3: Dashboard (gap %, success rate, runtime adherence)
- E4: Cloud deploy (API + worker + DB + storage) with secrets mgmt

---

## 6) How to Run (Windows, dev)

**Start API (no reload for streaming)**
```powershell
python -m uvicorn app.main:app --app-dir api --log-level info
```

**Doctor**
```powershell
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor
```

**Ingest**
```powershell
$PDF="C:\Users\jakem\Projects In Programming\He_Deep_Residual_Learning_CVPR_2016_paper.pdf"
$ingest = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Deep Residual Learning (CVPR 2016)" `
  -F ("file=@`"" + $PDF + "`";type=application/pdf")

$paper = ($ingest | ConvertFrom-Json).paper_id
$vsid  = ($ingest | ConvertFrom-Json).vector_store_id
$path  = ($ingest | ConvertFrom-Json).storage_path

"paper_id: $paper"
"vector_store_id (redacted): $($vsid.Substring(0,8))***"
"storage_path: $path"
```

**Verify**
```powershell
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/$paper/verify"
```

**Extractor (SSE)**
```powershell
curl.exe -N "http://127.0.0.1:8000/api/v1/papers/$paper/extract"
```

**Run tests (spot)**
```powershell
python -m pytest tests/test_papers_ingest.py::test_ingest_paper_via_upload -q
python -m pytest tests/test_papers_ingest.py::test_verify_ingest_endpoint -q
python -m pytest tests/test_papers_extract.py::test_extractor_sse_happy -q
```

---

## 7) Troubleshooting Quick Hits

- **22P02 invalid input syntax for UUID** → You passed `"system"` into a UUID column. Fix: omit `created_by` or set a valid `P2N_DEV_USER_ID` UUID.
- **Storage header type error** → Ensure Storage client headers are strings; your current deps are correct; we already fixed earlier header regression.
- **400 `'file_search' is not one of [...]`** → You uploaded the file with the wrong `purpose`. Fix: `purpose="assistants"`, then attach file to vector store.
- **SSE seems to hang** → Run server **without `--reload`**; use `curl.exe -N`; ensure firewall isn’t buffering.
- **Vector store missing** → Confirm ingest attached the PDF to the vector store and persisted its ID; re‑ingest if needed.

---

## 8) Acceptance Checklists

**Milestone A**
- [ ] Doctor reports all core envs present; Responses mode true.
- [ ] Ingest returns `{ paper_id, vector_store_id, storage_path }`.
- [ ] Verify route returns `true/true`.
- [ ] Extractor streams SSE → final `claims[]` with citations & confidence.
- [ ] Negative tests: bad URL, OpenAI failure, bucket mismatch, redaction consistency.

**Milestone B**
- [ ] Plan JSON v1.1 validated; includes `viz` & `explain`, `justifications` map with citations.
- [ ] Materialize returns notebook + env spec; notebook prints versions, sets seeds, writes `metrics.json`.

**Milestone C**
- [ ] Sandbox run completes within walltime; emits JSONL events; stores artifacts; report renders reproduction gap.

---

## 9) Reset & Recovery (dev only)

A dev reset script prompt (`C‑RESET‑01`) drops schema v0, re‑applies schema v0, seeds basics, and purges Storage under `papers/dev/*`, `runs/dev/*`, `storyboards/dev/*`.
Requires `CONFIRM_RESET=YES`.

---

## 10) Operational Runbook (dev)

1. Load `.env` → start API (no reload for streams).
2. `GET /internal/config/doctor` → confirm green.
3. Ingest a PDF → capture `paper_id`.
4. Verify ingest → confirm storage + vector store present.
5. Run Extractor SSE → confirm `claims[]` + traces.
6. Commit and push.
7. If anything goes sideways: check logs (typed errors), run targeted pytest, or dev reset.
