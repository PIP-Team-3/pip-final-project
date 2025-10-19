# P2N Seed Setup — Ingest Guide

This guide shows how to place PDFs, ingest them through the API, extract claims, plan, and materialize notebooks. It also covers prefetching datasets for offline/fast runs.

> Branch: `clean/phase2-working`

## 0) Where to put things in your repo

- **PDFs** → `assets/papers/` (create if missing)
- **Manifest CSV** → `docs/Claudedocs/SeedSetup/manifests_seed_papers.csv` (or keep in the seed folder)
- **Dataset Prefetch Script** → `scripts/prefetch_datasets.py` (you can also leave it in the seed folder)

### Suggested commit layout
```
docs/
  Claudedocs/
    SeedSetup/
      manifests_seed_papers.csv
      INGEST_GUIDE.md
scripts/
  prefetch_datasets.py
assets/
  papers/   # place downloaded PDFs here
```

## 1) Place PDFs under `assets/papers/`

Use Unpaywall to find OA PDFs for DOIs (or arXiv/ACL/NBER links in the manifest). Name files to match the `slug` column. Examples:

```
assets/papers/kim_2014_textcnn.pdf
assets/papers/joulin_2016_fasttext.pdf
assets/papers/zhang_2015_charcnn.pdf
```

## 2) Ingest each paper

The API will upload the PDF to Supabase Storage (`papers` bucket), create an OpenAI vector store, and write a `papers` row.

```bash
# Replace with real file and title
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/ingest"   -F "title=Convolutional Neural Networks for Sentence Classification"   -F "source_url=https://arxiv.org/abs/1408.5882"   -F "file=@assets/papers/kim_2014_textcnn.pdf"
```

If you prefer batch mode, use your existing script:
```
python scripts/reingest_paper_set_v1.py --manifest docs/Claudedocs/SeedSetup/manifests_seed_papers.csv
```
or use a simple loop that posts each CSV row.

## 3) Extract claims

```bash
curl -N -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/extract"
# Look for SSE: stage 'persist_done' and final 'result' list of claims
```

Verify persistence:
```bash
curl -s "http://127.0.0.1:8000/api/v1/papers/{paper_id}/claims"
```

## 4) Plan (two-stage planner)

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan"   -H "Content-Type: application/json"   -d '{"claims":[{"dataset":"SST-2","split":"test","metric":"accuracy","value":88.1,"units":"%","citation":"Table 2","confidence":0.9}]}'
```

- Stage 1: **o3-mini** produces detailed reasoning (file_search only; web_search filtered).
- Stage 2: **gpt-4o** converts to **Plan JSON v1.1** via Responses API **json_schema** output.

## 5) Materialize notebook + requirements

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/plans/{plan_id}/materialize"
# Uploads to the 'plans' bucket; creates 'notebook' and 'requirements' assets
```

Notebook code uses **lazy-loading**:
- **HuggingFace** datasets (e.g., `glue/sst2`, `ag_news`) with `cache_dir` and `download_mode="reuse_dataset_if_exists"`
- **torchvision** datasets (`MNIST`, `CIFAR10`) with `download=True` (checks cache first)
- **sklearn** datasets (tiny) bundled

## 6) Prefetch datasets (optional but recommended)

To speed up first runs and enable offline execution, pre-cache common datasets.

```bash
# Linux/Mac
export DATASET_CACHE_DIR=./data/cache
python scripts/prefetch_datasets.py

# Windows PowerShell
$env:DATASET_CACHE_DIR = ".\data\cache"
python scripts\prefetch_datasets.py
```

**Offline runs:** set `OFFLINE_MODE=true` in your runner or environment; loaders will avoid downloads and use cache only.

## 7) Quick checklist (per paper)

- [ ] PDF placed under `assets/papers/`
- [ ] Ingest: 200 OK → returned `paper_id`
- [ ] Extract: SSE shows `persist_done`; GET `claims` returns items
- [ ] Plan: 200 OK → returned `plan_id`
- [ ] Materialize: 200 OK → assets created in `plans` bucket
- [ ] (Optional) Prefetch run completed; cache exists
- [ ] Notebook verified to include real dataset loader (no synthetic fallback for known datasets)

---

## Troubleshooting

- **409 Duplicate (storage)**: plan assets already exist. Re‑materialize after deleting existing assets in Storage or adjust code to `update` on conflict.
- **o3-mini tool error**: ensure web_search is filtered for o3‑mini; Responses API used for Stage 2.
- **No claims persisted**: extractor now deletes‑then‑inserts (replace policy); check logs for `persist_start`/`persist_done`.