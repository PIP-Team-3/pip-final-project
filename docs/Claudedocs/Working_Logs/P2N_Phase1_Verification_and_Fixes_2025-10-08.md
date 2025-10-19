# P2N — Phase 1 Verification & Hotfix Playbook
**Date:** 2025‑10‑08  
**Scope:** Combine final guidance with current repo status to finish **Phase 1** properly:
- ✅ Modular notebook generator **Phase 1** (zero behavior change)
- ⚠️ **Persist extracted claims to DB** (code added; must verify)
- ⚠️ **Planner: o3‑mini without web_search** (code added; must verify)
- 🎯 Run end‑to‑end smoke (ingest → extract → **save** → plan → materialize)

> **Stage Gate:** Do **not** start Phase 2 until this document’s checklists pass.

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Next Steps 1–4 (with checkpoints)](#next-steps-1-4-with-checkpoints)
   1. [Step 1 — Verify Claims DB Persistence](#step-1--verify-claims-db-persistence)
   2. [Step 2 — Planner: o3‑mini without Web Search](#step-2--planner-o3mini-without-web-search)
   3. [Step 3 — End‑to‑End Smoke Run](#step-3--end-to-end-smoke-run)
   4. [Step 4 — Close Phase 1 and Prepare Phase 2](#step-4--close-phase-1-and-prepare-phase-2)
3. [Implementation Snapshots (what changed)](#implementation-snapshots-what-changed)
4. [Acceptance Criteria](#acceptance-criteria)
5. [Troubleshooting Playbook](#troubleshooting-playbook)
6. [Appendix A — Model Capability Matrix](#appendix-a--model-capability-matrix)
7. [Appendix B — Useful Commands & Snippets](#appendix-b--useful-commands--snippets)

---

## Executive Summary

### Current status (from logs + code)
- **Extractor**: Healthy. Streams `response.function_call_arguments.delta` and builds a valid JSON list of **28 claims** from the TextCNN paper (Table 2). Event handling uses the correct **underscore** event names and **`event.delta`** access.
- **Claims persistence**: **Code added** (models, insert method, router hook, and `GET /api/v1/papers/{paper_id}/claims`) but **not verified against a live DB** in the last session.
- **Planner**: o3‑mini **does not support** `web_search_preview`. Tool filtering fix is **in** but **not verified** against the live planner route.
- **Materialize**: Phase 1 refactor shipped — generator factory, ABCs, and tests. Behavior unchanged by design (synthetic data + logistic regression). A 500 occurred when calling materialize with a **non‑UUID** plan identifier — the route expects a **UUID**.

### What must happen **now**
1) Confirm claims are **persisted** (count equals the extracted list).  
2) Confirm planner **works on o3‑mini without web_search** and still produces Plan JSON v1.1.  
3) Run a **single end‑to‑end smoke** using the TextCNN paper ID.  
4) Mark Phase 1 **complete** and open Phase 2 (dataset selection).

---

## Next Steps 1–4 (with checkpoints)

### Step 1 — Verify Claims DB Persistence
**Goal:** After extraction, claims exist in `claims` table for the paper, one row per claim.

**Pre‑reqs**
- Server running with latest commits (`6fcae9d`, `9a94207`).
- Paper (TextCNN) present:
  - `paper_id = 15017eb5-68ee-4dcb-b3b4-1c98479c3a93`
  - `vector_store_id` is set on that paper.

**Run**

```bash
# A) Sanity
curl -sS http://127.0.0.1:8000/internal/config/doctor

# B) (Re)run extraction to trigger persistence
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract" | tee /tmp/extract.log

# Expect stage events:
#  - stage: extract_start
#  - stage: persist_start (count=N)
#  - stage: persist_done  (count=N)
#  - event: result        (json claims)

# C) Verify via the new read endpoint
curl -sS "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims" | jq 'length'
# Expected: 28 (for TextCNN Table 2)
```

**Checkpoints**
- ✅ SSE shows `persist_start` and `persist_done` with matching counts.
- ✅ `GET /api/v1/papers/{id}/claims` returns **28** rows.
- ✅ Fields match the extractor output (spot check one row).

**If failing**
- See [Troubleshooting](#troubleshooting-playbook): _Claims not saving_.

---

### Step 2 — Planner: o3‑mini without Web Search
**Goal:** The planner runs on **o3‑mini** with **file_search only**; no 400 error; returns Plan JSON v1.1.

**Pre‑reqs**
- Planner model configured to `o3-mini` (per `settings.py` or `manage.py models`).

**Run**
```bash
# Trigger planner (body optional if your route pulls claims by paper_id)
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/plan" \
  -H "Content-Type: application/json" \
  -d '{} ' | tee /tmp/plan_o3.log

# Expect:
#  - No 400 "web_search_preview not supported" error
#  - File-search events (if logged)
#  - Final result with Plan JSON v1.1
```

**Checkpoints**
- ✅ No error mentioning `web_search_preview`.
- ✅ Tools list (if logged) **does not** include `web_search`/`web_search_preview` for o3‑mini.
- ✅ Plan JSON v1.1 emitted (dataset, model, config, metrics, viz, assumptions if needed).

**Optional (web‑capable model sanity)**
```bash
# Switch to a web-capable model for comparison (only if desired)
python manage.py set-planner gpt-4.1-mini
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/plan" | tee /tmp/plan_gpt41.log
# You may see web_search events if prompt calls for it.
```

**If failing**
- See [Troubleshooting](#troubleshooting-playbook): _Planner model/tool mismatch_.

---

### Step 3 — End‑to‑End Smoke Run
**Goal:** Ingest → Extract → **Save** → Plan → Materialize (stub run optional).

**Run**
```bash
# 1) Ingest (if you want a fresh paper)
# curl -sS -X POST "http://127.0.0.1:8000/api/v1/papers/ingest" \
#   -F "title=TextCNN (Kim, 2014)" \
#   -F "file=@uploads/1408.5882.pdf"

# 2) Extract (fires persistence)
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract" | tee /tmp/extract_e2e.log

# 3) Verify claims exist
curl -sS "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims" | jq 'length'

# 4) Plan (o3-mini; file-search only)
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/plan" | tee /tmp/plan_e2e.log

# 5) Capture the returned plan UUID (from SSE result)
#    Then materialize by UUID (replace <PLAN_UUID>):
# curl -sS -X POST "http://127.0.0.1:8000/api/v1/plans/<PLAN_UUID>/materialize" | tee /tmp/mat.log
```

**Checkpoints**
- ✅ Extraction result + persistence events (counts match).
- ✅ Claims table returns **28**.
- ✅ Planner succeeds on o3‑mini without web_search error.
- ✅ Materialize endpoint accepts **UUID** and returns 200 (artifacts written).

---

### Step 4 — Close Phase 1 and Prepare Phase 2
**Goal:** Document completion and create the Phase 2 work items.

**Close‑out checklist (Phase 1)**
- [ ] Claims persistence verified (counts, fields).
- [ ] Planner o3‑mini verified (no web tool; valid plan).
- [ ] End‑to‑end smoke passes.
- [ ] Update status docs:
  - Mark “Roadmap #1: Claims DB” ✅ Complete.
  - Mark “C‑NOTEBOOK‑01 Phase 1” ✅ Complete.
- [ ] File a follow‑up issue to add **idempotent replace** test and **read route** contract to the OpenAPI.

**Phase 2 kickoff (dataset selection)**
- [ ] Implement `SklearnDatasetGenerator` (digits, iris, wine).
- [ ] Implement `TorchvisionDatasetGenerator` (MNIST, CIFAR10).
- [ ] Implement `HuggingFaceDatasetGenerator` (SST‑2, IMDB).
- [ ] Update factory selection + fallback chain (HF → torchvision → sklearn → synthetic).
- [ ] Add tests that verify generated notebook code contains the right dataset loader calls.

---

## Implementation Snapshots (what changed)

### A) Claims DB Persistence
- **Data models**: `ClaimCreate`, `ClaimRecord` (in `api/app/data/models.py`).
- **DB methods**: `insert_claims()` and `get_claims_by_paper()` (in `supabase.py`).
- **Extractor hook**: After Pydantic validation → build list → call `db.insert_claims()` → emit `persist_*` events.
- **Read endpoint**: `GET /api/v1/papers/{paper_id}/claims` (for validation & UI).

**Mapping** (extractor → DB):
- `dataset_name`, `split`, `metric_name`, `metric_value`, `units`, `method_snippet`
- `citation.source_citation` → `source_citation`
- `citation.confidence` → `confidence`
- `paper_id` is injected at persistence time

**Policy**: Replace‑per‑paper (simple, deterministic).

### B) Planner Tool Filtering (o3‑mini)
- For planner requests, when `openai_planner_model` **contains** `"o3-mini"`, remove any `web_search`/`web_search_preview` tool entries before calling `responses.create/stream`.
- Keep `file_search` and the function tool; keep `tool_choice="required"`.
- Prompt instructs: “Use File Search first; if web search unavailable, produce an Assumptions section.”

### C) Notebook Generator — Phase 1
- New package `api/app/materialize/generators/` with:
  - `base.py` — `CodeGenerator` ABC
  - `dataset.py` — `SyntheticDatasetGenerator`
  - `model.py` — `SklearnLogisticGenerator`
  - `factory.py` — returns synthetic + logistic (Phase 1)
- `notebook.py` orchestrates via the factory.
- **No behavior change**; large test suite added.

---

## Acceptance Criteria

1) **Claims saved**
- Running `/extract` emits `persist_start`/`persist_done` and DB returns **28** claims.
- Re‑running extraction keeps row count stable (replace policy).

2) **Planner runs on o3‑mini**
- No 400 error about `web_search_preview`.
- Plan JSON v1.1 returned; file search used; “Assumptions” present if needed.

3) **Materialize by UUID**
- Materialize route called with a **UUID** plan id (not a slug).
- Returns 200 and writes artifacts. (Stubbed run is OK for Phase 1.)

4) **Docs & tests updated**
- Status docs updated; Phase 1 marked done.
- New tests for persistence and tool filtering exist and pass locally.

---

## Troubleshooting Playbook

### A) Claims not saving
- **Symptom**: No `persist_*` events; `GET /claims` returns 0.
- **Checks**:
  1. Server logs: look for `extractor.claims.saved` or `extractor.claims.save_failed`.
  2. Ensure `paper_id` is valid UUID and matches `claims.paper_id` FK.
  3. DB errors: constraint violations (confidence out of range; NOT NULL failures).
- **Actions**:
  - Run extraction once more. If still failing, temporarily log the payload length and one sample row prior to insert.
  - Validate schema alignment: column names and nullability.

### B) Planner still errors on web_search
- **Symptom**: 400 with `web_search_preview` while using o3‑mini.
- **Checks**:
  1. Log the **final tools array** being sent for planner.
  2. Confirm `settings.openai_planner_model` actually equals/contains “o3-mini”.
- **Actions**:
  - Strip both `web_search` **and** `web_search_preview` for o3‑mini.
  - As a fallback, temporarily switch model to `gpt-4.1-mini` to unblock tests.

### C) Materialize 500
- **Symptom**: `invalid input syntax for type uuid: "test-phase1-plan"`
- **Fix**: Use a real **UUID** from the planner’s SSE `result`. Query the plans table if needed to find the last plan id.

### D) Vector store empty
- **Symptom**: Extractor/planner run but produce empty/noisy outputs; no `file_search` events.
- **Checks**:
  1. `/api/v1/papers/{id}/verify` returns ok.
  2. Paper has a non‑null `vector_store_id`.
- **Actions**:
  - Re‑ingest the PDF to rebuild the vector store.
  - Verify OpenAI dashboard shows chunks in that store.

---

## Appendix A — Model Capability Matrix

| Model          | File Search | Web Search | Function Tools | Notes                                  |
|----------------|-------------|------------|----------------|----------------------------------------|
| gpt‑4o         | ✅           | ✅          | ✅              | Good for extractor & planner           |
| gpt‑4.1‑mini   | ✅           | ✅          | ✅              | Cost‑efficient, web‑capable alternative|
| o3‑mini        | ✅           | ❌          | ✅              | Use file_search only; add assumptions  |

> Keep the planner code capability‑aware so you never send unsupported tools.

---

## Appendix B — Useful Commands & Snippets

### Health & config
```bash
python manage.py doctor
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/internal/config/doctor
```

### Extraction & persistence
```bash
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/<paper_id>/extract" | tee /tmp/extract.log
grep -A1 '"stage":"persist_' /tmp/extract.log

curl -sS "http://127.0.0.1:8000/api/v1/papers/<paper_id>/claims" | jq 'length'
```

### Planner
```bash
# o3-mini (no web tool)
curl -sS -N -X POST "http://127.0.0.1:8000/api/v1/papers/<paper_id>/plan" | tee /tmp/plan_o3.log

# switch to a web-capable model (optional)
python manage.py set-planner gpt-4.1-mini
```

### Materialize (use a UUID)
```bash
curl -sS -X POST "http://127.0.0.1:8000/api/v1/plans/<PLAN_UUID>/materialize" | tee /tmp/mat.log
```

---

### Final Note
You now have **everything** to close Phase 1 cleanly. The only remaining work is **verification** (Step 1–3). Once done, promote the status docs and kick off **Phase 2** (dataset selection) immediately.