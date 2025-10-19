
# P2N OPERATIONS PLAYBOOK (Milestone A → B)
_Last updated: 2025-10-02 23:00 UTC_

This playbook is the day‑to‑day **runbook** for operating and validating the P2N backend through **Milestone A (Ingest + Verify + Extractor SSE)** and preparing for **Milestone B (Planning/Codegen materialization)**. It is written for Windows PowerShell and assumes a **local dev** workflow.

> Golden Sources:
> - `ROADMAP_P2N.md` — strategy, milestones, acceptance gates
> - `FUTURE_CODEX_PROMPTS.md` — the next prompts Codex should execute (with context hydration)
> - This file — exact commands, checks, and decision trees

---

## 0) Scope & Guardrails

- **Schema posture:** _v0 No‑Rules_. Only primary keys on `id`. **No FKs, enums, CHECKS, defaults, triggers, or RLS.**
- **Version matrix (do not drift):**
  - **Python:** 3.12.5
  - **OpenAI Python:** **1.109.1** (Responses + Vector Stores + File Search compatible)
  - **OpenAI Agents SDK:** **0.3.3** (requires `openai<2`)
  - **FastAPI/Starlette/Uvicorn:** as pinned in `api/requirements.txt`
  - **Supabase Python:** `supabase==2.20.0`, `storage3==2.20.0`
  - **httpx:** 0.28.x
- **Models:** `gpt-4.1-mini` for Extractor/Planner (Responses mode).  
- **Tools:** Responses **File Search** (via Vector Stores) + optional Web Search.  
- **Security:** Service role key is **server‑only**. Buckets are **private**. Signed URLs minted server‑side only.  
- **Logging rule:** Never log secrets. Redact vector_store_id to first 8 chars + `***`.

---

## 1) Environment & Secrets

### 1.1 Create & Pin the Virtualenv (Windows)

```powershell
# Confirm Python 3.12.5 exists
py -3.12 -V

# Create venv at project root
py -3.12 -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Confirm interpreter is the venv and 3.12.x
python -c "import sys; print(sys.executable); print(sys.version)"
```

### 1.2 Install Dependencies (respect the version matrix)

> **Important:** `openai-agents==0.3.3` needs `openai<2`. Keep **openai==1.109.1**.

```powershell
python -m pip install --upgrade pip
pip install -r api/requirements.txt

# If needed, reinforce key pins explicitly:
pip install "openai==1.109.1" "openai-agents==0.3.3" "supabase==2.20.0" "storage3==2.20.0" "httpx==0.28.1"
```

### 1.3 Provide `.env`

Create a `.env` at repo root with **your values**:

```
# OpenAI
OPENAI_API_KEY=sk-...

# Supabase
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...   # server-only
SUPABASE_ANON_KEY=eyJhbGciOi...          # for local tests only

# App
APP_ENV=dev
P2N_PAPERS_BUCKET=papers
P2N_RUNS_BUCKET=runs
P2N_STORYBOARDS_BUCKET=storyboards

# Tool caps (example)
CAP_FILE_SEARCH_PER_RUN=10
CAP_WEB_SEARCH_PER_RUN=5
CAP_CODE_INTERPRETER_SECONDS=60
```

**Load into current PowerShell session (no secrets printed):**

```powershell
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1].Trim())" -Value $matches[2].Trim().Trim('"') } }
```

---

## 2) Start/Stop & Health

### 2.1 Start API

```powershell
python -m uvicorn app.main:app --app-dir api --reload --log-level info
```

Keep this terminal open.

### 2.2 Doctor

```powershell
# In a second terminal (same venv, env loaded)
curl http://127.0.0.1:8000/internal/config/doctor
```

**Expect JSON with booleans only** (no secrets), e.g.:

```json
{
  "supabase_url_present": true,
  "supabase_service_role_present": true,
  "supabase_anon_present": true,
  "openai_api_key_present": true,
  "all_core_present": true,
  "caps": {
    "file_search_per_run": 10,
    "web_search_per_run": 5,
    "code_interpreter_seconds": 60
  },
  "responses_mode_enabled": true,
  "openai_python_version": "1.109.1",
  "models": {"selected":"gpt-4.1-mini"},
  "tools": {"file_search": true, "web_search": true}
}
```

---

## 3) Storage & DB Smoke

### 3.1 Signed URL (server-only)

```powershell
# body: { "bucket":"papers","path":"dev/smoke.txt","ttl_seconds":60 }
curl -s -X POST http://127.0.0.1:8000/internal/storage/signed-url -H "Content-Type: application/json" -d "{\"bucket\":\"papers\",\"path\":\"dev/smoke.txt\",\"ttl_seconds\":60}"
```

**Expect:** a URL that works for ~60s. Logs must NOT show token/query params.

### 3.2 DB Smoke

```powershell
curl -s -X POST http://127.0.0.1:8000/internal/db/smoke
```

**Expect:** {"inserted":1,"read":1,"deleted":1} and the ephemeral row briefly appears in Supabase → disappears.

---

## 4) Ingest Workflow (Milestone A)

### 4.1 Ingest a PDF (multipart)

```powershell
$PDF="C:\Users\<you>\path\to\paper.pdf"
$ingest = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Some Paper Title" `
  -F ("file=@`"" + $PDF + "`";type=application/pdf")

$ingest
```

**Expect JSON:**

```json
{
  "paper_id":"<uuid>",
  "vector_store_id":"vs_xxx...",
  "storage_path":"papers/dev/YYYY/MM/DD/<uuid>.pdf"
}
```

### 4.2 Verify Ingest

```powershell
$paper = ($ingest | ConvertFrom-Json).paper_id
curl -s http://127.0.0.1:8000/api/v1/papers/$paper/verify
```

**Expect:** {"storage_path_present":true,"vector_store_present":true}

---

## 5) Extractor SSE (Milestone A)

### 5.1 Run Extractor

```powershell
# Replace $paper with your UUID from ingest
curl.exe -N http://127.0.0.1:8000/api/v1/papers/$paper/extract
```

**Expect SSE events:**

- `stage_update: extract_start`
- `stage_update: file_search_call` (one or more; capped by config)
- `log_line: ...` (safe text only)
- token deltas (partial text)
- `stage_update: extract_complete`
- final JSON payload with `claims[]` (each claim has `dataset/split/metric/value/units + citation + confidence`).

**Guardrails:** Low confidence or missing citations must **halt** with typed error, not partial results.  
**Policy caps:** If File Search calls exceed cap → typed error with `policy.cap.exceeded` trace label.

---

## 6) Reset / Rollback (Dev Only)

> Use only when you need a clean slate.

- Run dev reset script (`C-RESET-01`) to:
  - Drop & recreate schema v0
  - Reseed demo rows
  - Purge `papers/dev/*`, `runs/dev/*`, `storyboards/dev/*` in Storage

**Safety:** Requires `CONFIRM_RESET=YES` flag.

---

## 7) Troubleshooting Decision Trees

### 7.1 OpenAI “invalid purpose” during ingest

- **Symptom:** 400 `"'file_search' is not one of [...] - 'purpose'"`
- **Cause:** Files must be uploaded with `purpose="assistants"` before attaching to a Vector Store for File Search (Responses).
- **Fix:** Ensure the workflow: upload → `purpose="assistants"` → attach to vector store.

### 7.2 Supabase `22P02 invalid input syntax for type uuid: "system"`

- **Symptom:** DB insert fails with 22P02 at ingest.
- **Cause:** v0 schema expects **TEXT** for fields like `created_by/updated_by`; do not pass `"system"` into a UUID column.
- **Fix:** Keep schema v0 definitions as TEXT for provenance/user fields; confirm `sql/schema_v0.sql` reflects that; purge & reseed if needed.

### 7.3 Storage upload “Header value must be str or bytes, not bool”

- **Symptom:** TypeError from `httpx` header building on upload.
- **Cause:** Passing booleans where strings expected in storage client options/header composition.
- **Fix:** Use `file_options` dict in `storage3.upload(...)` and never pass headers with boolean values.

### 7.4 `SyncQueryRequestBuilder` has no `.select`

- **Symptom:** AttributeError when `.select("*")` chained after `.insert(...)`.
- **Cause:** Newer postgrest bindings return the created row in `.execute()`; `.select` is not on the insert builder.
- **Fix:** Remove `.select("*")` in insert paths; read back separately only if necessary.

### 7.5 No SSE output

- **Symptom:** `/extract` hangs or returns nothing.
- **Checks:**
  - Confirm `vector_store_id` exists for the `paper_id`.
  - Ensure Responses run is created with tool attachments including File Search + that vector store ID.
  - Ensure proxy/server not buffering SSE (use curl `-N`, keep-alive).

### 7.6 Traces not visible

- **Symptom:** No traces for ingest/extract.
- **Fix:** Ensure trace labels exist (`p2n.ingest.storage.write`, `p2n.ingest.file_search.index`, `p2n.extractor.run`), and tracing not disabled in settings.

---

## 8) Acceptance Gates (Milestone A DoD)

- Buckets exist and are private; signed URLs work; tokens never logged.
- Schema v0 live; no rules beyond PK(id); seed optional.
- Ingest → returns `{paper_id, vector_store_id, storage_path}`.
- Verify route returns `true/true` for storage & vector store.
- Extractor SSE streams stages/tokens and returns structured `claims[]` with citations & confidence.
- Guardrails: tripwire on low confidence/missing citations (typed error).
- Policy caps: enforced & observable in traces.
- Logs redact sensitive values; `vector_store_id` masked.

---

## 9) Operational Hygiene

- **Git:** Do not commit `.env` or real PDFs. Add large docs to `.gitignore` or `docs/` as placeholders only.
- **Docs:** When behavior changes, update `ROADMAP_P2N.md` + `FUTURE_CODEX_PROMPTS.md` + this playbook.
- **Schema changes:** Require team sign‑off; create `schema_v1.sql` for the first hardening pass (FKs, RLS, defaults, indexes).

---

## 10) Quick Reference Commands

```powershell
# Activate & load env
.\.venv\Scripts\Activate.ps1
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1].Trim())" -Value $matches[2].Trim().Trim('"') } }

# Start server
python -m uvicorn app.main:app --app-dir api --reload --log-level info

# Doctor
curl http://127.0.0.1:8000/internal/config/doctor

# Ingest
$PDF="C:\path\to\paper.pdf"
curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest -F "title=Paper" -F ("file=@`"C:\path\to\paper.pdf`";type=application/pdf")

# Verify
$paper="<uuid-from-ingest>"
curl -s http://127.0.0.1:8000/api/v1/papers/$paper/verify

# Extract (SSE)
curl.exe -N http://127.0.0.1:8000/api/v1/papers/$paper/extract
```

---

## 11) Appendix — Schema v0 Shape (reference only)

- **Only PK(id)** on each table; other columns NULL‑permitted.
- `papers`: `id (uuid)`, `title (text)`, `pdf_sha256 (text)`, `storage_path (text)`, `vector_store_id (text)`, `created_at (timestamptz)`, `created_by (text)`
- `runs`, `plans`, `run_events`, `run_series`, `storyboards`: same v0 philosophy.

_Any deviation from this posture must be explicitly approved before implementing._
