# Manual Test Playbook — End‑to‑End after Planner Fix (Windows PowerShell)

## 0) One-time: activate venv & load `.env` in each shell

```powershell
Set-Location "C:\Users\jakem\Projects In Programming\PIP Final Group Project"
.\.venv\Scripts\Activate.ps1

# Load .env into this terminal
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }
```

## 1) Start API (no reload for SSE)

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1
```

Expect: **Supabase auth warning** lines (harmless), then `Uvicorn running ...`

## 2) Doctor

```powershell
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor
```

Expect JSON: `responses_mode_enabled: true`, `openai_python_version: "1.109.1"`, tools.file_search: true, runner posture.

## 3) Ingest a PDF

```powershell
$PDF = "C:\Users\jakem\Projects In Programming\He_Deep_Residual_Learning_CVPR_2016_paper.pdf"
$ing = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Deep Residual Learning (CVPR 2016)" `
  -F ("file=@`"" + $PDF + "`";type=application/pdf") | ConvertFrom-Json

$paper_id = $ing.paper_id
$vsid     = $ing.vector_store_id
"paper_id: $paper_id"; "vector_store_id: $vsid"
```

## 4) Planner v1.1 (fixed call shape)

```powershell
$actor = [guid]::NewGuid().Guid
$planObj = @{
  created_by     = $actor
  budget_minutes = 5
  claims         = @(
    @{
      dataset    = "ImageNet"; split = "val"
      metric     = "top-1 accuracy"; value = 75.3; units = "percent"
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

**Expect:** HTTP 200; non‑empty `plan_id`. No `Unsupported response_format type` errors.

## 5) Materialize & verify assets

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/materialize"
curl.exe -sS "http://127.0.0.1:8000/api/v1/plans/$plan_id/assets"
```

**Expect:** JSON containing short‑TTL signed URLs (don’t share); notebook & requirements present.

## 6) Run + SSE

```powershell
$run = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/plans/$plan_id/run" | ConvertFrom-Json
$run_id = $run.run_id

# Stream (watch for seed_check → run_start → run_complete)
curl.exe -N --http1.1 -H "Accept: text/event-stream" "http://127.0.0.1:8000/api/v1/runs/$run_id/events"
```

**Expect:** `stage_update` events, logs, then final artifacts in Storage: `metrics.json`, `events.jsonl`, `logs.txt`.

## 7) Report

```powershell
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/$paper_id/report"
```

**Expect:** `{ claimed, observed, gap_percent, citations[], artifacts{...} }`.

## 8) Kid‑Mode

```powershell
$story = curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/explain/kid" -H "Content-Type: application/json" `
  -d "{""paper_id"": ""$paper_id"", ""run_id"": ""$run_id""}" | ConvertFrom-Json

$storyboard_id = $story.storyboard_id
curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/explain/kid/$storyboard_id/refresh"
```

**Expect:** Storyboard JSON persisted (+ alt‑text on all pages); refresh updates scoreboard.

## Troubleshooting

- **Planner 502 with `Unsupported response_format type`** → code still tries `text=<Model>`; patch to `response_format={"type":"json_object"}`.  
- **File search returns nothing** → ensure `tool_resources={"file_search":{"vector_store_ids":[vsid]}}` is passed.  
- **Supabase auth `__del__` warnings** → cosmetic; ignore.  
- **SSE stalls** → use `--http1.1`, avoid `--reload`, keep one worker.
