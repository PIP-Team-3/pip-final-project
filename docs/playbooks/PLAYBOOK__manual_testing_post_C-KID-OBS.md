# P2N Manual Test Playbook (Post C‑KID‑01 & C‑OBS‑01)
_Last updated: 2025-10-04_

This playbook validates the **end‑to‑end pipeline** on Windows PowerShell using your current implementation:
Ingest → Extractor (SSE) → Planner v1.1 → Materialize → Run (deterministic, CPU‑only, caps) → Report (gap) → Kid‑Mode Storybook → Doctor (observability).

**Assumptions**
- Python 3.12.5
- Virtualenv at `.venv`
- OpenAI Python **1.109.1** (Agents SDK 0.3.3 compatible)
- Schema **v0** (no FKs/RLS/CHECK/UNIQUE/defaults; app supplies all values)
- Private Supabase Storage (signed URLs only)
- Responses mode enabled; `file_search` tool configured at **top level** with `max_num_results`

---

## 0) Pre‑flight: Env, venv, packages

```powershell
# Run in project root
Set-Location "C:\Users\jakem\Projects In Programming\PIP Final Group Project"

# Create/activate venv if needed
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Confirm interpreter/version
python -c "import sys; print(sys.executable); print(sys.version)"

# Install deps (keep openai pinned for Agents SDK)
python -m pip install -U pip
python -m pip install -r api\requirements.txt
python -m pip install "openai==1.109.1" "openai-agents==0.3.3"
```

Load **.env** into the current shell (each terminal needs it):

```powershell
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }
```

---

## 1) Start API (Terminal A)

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1
```
> Tip: avoid `--reload` during SSE tests on Windows.

**Expected log lines**
- `Application startup complete.`
- Later: request lines for each API call (201 Created for ingest, 202 Accepted for run, 200 OK for report/kid).

---

## 2) Doctor (Terminal B)

```powershell
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor
```
**Expect** JSON showing:
- `responses_mode_enabled: true`
- `tools.file_search: true`
- runner posture: `cpu_only: true`, `seed_policy: "deterministic"`, `artifact_caps: { logs_mib: 2, events_mib: 5 }`
- `last_run: null` (cold start)

---

## 3) Ingest a local PDF

```powershell
$PDF = "C:\Users\jakem\Projects In Programming\He_Deep_Residual_Learning_CVPR_2016_paper.pdf"
$ing = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Deep Residual Learning (CVPR 2016)" `
  -F ("file=@`"" + $PDF + "`";type=application/pdf") | ConvertFrom-Json

$paper_id = $ing.paper_id
$vsid  = $ing.vector_store_id
$path  = $ing.storage_path

"paper_id: $paper_id"
"vector_store_id: $vsid"
"storage_path: $path"
```
**Expect**
- Non‑empty `paper_id` (UUID), `vector_store_id` (redacted in logs), and `storage_path` under private bucket.

---

## 4) (Optional) Extractor SSE

```powershell
# Observe live tokens and stages (CTRL+C to stop)
curl.exe -N --http1.1 -H "Accept: text/event-stream" "http://127.0.0.1:8000/api/v1/papers/$paper_id/extract"
```
**Expect SSE events**
- `stage_update: file_search_call` → `extract_start` → `extract_complete`
- final data contains `claims[]` with `citation` and `confidence`
- If cap exceeded: typed error `E_POLICY_CAP_EXCEEDED`

---

## 5) Planner v1.1

Planner requires `created_by` and `claims[]` in the JSON body and validates against Plan v1.1.

```powershell
$actor = [guid]::NewGuid().Guid
$planObj = @{
  created_by     = $actor
  budget_minutes = 5
  claims         = @(
    @{
      dataset    = "ImageNet"
      split      = "val"
      metric     = "top-1 accuracy"
      value      = 75.3
      units      = "percent"
      citation   = "He et al., 2016 (ResNet), CVPR, Table 1"
      confidence = 0.90
    }
  )
}

$plan = Invoke-RestMethod -Method POST `
  -Uri ("http://127.0.0.1:8000/api/v1/papers/{0}/plan" -f $paper_id) `
  -Headers @{ "X-Actor-Id" = $actor } `
  -ContentType "application/json" `
  -Body ($planObj | ConvertTo-Json -Depth 10)

$plan_id = $plan.plan_id
"plan_id: $plan_id"
```
**Expect**
- Non‑empty `plan_id`
- If `422 Unprocessable Entity`: the JSON body is malformed or required fields missing (use `Invoke-RestMethod` as above).

---

## 6) Materialize notebook + env

```powershell
$mat = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/materialize" | ConvertFrom-Json
$mat
```
**Expect**
- JSON with `{ notebook_asset_path, env_asset_path, env_hash }`

Verify signed URLs (short TTL, tokens **not** logged):
```powershell
$assets = curl.exe -sS "http://127.0.0.1:8000/api/v1/plans/$plan_id/assets" | ConvertFrom-Json
$assets
```

---

## 7) Run (SSE)

```powershell
$run = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/run" | ConvertFrom-Json
$run_id = $run.run_id
"run_id: $run_id"

# Live events
curl.exe -N --http1.1 -H "Accept: text/event-stream" "http://127.0.0.1:8000/api/v1/runs/$run_id/events"
```
**Expect SSE events**
- `stage_update: seed_check` → `run_start`
- `progress` updates
- `log_line` forwarding
- `run_complete` at end (or typed error like `E_RUN_TIMEOUT`, `E_GPU_REQUESTED`)
- Artifacts persisted to Storage:
  - `runs/{run_id}/metrics.json`
  - `runs/{run_id}/events.jsonl`
  - `runs/{run_id}/logs.txt`

**Caps**
- Logs truncated at ~2 MiB with `__TRUNCATED__`
- Events truncated at ~5 MiB with `__TRUNCATED__`

---

## 8) Report (gap)

```powershell
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/$paper_id/report" | ConvertFrom-Json
```
**Expect**
- `{ claimed, observed, gap_percent, metric_name, citations[], artifacts{metrics_url,events_url,logs_url} }`

---

## 9) Kid‑Mode Storybook

```powershell
$story = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/explain/kid" `
  -H "Content-Type: application/json" `
  -d ("{ `"paper_id`": `"$paper_id`" }") | ConvertFrom-Json
$story_id = $story.storyboard_id
"storyboard_id: $story_id"

# After run completes, refresh final page (scoreboard)
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/explain/kid/$story_id/refresh" | ConvertFrom-Json
```
**Expect**
- Storyboard with 5–7 pages, **alt‑text required**
- Final page updated with two‑bar scoreboard (claimed vs observed)

---

## 10) Doctor again (observability)

```powershell
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor
```
**Expect**
- runner posture fields present and unchanged
- `last_run` populated with `{ id, status, completed_at, env_hash }`
- signed URLs and keys redacted

---

## Troubleshooting

- **422 Unprocessable** on Planner: use `Invoke-RestMethod` (PowerShell) with proper JSON; provide `created_by` and `claims[]`.
- **`Responses.stream() got an unexpected keyword argument 'attachments'`**: you’re calling the new API incorrectly. Use top‑level tools `{ "type":"file_search","max_num_results": N }` and pass `attachments` only in the **message** as `{ "type":"file_search" }`.
- **`E_GPU_REQUESTED`**: GPU was requested; runner enforces CPU‑only by design.
- **SSE hangs** on Windows shell: use `--http1.1` and **avoid** `--reload` server flag.
- **`E_DB_INSERT_FAILED`** or `22P02` UUID errors: ensure `created_by` is a real UUID; schema v0 means app must supply valid IDs.
- **Env not loaded**: each terminal must `Get-Content .env | % {{ ... }}` before use.

---

## Clean up (optional)

```powershell
# Stop API in Terminal A with CTRL+C
# To clear test artifacts in your private bucket, use your Supabase console or custom maintenance script.
```
