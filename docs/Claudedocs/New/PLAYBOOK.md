# P2N Verification Playbook
**Updated:** 2025-10-05

## 0) One‑time setup (Windows PowerShell)
```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Load .env into current session
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    $key = $matches[1].Trim()
    $value = $matches[2].Trim().Trim('"').Trim("'")
    Set-Item -Path "Env:$key" -Value $value
  }
}

# Start API
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1
```

---

## 1) Health + Config
```powershell
Invoke-RestMethod "http://localhost:8000/health"
Invoke-RestMethod "http://localhost:8000/internal/config/doctor"
```
**Expect:** 200 OK; redacted secrets; vector store reachable if configured.

---

## 2) Database Smoke (schema v1‑safe)
> Ensures we **don’t** violate checks (no `status='smoke'`, unique keys rotate per call).
```powershell
curl.exe -sS -X POST http://localhost:8000/internal/db/smoke -H "accept: application/json"
```
**Expect:** 200 OK and a `paper_id`.  
If you see `papers_status_check` or uniqueness violations, update the smoke test to:
- Omit `status` (let default `'ready'` apply)
- Use unique `vector_store_id` and `pdf_sha256` (`uuid4` suffix)

---

## 3) Ingest
```powershell
# By URL
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/v1/papers/ingest?url=https://arxiv.org/pdf/1512.03385.pdf&title=ResNet" `
  -ContentType "application/json"
```
**Expect (DB):** row in `papers` with:
- `pdf_storage_path LIKE 'papers/%'`
- Unique `vector_store_id`, `pdf_sha256`
- `status='ready'`

---

## 4) Extract (SSE)
```powershell
# Stream in a separate terminal
curl.exe -N "http://localhost:8000/api/v1/papers/<paper_id>/extract"
```
**Expect:** `stage_update`, `token`, `result` events; at least 1 claim with citation.

---

## 5) Plan
```powershell
$plan = Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/v1/papers/<paper_id>/plan" `
  -ContentType "application/json" `
  -Body (@{
    claims = @(@{dataset_name="CIFAR-10"; metric_name="accuracy"; metric_value=85.0; units="percent"; source_citation="Table 1"})
    budget_minutes = 15
  } | ConvertTo-Json)
```
**Expect (DB):** row in `plans`:
- `version='1.1'`
- `status='draft'` initially
- `budget_minutes` present

---

## 6) Materialize
```powershell
Invoke-RestMethod -Method POST "http://localhost:8000/api/v1/plans/<plan_id>/materialize"
```
**Expect:**
- Notebook + requirements uploaded to `assets/`
- `plans.env_hash` set, `plans.status='ready'`

---

## 7) Run (C‑RUN‑01 will make this real)
```powershell
Invoke-RestMethod -Method POST "http://localhost:8000/api/v1/plans/<plan_id>/run"
curl.exe -N "http://localhost:8000/api/v1/runs/<run_id>/events"
```
**Expect:** `queued → running → succeeded` and artifacts in `runs/<run_id>/`.

---

## 8) Report
```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/papers/<paper_id>/report"
```
**Expect:** gap %, citations array, signed URLs (TTL ≈ 120s).

---

## 9) Kid‑Mode + Refresh
```powershell
Invoke-RestMethod -Method POST "http://localhost:8000/api/v1/explain/kid" -Body (@{paper_id="<paper_id>"} | ConvertTo-Json) -ContentType "application/json"
Invoke-RestMethod -Method POST "http://localhost:8000/api/v1/explain/kid/<storyboard_id>/refresh"
```
**Expect:** storyboard JSON persisted; `storage_path LIKE 'storyboards/%'`; scoreboard updated.

---

## Storage Gotchas (fixed)
- **Deletion:** `client.storage.from_(bucket).remove([path])` (no `delete_object`)
- **Resilience:** On DB insert failure, run **guarded** cleanup; never mask original error.

---

## Status Enums (do not deviate)
- papers: `ready|processing|failed`
- plans: `draft|ready|failed`
- runs: `queued|running|succeeded|failed|timeout|cancelled`

---

## Fast Failure Codes (examples)
- `E_VECTOR_STORE_NOT_FOUND`
- `E_PLAN_JSON_INVALID`
- `E_RUN_TIMEOUT`
- `E_STORAGE_UPLOAD_FAILED`
- `E_EXTRACT_NO_CLAIMS`

---

## Easy‑Win Papers (see `papers_to_ingest.md` for table + batch script)
- ResNet (1512.03385), MobileNetV2 (1801.04381), DenseNet (1608.06993), SqueezeNet (1602.07360)
- WideResNet (1605.07146), mixup (1710.09412), CutMix (1905.04899), RandAugment (1909.13719)
- Cutout (1708.04552), BatchNorm (1502.03167), Bag of Tricks (1812.01187), Adam (1412.6980)
- Focal Loss (1708.02002), TextCNN (1408.5882), fastText (1607.01759), DistilBERT (1910.01108)
- ULMFiT (1801.06146), GCN (1609.02907), XGBoost (1603.02754), Super‑Convergence (1708.07120)
