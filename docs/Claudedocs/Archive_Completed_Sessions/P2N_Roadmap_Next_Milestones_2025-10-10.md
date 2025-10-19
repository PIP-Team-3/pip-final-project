# P2N Roadmap – Next Milestones (2025‑10‑10)

**Status:** Phase 2 Micro‑Milestone 1 **VERIFIED**  
**Branch:** `clean/phase2-working`

## Where we are (short, technical)

- ✅ **Pipeline:** Ingest → Extract (claims) → Plan (two‑stage) → Materialize works.
- ✅ **Two‑stage planner:** o3‑mini (reasoning, file_search) → GPT‑4o (Responses API `json_schema` formatter).
- ✅ **Phase 2 dataset registry:** HuggingFace / torchvision / sklearn generators with **lazy loading**, **cache_dir**, **OFFLINE_MODE**.
- ✅ **Supabase fixes:** SDK update chaining; `plans` bucket for notebook/requirements; path duplication removed.
- ✅ **Claims persistence:** delete‑then‑insert (idempotent), SSE `persist_start` / `persist_done`.
- 🧪 **Ready to test** with new papers; notebooks now load **real datasets** (e.g., `glue/sst2`) instead of synthetic fallback.

---

## Milestone A – Phase 2: Dataset Expansion (M2)

**Goal:** Broaden plug‑and‑play dataset coverage while keeping server stateless.

### A.1 Add more HF/torchvision entries (registry only)
- **HF:** `dbpedia_14`, `yahoo_answers_topics`, `cola`, `qnli`, `snli`, `squad` (streaming where helpful)
- **torchvision:** `SVHN`, `CIFAR100`
- **sklearn:** add `make_moons`, `make_circles` convenience fallbacks

**Acceptance criteria**
- [ ] Generators return correct imports/code/requirements
- [ ] Materialized notebooks use `cache_dir` and run offline with `OFFLINE_MODE=true`
- [ ] Unit tests (≥ 20) verify code string contains expected loaders

### A.2 Minimal CSV/API dataset generator (Phase 2.5)
- **Why:** unlock seed “wow” papers (Bechdel+TMDb, Taxi+NOAA, COMPAS, Bike Sharing)
- **Design:** `CSVLoaderGenerator` + `APILoaderGenerator` with small, safe helpers
- **Features:** path/env‑driven config; schema preview; sample down‑select for CPU budget

**Acceptance criteria**
- [ ] Provide a working CSV loader for **one** public dataset (e.g., COMPAS or Bike Sharing)
- [ ] Provide a working API loader for **one** API‑backed dataset (e.g., TMDb or NOAA)
- [ ] Materialized notebooks log row counts and write a tiny `metrics.json`

**Tests**
- [ ] Unit: code contains `pd.read_csv(...)` with error handling
- [ ] Integration: offline run uses a small cached CSV in repo
- [ ] Docs: `INGEST_GUIDE.md` updated with how to place CSV/API keys

---

## Milestone B – Phase 3: Smart Model Generators (M3)

**Goal:** Produce faithful but budgeted models beyond LogisticRegression.

### B.1 TorchTextCNNGenerator (TextCNN)
- **Scope:** embeddings + conv filters + pooling + classifier; small width/epochs to meet CPU budget
- **Fallbacks:** if GPU requested or OOM → small filters/epochs automatically

**Acceptance criteria**
- [ ] Notebook trains a tiny TextCNN on `glue/sst2` and logs accuracy
- [ ] Runs within 20 min CPU on dev box (document env)
- [ ] Requirements pinned; no CUDA wheels

### B.2 TorchResNetGenerator (vision)
- **Scope:** ResNet‑18 w/ fewer epochs & subset for CIFAR‑10/100; accuracy logged

**Acceptance criteria**
- [ ] Notebook trains a small ResNet variant on CIFAR‑10 within budget
- [ ] Deterministic seeding; accuracy >= baseline

### B.3 SklearnModelGenerator (classic)
- **Scope:** RandomForest, LinearSVM, LogisticRegression
- **Criteria:** unit tests for hyperparam surfaces, data shape validations

---

## Milestone C – Phase 3.1 Runner + Metrics/Evals (M3.1)

**Goal:** Execute notebooks deterministically and capture outputs.

- **Runner:** CPU‑only sandbox; time/ram limits; seeded RNG; write `metrics.json`
- **SSE feed:** surface `metric_update` and `stage_update` during run
- **Artifacts:** store `metrics`, `logs`, `events` in Supabase `assets`

**Acceptance criteria**
- [ ] `/runs` endpoint: create + stream + finalize
- [ ] `metrics.json` uploaded; accuracy shown in UI
- [ ] Re‑runs produce identical metrics (within tolerance)

---

## Milestone D – Phase 3.2 Gap Analyzer (M3.2)

**Goal:** Compare **observed** vs **claimed**; explain the gap.

- Compute gap % and sign; cite possible causes (budget, data size, architecture)
- Persist to `evals` table; show in UI

**Acceptance criteria**
- [ ] Evals plotted on paper page (claimed vs observed)
- [ ] CSV export for dashboard

---

## Milestone E – Phase 4 Packaging (M4)

- Dockerfile + compose; volumes for `DATASET_CACHE_DIR`
- Seed cache volume; prefetch on build (optional)
- CI smoke tests (ingest→extract→plan→materialize)

**Acceptance criteria**
- [ ] One‑command up; healthcheck green
- [ ] CI run succeeds in <10 minutes

---

## Operational Playbook (short)

- Use **plans** bucket for artifacts; `papers` for PDFs
- Always prefetch common datasets on new machines (`scripts/prefetch_datasets.py`)
- Keep two‑stage planner models pinned and response schema strict
- When adding datasets, **registry first**, then generators, then unit tests

---

## Appendix A – Quick daily driver

1) Place PDFs → `assets/papers`
2) Ingest → note `paper_id`
3) Extract → verify `claims`
4) Plan → note `plan_id`
5) Materialize → verify loaders (no synthetic fallback)
6) (Optional) Prefetch datasets; rerun in offline mode