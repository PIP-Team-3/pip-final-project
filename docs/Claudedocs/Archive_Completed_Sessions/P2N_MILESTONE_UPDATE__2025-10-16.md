# P2N — Seed Setup Completion & Next Milestones
**Date:** 2025-10-16  
**Branch:** `clean/phase2-working`

---

## 📌 Executive Summary

- ✅ **Phase 2 Micro‑Milestone 1 VERIFIED** — notebook materialization now produces **real dataset loaders** (e.g., `load_dataset("glue", "sst2")`) instead of synthetic fallbacks when the dataset is covered by the registry.
- ✅ **Supabase fixes**: SDK update chaining bug resolved; artifact uploads use **plans** bucket and correct paths; duplicate/409 handled; claims persistence now **replace-policy** (delete‑then‑insert) and **idempotent**.
- ✅ **Two‑stage planner** stable: **o3‑mini** (reasoning, file search) → **gpt‑4o Responses API** (schema‑strict JSON via `json_schema`), with numeric type guardrails.
- ✅ **Dataset registry expanded**: +7 entries (HF + torchvision) and lazy‑loading with `cache_dir`, `OFFLINE_MODE`, and CPU‑friendly sample limits.
- 🧪 **11 seed papers ingested**, **claims extracted for 4 ML/NLP papers**; ready to run Phase‑2 verification tests across NLP and vision.

> TL;DR: End‑to‑end (ingest → extract → plan → materialize) is **operational** with real datasets where covered, and safe fallbacks when not. Next: broaden registry + add model generators (TextCNN/ResNet) + runner shim.

---

## 📊 What We Just Accomplished (Seed Setup Summary)

### Papers Ingested (11)

#### NLP (3)
| Slug | Title | Paper ID | Claims | Datasets |
|---|---|---|---:|---|
| `kim_2014_textcnn` | TextCNN | `15017eb5-68ee-4dcb-b3b4-1c98479c3a93` | 28 (pre‑existing) | SST‑2, TREC, MR |
| `joulin_2016_fasttext` | fastText | `412e60b8-a0a0-4bfc-9f5f-b4f68cd0b338` | 13 (pre‑existing) | AG News, DBpedia, Yelp, Yahoo |
| `zhang_2015_charcnn` | CharCNN | `8479e2f7-78fe-4098-b949-5899ce07f8c9` | **7 NEW** | AG News, DBpedia, Yelp, Yahoo |

#### Vision (3)
| Slug | Title | Paper ID | Claims | Datasets |
|---|---|---|---:|---|
| `he_2015_resnet` | ResNet | `f568a896-673c-452b-ba08-cc157cc8e648` | **5 NEW** | ImageNet, CIFAR‑10 |
| `sandler_2018_mobilenetv2` | MobileNetV2 | `a2f98794-2af9-43b0-b45e-a2b4fff0e4c1` | **3 NEW** | ImageNet, COCO, PASCAL VOC |
| `huang_2017_densenet` | DenseNet | `3e585dc9-5968-4458-b81f-d1146d2577e8` | **5 NEW** | CIFAR‑10, CIFAR‑100, SVHN |

#### Public Interest (5)
| Slug | Title | Paper ID | Claims | Notes |
|---|---|---|---:|---|
| `farber_2015_taxi_weather` | Taxi + Weather | `f99a15d2-d5c9-4eb0-b02c-cffb10fe8447` | — | TLC/NOAA data |
| `eia930_temp_load` | Electricity + Temperature | `b112dad4-326c-433c-af5e-a0020f478767` | — | EIA Open Data |
| `hardt_2016_equality_of_opportunity` | ML Fairness | `a865b40b-982c-4749-8b21-e02de388f6bf` | — | UCI Adult |
| `reagan_2016_emotional_arcs` | Story Arcs | `8bcbd3c7-e80b-4b2b-889a-4ff0cbc32249` | — | Gutenberg |
| `miller_sanjurjo_2018_hot_hand` | Hot Hand Fallacy | `36025869-6ee1-4240-af0d-ee1a2490b04c` | — | Simulation‑based |

### Extracted Claims (new highlights)

- **CharCNN** (7): AG News (7.64% err), DBpedia (1.31%), Yelp Polarity (4.56%), Yahoo (31.49%), etc.  
- **ResNet** (5): ImageNet top‑5 4.49% (val), CIFAR‑10 6.43% (test), VOC/COCO mAP, etc.  
- **MobileNetV2** (3): ImageNet top‑1 72.0%, VOC mIOU 75.32%, COCO 22.1 mAP.  
- **DenseNet** (5): CIFAR‑10 3.46%, CIFAR‑100 17.18%, etc.

---

## 🧱 Platform Fixes Locked In

- **Supabase SDK compatibility:** removed invalid `.select()` after `.update().eq()` chains; use `execute()` + record handling.
- **Artifacts to Storage:** use **plans** bucket; removed duplicated `plans/` prefix; handle **409 Duplicate** safely.
- **Claims persistence:** **replace‑policy** (delete‑then‑insert) with SSE `persist_start` / `persist_done`; idempotent on re‑extract.
- **Planner Stage‑2:** migrated to **Responses API** with `json_schema` (strict) + numeric type guardrails → high pass rate.

---

## 📦 Phase‑2 Dataset Registry (current state)

**HF (HuggingFace):** `glue/sst2`, `imdb`, `ag_news`, `yahoo_answers_topics`, `yelp_polarity`, `trec`  
**torchvision:** `CIFAR10`, `CIFAR100`, `MNIST`  
**sklearn:** `digits`, `iris`

> **Not in registry (fallback → synthetic):** ImageNet, PASCAL VOC, MS COCO, SVHN, Sogou, Amazon Reviews, **DBpedia‑14 (candidate to add)**.

**Notebook generation** already supports: lazy‑loading; `cache_dir`; `OFFLINE_MODE`; sub‑sampling to respect CPU/time budgets.

---

## 🧪 What to Test Immediately (Phase‑2 verification)

1) **CharCNN + AG News** → expect `load_dataset("ag_news")` (no `make_classification`).  
2) **ResNet + CIFAR‑10** → expect `torchvision.datasets.CIFAR10`.  
3) **DenseNet + CIFAR‑100** → expect `torchvision.datasets.CIFAR100`.  
4) **MobileNetV2 + ImageNet** → expect **synthetic fallback** (registry intentionally excludes ImageNet).

---

## 🚀 Next Milestones (Updated)

### Milestone A — Phase‑2: Dataset Expansion (M2)

**A.1 Add entries (registry only)**  
- HF: `dbpedia_14` (⭐), `cola`, `qnli`, `snli`, `squad`  
- torchvision: `SVHN` (⭐)  
- sklearn: `make_moons`, `make_circles`

**A.2 Minimal CSV/API dataset loader (Phase 2.5)**  
- `CSVLoaderGenerator` (COMPAS or Bike Sharing) with path/env controls and schema preview  
- `APILoaderGenerator` (TMDb or NOAA) with small helper and caching

**Acceptance**  
- ✔ Generators emit correct imports/code/requirements  
- ✔ Unit tests validate emitted code contains the right loaders and cache handling  
- ✔ Offline runs work with pre‑cached files

---

### Milestone B — Phase‑3: Smart Model Generators (M3)

**B.1 TorchTextCNNGenerator (TextCNN)**  
- Tiny embedding + conv + pooling + head; budgeted epochs; logs accuracy

**B.2 TorchResNetGenerator (vision)**  
- ResNet‑18 for CIFAR‑10/100 with sub‑sampling; logs accuracy; deterministic seeding

**B.3 SklearnModelGenerator (classic)**  
- RandomForest, LinearSVM, LogisticRegression; input validation & tests

**Acceptance**  
- ✔ Runs ≤ 20 minutes CPU on dev laptop; deterministic; accuracy reported to `metrics.json`  
- ✔ Requirements pinned; **no CUDA wheels**

---

### Milestone C — Phase‑3.1 Runner + Metrics/Evals (M3.1)

- CPU‑only local runner shim; stream `stage_update`/`metric_update`  
- Persist `metrics.json`, `logs.txt`, `events.jsonl` to **assets**

**Acceptance**  
- ✔ `/runs` executes notebooks and uploads artifacts  
- ✔ Re‑runs deterministic within tolerance

---

### Milestone D — Phase‑3.2 Gap Analyzer (M3.2)

- Compute `gap_percent` and store to `evals`  
- Simple explanations (subset data, fewer epochs, different model) with citations

**Acceptance**  
- ✔ Paper page shows claimed vs observed bars  
- ✔ CSV export for dashboard

---

### Milestone E — Phase‑4 Packaging (M4)

- Dockerfile + compose; persistent volume for `DATASET_CACHE_DIR`; CI smoke test

**Acceptance**  
- ✔ One‑command up; healthcheck OK; CI smoke in < 10 mins

---

## 🧩 Micro‑Milestones for Claude Code (copy/paste)

> Use these as “tickets” in a fresh Claude Code chat. Each has a **Goal**, **Files**, **Steps**, **Tests**, **Done When**.

### MM‑A1 — Add `dbpedia_14` to registry
- **Goal:** Codegen emits HF loader for DBpedia‑14
- **Files:** `api/app/materialize/generators/dataset_registry.py`
- **Steps:**
  1. Add `dbpedia_14` with `hf_path=("dbpedia_14",)`
  2. Ensure generator adds `datasets` to requirements
  3. Unit test: code string contains `load_dataset("dbpedia_14")`
- **Tests:** run the unit; materialize CharCNN DBpedia claim
- **Done When:** notebook contains `load_dataset("dbpedia_14", ...)`

### MM‑A2 — Add `SVHN` to registry
- **Goal:** Codegen emits `torchvision.datasets.SVHN`
- **Files:** `dataset_registry.py`, `dataset.py`
- **Steps:**
  1. Add `SVHN` metadata (class `SVHN`, typical size ~100MB)
  2. Generator emits code with `download=not OFFLINE_MODE`
  3. Unit test: code contains `datasets.SVHN`
- **Done When:** CIFAR/ResNet path can be re‑used for SVHN claim

### MM‑A3 — CSV loader prototype (COMPAS)
- **Goal:** `CSVLoaderGenerator` loads a repo‑cached CSV, logs row counts
- **Files:** `generators/dataset.py` (new class), `factory.py`
- **Steps:**  
  1. Accept `DATASET_CSV_PATH` env var; load with `pd.read_csv`  
  2. Split train/test; write `metric_update` with counts  
  3. Unit test: code string contains `pd.read_csv` and env usage
- **Done When:** notebook runs offline using a small CSV in `assets/datasets/`

### MM‑B1 — TorchTextCNNGenerator
- **Goal:** Tiny TextCNN that runs ≤ 20 min CPU
- **Files:** `generators/model.py`, `factory.py`
- **Steps:**  
  1. Implement module (embeddings + 1–2 filter widths)  
  2. Map plan hyperparams with safe defaults  
  3. Log accuracy to `metrics.json`
- **Tests:** compile check; smoke run on small SST‑2 subset
- **Done When:** `metrics.json` has `accuracy`

### MM‑C1 — Runner shim
- **Goal:** Execute notebook with time/memory limit; upload artifacts
- **Files:** `api/app/runs/executor_local.py`, `routers/runs.py`
- **Steps:**  
  1. Run via `papermill`/`nbconvert`  
  2. Stream output lines to SSE; collect metrics/logs  
  3. Upload to `assets` bucket
- **Done When:** `/runs` → artifacts uploaded; SSE shows progress

---

## 🤝 Parallel Workstreams (team)

- **Back‑end (you):** MM‑A1/A2 then B1 (TextCNN), then C1 (runner)  
- **Front‑end (partner team):** paper detail page → claims table → plan viewer → SSE run console  
- **Data ops:** prepare a tiny cache (`DATASET_CACHE_DIR`) volume; seed common datasets

---

## 📂 Where to store this file

Add to your repo at:  
`docs/Claudedocs/Milestones/P2N_MILESTONE_UPDATE__2025-10-16.md`

---

## ✅ Quick Success Checklist

- [ ] CharCNN + AG News materializes with `load_dataset("ag_news")`  
- [ ] ResNet + CIFAR‑10 materializes with `torchvision.datasets.CIFAR10`  
- [ ] DenseNet + CIFAR‑100 materializes with `torchvision.datasets.CIFAR100`  
- [ ] MobileNetV2 + ImageNet → synthetic fallback (by design)  
- [ ] Add `dbpedia_14` + `SVHN` (then re‑test CharCNN/fastText/ResNet paths)  
- [ ] Implement TextCNN generator; log accuracy in `metrics.json`  
- [ ] Add runner shim; persist run artifacts  
- [ ] CI smoke covers ingest → extract → plan → materialize
