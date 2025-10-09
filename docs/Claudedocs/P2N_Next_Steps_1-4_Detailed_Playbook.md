
# P2N — Next Steps 1–4: Detailed Implementation Playbook
**Last updated:** 2025‑10‑07  
**Scope:** Immediate next steps to harden and extend the now‑working extraction pipeline.  
**Audience:** Backend/infra engineers, test engineers, and PM/tech lead.

---

## TL;DR (Executive Summary)

- **Step 1 — Complete Extraction Integration:** Persist extracted claims to DB with versioning; add vector‑store readiness and retrieval tripwires; expose claim counts; tighten typed errors.  
- **Step 2 — End‑to‑End Pipeline Testing:** Codify ingest → extract → plan → materialize → run (stub) as automated tests across 3–5 exemplar papers; surface costs and latencies.  
- **Step 3 — Improve Extraction Quality:** Splits, units, dedup, and confidence calibration; enforce “search‑before‑emit” sentinel and no‑grounding pathways; measurable quality gates.  
- **Step 4 — Real Notebook Generation (C‑NOTEBOOK‑01):** Modular generators for datasets/models; start with sklearn seeds for quick realism; then torchvision/HuggingFace; add deterministic “safety” cell; Docker‑ready outputs.

Each step below contains **Objectives → Deliverables → Checkpoints/Milestones → Detailed Workplan → Tests → Observability/SLIs → Risks & Mitigations → Exit Criteria**.

---

## Step 1 — Complete Extraction Integration

### Objectives
1. Persist **every successful extraction** to the `claims` table with a **`claim_set_id`** to support versioning.  
2. Add **pre‑extraction vector store readiness** + **minimum retrieval tripwire** to avoid silent empty outputs.  
3. Emit **claim counts** (and a short preview) in the SSE `result` to aid UX and CI.  
4. Tighten typed errors: `E_VECTOR_STORE_NOT_READY`, `E_EXTRACT_NO_GROUNDING`, `E_EXTRACT_LOW_CONFIDENCE`.

### Deliverables
- Server persists a **claim set** per extraction run (`claim_set_id`, `run_id`, `paper_id`).  
- New **typed errors** with actionable remediation text.  
- SSE `result` includes: `{ "claims_count": N, "claim_set_id": "...", "sample": [first_3_claims] }`.  
- **Docs & tests** covering success + failure modes.

### Checkpoints & Milestones
- **M1:** DB ready (DDL) & migration applied.  
- **M2:** Prechecks/tripwires in place; typed errors wired to SSE.  
- **M3:** Persistence path implemented; result payload shows `claims_count`.  
- **M4:** Tests passing (unit + integration).

### Detailed Workplan
1. **DB / DDL (idempotent migration)**
   - Add to `claims` (if missing): `claim_set_id UUID NOT NULL`, `run_id UUID NULL`, `raw_citation TEXT NULL`, `content_hash TEXT NOT NULL`.
   - Create `claim_sets` table (optional but recommended):
     ```sql
     CREATE TABLE IF NOT EXISTS claim_sets (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       created_by TEXT NULL,
       supersedes UUID NULL REFERENCES claim_sets(id) ON DELETE SET NULL
     );
     ```
   - Add partial **dedup** index on `claims.content_hash` scoped to `paper_id`:
     ```sql
     CREATE UNIQUE INDEX IF NOT EXISTS ux_claims_hash_per_paper
       ON claims (paper_id, content_hash);
     ```

2. **Vector Store Readiness Precheck**
   - On `/extract` entry: verify `paper.vector_store_id` present; call a cheap readiness probe (e.g., list store files or attempt a `file_search` with a sentinel query `"READY_PROBE"` limited to 1 result).  
   - If not ready: return `E_VECTOR_STORE_NOT_READY` with “retry after indexing completes” guidance.

3. **Minimum Retrieval Tripwire**
   - During streaming, count `response.file_search_call.*` events and the number of retrieved items (if available in annotations).  
   - If **no retrieval events** occur and the model attempts to emit, **abort** with `E_EXTRACT_NO_GROUNDING`.

4. **Persistence Path**
   - On successful parsed output:
     - Create a `claim_set_id = uuid4()`.
     - For each claim, compute a **stable content hash** (lowercased normalization, rounding metric):
       ```text
       H = sha256(
         f"{dataset_name|''}|{split|''}|{metric_name|''}|{round(metric_value, 3)}|{units|''}|{normalize(citation.source_citation)}"
       )
       ```
     - Insert rows; ignore duplicates via `ON CONFLICT (paper_id, content_hash) DO NOTHING`.
     - If you want strict versioning semantics, mark older sets: `UPDATE claim_sets SET superseded_by = :new_set WHERE paper_id=:paper_id AND id<>:new_set` (optional).

5. **SSE `result` payload**
   - Send:
     ```json
     {
       "type": "extract_result",
       "paper_id": "...",
       "claim_set_id": "...",
       "claims_count": 28,
       "sample": [ /* up to first 3 claims */ ]
     }
     ```

6. **Typed Errors**
   - Map precheck/tripwire outcomes into explicit codes:
     - `E_VECTOR_STORE_NOT_READY`
     - `E_EXTRACT_NO_GROUNDING`
     - `E_EXTRACT_LOW_CONFIDENCE`
     - Preserve existing: `E_POLICY_CAP_EXCEEDED`, `E_EXTRACT_OPENAI_ERROR`, etc.

### Tests
- **Unit**
  - `test_claim_hash_stability_rounding()`  
  - `test_content_hash_dedup_per_paper()`  
  - `test_vector_store_precheck_ready()/not_ready()`  
  - `test_min_retrieval_tripwire_blocks_emit()`

- **Integration**
  - `test_extract_persists_claims_with_claim_set_id()` (happy path).  
  - `test_extract_returns_no_grounding_when_no_search()` (use a blank PDF).  
  - `test_extract_emits_claims_count_in_result()`.

- **E2E**
  - Ingest `TextCNN` → Extract → Assert `claims_count >= 20`, preview contains SST‑2 row.

### Observability / SLIs
- **SLIs:** extraction success rate, avg time to first retrieval, claims per paper, error code distribution.  
- **Logs:** include `vector_store_id`, `claims_count`, `claim_set_id`.  
- **Tracing:** annotate span with `retrieval_calls`, `retrieved_items`, `claims_count`.

### Risks & Mitigations
- **Risk:** Over‑dedup removes legitimate near‑duplicates.  
  **Mitigation:** Use per‑paper dedup with conservative rounding (3 decimals) + retain `run_id` for audit.  
- **Risk:** Vector store probe cost.  
  **Mitigation:** Cache readiness flag per paper for 10–30 minutes.

### Exit Criteria
- Claims persist reliably with versioning; typed errors + claim counts visible; green tests.

---

## Step 2 — End‑to‑End Pipeline Testing

### Objectives
Codify the **entire flow** (ingest → extract → plan → materialize → run‑stub) into repeatable integration/E2E tests and establish **latency & cost baselines**.

### Deliverables
- `tests/e2e/test_e2e_basic.py` executing the full loop on 2–3 papers.  
- Smoke scripts in `scripts/` (`e2e_smoke.sh`, `doctor.sh`).  
- CI job to run smoke suite on PRs; full E2E nightly.

### Checkpoints & Milestones
- **M1:** Smoke test for TextCNN green.  
- **M2:** Add ResNet paper; both green.  
- **M3:** Nightly E2E across 3–5 papers with cost/latency reports.

### Detailed Workplan
1. **Test Data & Fixtures**
   - Ensure 2–3 PDFs are locally available (TextCNN, ResNet, 1 “simple” paper).  
   - Fixtures create temp workspace, clean up storage paths.

2. **Smoke Script (`scripts/e2e_smoke.sh`)**
   - Checks env & health.  
   - Ingest if missing; **poll vector store readiness**.  
   - Extract (assert `claims_count > 0`).  
   - Plan (assert Plan JSON v1.1 present).  
   - Materialize (assert notebook + requirements stored).  
   - Run (stub) → assert metrics artifact exists.

3. **Integration/E2E PyTest**
   - Structure per stage with clear asserts and informative failure messages.  
   - Use **markers**: `@pytest.mark.smoke`, `@pytest.mark.nightly`.

4. **Cost/Latency Baselines**
   - Log tokens/tool calls per stage; save a small CSV artifact in CI (`artifacts/e2e_metrics.csv`).

### Tests (examples)
```python
def test_e2e_textcnn(tmp_path):
    paper_id = ingest("uploads/1408.5882.pdf")
    wait_vector_store_ready(paper_id)
    claims = extract(paper_id)
    assert len(claims) >= 20

    plan_id = plan(paper_id)
    nb_bytes, reqs = materialize(plan_id)
    assert b"import" in nb_bytes

    run_id = run_stub(plan_id)
    metrics = fetch_metrics(run_id)
    assert "status" in metrics
```

### Observability / SLIs
- Time per stage, cost per stage, success ratio.  
- Persist CSV from CI for trend tracking.

### Risks & Mitigations
- **Risk:** Flaky retrieval on PDFs with complex layout.  
  **Mitigation:** Skip “torture” PDFs in smoke; put them in nightly with retries.

### Exit Criteria
- Smoke suite < 5 min, fully green on PRs; nightly E2E across 3–5 papers with metrics.

---

## Step 3 — Improve Extraction Quality

### Objectives
Increase **recall & precision** while preserving determinism and cost bounds. Address splits/units, dedup, and confidence calibration. Enforce “search‑before‑emit.”

### Deliverables
- Normalization pass (units/value parsing, split inference).  
- Duplicate collapse within a claim set.  
- “Search‑before‑emit” **sentinel test** added.  
- Confidence calibration policy note.

### Checkpoints & Milestones
- **M1:** Normalizers live (units/values/splits).  
- **M2:** Dedup strategy deployed & validated.  
- **M3:** Sentinel test in CI; no regressions.  
- **M4:** QA sample: ≥90% precision on a 30‑row labeled set.

### Detailed Workplan
1. **Normalization**
   - Units: map `percent`, `%`, `Percentage` → `%`.  
   - Values: extract numeric from `88.1%` → `88.1`, set units `%` if missing.  
   - Splits: if not explicit, infer from citation context (e.g., “Table 2 (Test)”).

2. **Dedup within Claim Set**
   - Group by `(dataset|split|metric|round(value,3)|units)`; keep highest‑confidence or first occurrence.  
   - Retain all rows in DB but **mark duplicates** with `is_duplicate=true` (or keep only one; your choice).

3. **Sentinel: Search‑before‑Emit**
   - Add a test that asserts at least one `response.file_search_call.searching` event **precedes** the first `function_call_arguments.delta` event.  
   - Fails fast if violated.

4. **Confidence Calibration (lightweight)**
   - Bucket confidences and sample 10 rows/biweek for manual QA; adjust prompt thresholds if buckets don’t correlate with correctness.

### Tests
- **Unit:** normalization & parsing cases; dedup logic.  
- **Integration:** confirm sentinel triggers on a synthetic prompt that tries to emit without search.  
- **QA harness:** simple YAML/CSV label set with expected (dataset/metric/value/units/split).

### Observability / SLIs
- Precision (% exact matches on QA set), duplicate rate, normalized‑fields coverage, average confidence by bucket.

### Risks & Mitigations
- **Risk:** Over‑normalization (e.g., “BLEU‑4” vs “BLEU”).  
  **Mitigation:** Keep “metric_name_raw”; normalize to a canonical label but retain raw for audits.

### Exit Criteria
- Normalization active; sentinel test green; QA precision ≥ 90% on labeled sample.

---

## Step 4 — Real Notebook Generation (C‑NOTEBOOK‑01)

### Objectives
Replace the synthetic notebook path with **modular, real‑data notebooks** that can run in CPU budget, with deterministic seeding and Docker‑readiness.

### Deliverables
- `materialize/generators/` package with dataset/model generators + factory.  
- Minimal real path: sklearn datasets + classic models (fast wins).  
- Torchvision & HuggingFace generators (incremental).  
- Safety cell & env‑aware behavior; Dockerfile for executor.

### Checkpoints & Milestones
- **M1 (Week 1):** Modularization complete; behavior parity with current synthetic path; tests green.  
- **M2 (Week 2):** Sklearn datasets/models live; TextCNN plans fallback gracefully to sklearn.  
- **M3 (Week 3):** Torchvision (MNIST/CIFAR10) + PyTorch CNN; ResNet for planner’s ResNet paper.  
- **M4 (Week 4):** HuggingFace datasets (SST‑2/IMDB); Docker‑ready notebooks; safety cell.

### Detailed Workplan
1. **Scaffold (Week 1)**
   - Files:
     ```text
     api/app/materialize/generators/
       __init__.py
       base.py              # CodeGenerator ABC
       dataset.py           # Dataset generators
       model.py             # Model generators
       factory.py           # Selection logic
     ```
   - `CodeGenerator` ABC: `generate_imports(plan)`, `generate_code(plan)`, `generate_requirements(plan)`.
   - Extract current synthetic path into `SyntheticDatasetGenerator` and `SklearnLogisticGenerator`.

2. **Sklearn First (Week 2)**
   - Datasets: `digits`, `iris`, `wine`, `breast_cancer`.  
   - Models: `LogisticRegression`, `RandomForestClassifier`, `SVC`, `KNeighborsClassifier`.  
   - Fallback chain: **HF → torchvision → sklearn → synthetic** (but initially, return sklearn for speed).

3. **Torchvision & PyTorch CNN (Week 3)**
   - Datasets: `MNIST`, `CIFAR10` (CPU‑friendly).  
   - Models: `SimpleCNN` (text/image‑compatible baseline).  
   - Planner’s ResNet paper: map to `torchvision.models.resnet18/resnet50` with reduced epochs.

4. **HuggingFace Datasets (Week 4)**
   - `glue/sst2`, `imdb`, `squad` (tokenized loaders).  
   - Add `OFFLINE_MODE` env var control (cache‑only).

5. **Safety Cell (all phases)**
   - Deterministic seeding (`PYTHONHASHSEED`, NumPy, torch).  
   - CPU‑only guard; max wall‑clock; memory checks; **always** write `metrics.json` with success/fail.

6. **Docker Readiness**
   - Relative paths only; no user‑specific absolute paths.  
   - `Dockerfile` for executor image; ensure notebooks run in container.

### Tests
- **Unit:** factory selection by dataset/model name; generator output contains expected snippets (e.g., `load_digits()`, `resnet18`).  
- **Integration:** materialize a plan → open notebook → assert imports/cells exist; run in a lightweight kernel (local or mocked executor) to ensure `metrics.json` is produced.  
- **E2E:** Plan for ResNet paper yields a notebook that **mentions** `resnet*` and trains for ≥1 epoch with reduced dataset size.

### Observability / SLIs
- Materialization time, notebook size, requirements count, run duration (stub vs later executor).  
- Execution pass rate in Docker; % notebooks using OFFLINE_MODE successfully.

### Risks & Mitigations
- **Risk:** HF datasets blow up time/bandwidth.  
  **Mitigation:** Gate via OFFLINE_MODE + sample‑size caps + early sklearn path.  
- **Risk:** Torch CPU perf on large models.  
  **Mitigation:** Use small subsets/epochs; document “demo mode” defaults.

### Exit Criteria
- Sklearn path working end‑to‑end; Torchvision and HF generators available; notebooks safely runnable under CPU/time caps; green tests.

---

## Cross‑Cutting: CI, Docs, and Ops

- **CI:** 
  - PR: lint, unit, smoke (TextCNN only).  
  - Nightly: full E2E, extraction QA sample evaluation, cost/latency export.  
- **Docs:** 
  - `docs/Claudedocs/CURRENT_STATUS__YYYY‑MM‑DD.md` refreshed per milestone.  
  - Add `docs/dev/materialize_generators.md` (registry, examples, constraints).  
- **Ops/Cost:** 
  - Track OpenAI tool calls & tokens per stage; alert on regressions > 20% WoW.  
  - Add feature flag for `two_phase_extractor` (Phase A retrieval‑only → Phase B emit‑only).

---

## “Definition of Done” per Step

| Step | DoD |
|------|-----|
| 1. Extraction Integration | Claims persisted with `claim_set_id`; typed errors; `claims_count` in SSE; tests green |
| 2. E2E Testing | Smoke on PRs; nightly on 3–5 papers with cost/latency CSV artifacts |
| 3. Extraction Quality | Normalizers + dedup active; sentinel test; ≥90% precision on sample |
| 4. Real Notebooks | Generators modularized; sklearn live; Torchvision/HF added; Docker‑ready safety cell; tests green |

---

## Suggested Sequencing (2 weeks minimum viable; 4 weeks full)

- **Week 1:** Step 1 DoD + Step 2 smoke; begin Step 4 scaffold.  
- **Week 2:** Step 2 nightly; Step 3 normalizers + sentinel; Step 4 sklearn generators live.  
- **Week 3:** Step 4 Torchvision + PyTorch CNN; minimal ResNet path.  
- **Week 4:** Step 4 HuggingFace + Docker validation; polish and docs.

---

## Appendix — Sample Snippets

**Content Hash (Python pseudo‑code):**
```python
def normalize_units(u): return {"percent":"%", "%":"%"}.get((u or "").strip().lower(), (u or "").strip())

def canonical_metric(m): return (m or "").strip().lower()

def content_hash(c):
    ds = (c.dataset_name or "").strip().lower()
    sp = (c.split or "").strip().lower()
    mn = canonical_metric(c.metric_name)
    mv = "" if c.metric_value is None else f"{float(c.metric_value):.3f}"
    un = normalize_units(c.units)
    sc = (c.citation.source_citation or "").strip().lower()
    raw = f"{ds}|{sp}|{mn}|{mv}|{un}|{sc}"
    return sha256(raw.encode("utf-8")).hexdigest()
```

**Safety Cell (notebook header excerpt):**
```python
# Determinism & Safety
import os, random, time, json, signal
import numpy as np

SEED = int(os.getenv("SEED", "42"))
random.seed(SEED); np.random.seed(SEED)

OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"
MAX_RUNTIME_S = int(os.getenv("MAX_RUNTIME_S", "900"))  # 15m
_start = time.time()

def guard():
    if time.time() - _start > MAX_RUNTIME_S:
        raise TimeoutError(f"Exceeded {MAX_RUNTIME_S}s")
guard()

def write_metrics(status="ok", **kw):
    with open("metrics.json", "w") as f:
        json.dump({"status": status, **kw}, f)
```

**E2E smoke (bash):**
```bash
#!/usr/bin/env bash
set -euo pipefail
python manage.py doctor | grep '"responses_mode_enabled": true' >/dev/null

PAPER="uploads/1408.5882.pdf"
PID=$(curl -sS -X POST http://localhost:8000/api/v1/papers/ingest -F "file=@${PAPER}" -F "title=TextCNN" | jq -r .paper_id)

# poll readiness
for i in {1..20}; do
  ready=$(curl -sS "http://localhost:8000/api/v1/papers/${PID}/verify" | jq -r .vector_store_ready)
  [[ "$ready" == "true" ]] && break
  sleep 3
done

# extract
evs=$(curl -sS -N "http://localhost:8000/api/v1/papers/${PID}/extract" | tee /tmp/ex.log)
cnt=$(echo "$evs" | awk '/^event: result/{getline; print}' | sed 's/^data: //' | jq .claims_count)
test "${cnt:-0}" -gt 0
echo "✓ claims_count=$cnt"
```

---

**Prepared by:** PromptOps / Backend  
**Contact:** #p2n‑backend Slack channel
