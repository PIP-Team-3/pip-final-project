# Playbook — Verification Steps (Hands‑On)
**Audience:** Devs & Ops  
**Goal:** Quick checks to confirm extractor/planner stay within contract

---

## 1) Health & Env
**Bash**
```bash
set -euo pipefail
curl -sS http://localhost:8000/health | grep -q '"status":"ok"' && echo "API OK"
curl -sS http://localhost:8000/internal/config/doctor
```

If doctor says all core present and `openai_python_version` is `1.109.1`, proceed.

---

## 2) Ingest (local PDF path)
**Bash**
```bash
curl -sS -X POST "http://localhost:8000/api/v1/papers/ingest" \
  -F "file=@uploads/1512.03385.pdf" \
  -F "title=ResNet (He et al., 2015)"
```

Expected: `201 Created` with `paper_id`, `vector_store_id`, `storage_path`.

---

## 3) Extract (SSE) — observe final JSON result
**Bash**
```bash
curl -sS -X POST -N "http://localhost:8000/api/v1/papers/${PAPER_ID}/extract" \
| tee /tmp/extract.log \
| grep -E "event: (result|error)|^data:" | tail -20
```

Expected: `event: result` followed by **strict JSON** (ExtractorOutput). If prose only, treat as drift; re‑run once; if still prose, open a bug.

---

## 4) Plan (v1.1)
**Bash**
```bash
curl -sS -X POST "http://localhost:8000/api/v1/papers/${PAPER_ID}/plan" \
  -H "Content-Type: application/json" \
  -d '{"claims":[{"dataset_name":"CIFAR-10","metric_name":"accuracy","metric_value":85.0,"units":"percent","source_citation":"Table 1","split":"test","method_snippet":"ResNet-18","confidence":0.9}],"budget_minutes":15}'
```

Expected: `{ "plan_id": "..." }` and JSON validates as Plan v1.1 (server will reject otherwise).

---

## 5) Materialize
**Bash**
```bash
curl -sS -X POST "http://localhost:8000/api/v1/plans/${PLAN_ID}/materialize" \
| tee /tmp/mat.json && jq -r '.env_hash' /tmp/mat.json
```

Expected: non‑null `env_hash` and notebook/requirements assets recorded.

---

## 6) Run (stub until C‑RUN‑01)
**Bash**
```bash
RUN_ID=$(curl -sS -X POST "http://localhost:8000/api/v1/plans/${PLAN_ID}/run" | jq -r '.run_id')
echo "RUN_ID=$RUN_ID"
```

Expected: status flows `queued -> running -> succeeded` (stub).

---

## 7) Report
**Bash**
```bash
curl -sS "http://localhost:8000/api/v1/papers/${PAPER_ID}/report"
```

Expected: gap stats + signed URLs for artifacts.

---

## 8) Common Errors & Fixes
- **Unknown parameter 'attachments'** → Remove `attachments` from Responses `input`; configure File Search in the tool.  
- **`E_EXTRACT_NO_OUTPUT`** → Ensure `response_format.json_schema.strict=true`; retry once with “JSON‑only” reminder.  
- **Supabase `mime type text/plain`** → Ensure upload uses header key `content-type: application/pdf`.  
- **DB enum violation (`papers_status_check`)** → Only `'ready'|'processing'|'failed'` allowed.

---

## 9) Drift Sentinels (quick tests you can run)
- `grep -R "\"attachments\"" api/` → should be **empty**.  
- `grep -R "text_format" api/` → should be **empty**.  
- Payload logging (redacted) contains `response_format.json_schema.strict: true`.