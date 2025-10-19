# P2N Seed Setup — Ingest Guide (clean/phase2-working)

This guide gets your baseline papers into the system, extracts claims, plans, and materializes notebooks. It also shows optional dataset prefetch for fast/offline runs.

## 0) Folder layout

```
assets/
  papers/                                 # Place PDFs here
docs/
  Claudedocs/
    SeedSetup/
      manifests_seed_papers.csv
      INGEST_GUIDE.md
scripts/
  prefetch_datasets.py                    # (optional) dataset cache warmup
```

## 1) Put PDFs under `assets/papers/`

Use the manifest CSV to download PDFs. Prefer OA (open access) links provided.  
If a DOI is listed instead of direct PDF, use Unpaywall to fetch OA or manually save the article page as PDF.

**Naming:** match the `slug` column in the CSV, e.g.:

```
assets/papers/kim_2014_textcnn.pdf
```

## 2) Ingest each paper

Single:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/ingest"   -F "title=Convolutional Neural Networks for Sentence Classification"   -F "source_url=https://arxiv.org/abs/1408.5882"   -F "file=@assets/papers/kim_2014_textcnn.pdf"
```

Batch (using your script):

```bash
python scripts/reingest_paper_set_v1.py   --manifest docs/Claudedocs/SeedSetup/manifests_seed_papers.csv
```

> The API uploads to Supabase Storage (`papers` bucket), creates an OpenAI vector store, and writes a row in `papers`.

## 3) Extract claims (and persist to DB)

```bash
curl -N -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/extract"
```

Watch for SSE stages:
- `persist_start` → `persist_done` (claims saved)
- final `result` with `claims`

Verify in DB:

```bash
curl -s "http://127.0.0.1:8000/api/v1/papers/{paper_id}/claims"
```

## 4) Plan (Two-Stage: o3-mini → gpt-4o)

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan"   -H "Content-Type: application/json"   -d '{"claims":[{"dataset":"SST-2","split":"test","metric":"accuracy","value":88.1,"units":"%","citation":"Table 2","confidence":0.9}]}'
```

- Stage 1: o3-mini (reasoning + file_search)
- Stage 2: gpt-4o (Responses API with JSON Schema)

## 5) Materialize notebook + requirements (to `plans` bucket)

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/plans/{plan_id}/materialize"
```

The notebook uses **lazy dataset loading**:
- HuggingFace (`load_dataset(..., cache_dir=..., download_mode="reuse_dataset_if_exists")`)
- torchvision (`download=True` caches locally)
- sklearn (bundled)

## 6) Optional: Prefetch datasets

```bash
# Linux/Mac
export DATASET_CACHE_DIR=./data/cache
python scripts/prefetch_datasets.py

# Windows PowerShell
$env:DATASET_CACHE_DIR = ".\data\cache"
python scripts\prefetch_datasets.py
```

Set `OFFLINE_MODE=true` to force cache-only runs.

## 7) Checklist

- [ ] PDF exists under `assets/papers/`
- [ ] Ingest returns 200 OK and `paper_id`
- [ ] Extract SSE shows `persist_done`, GET `/claims` returns items
- [ ] Plan returns `plan_id`
- [ ] Materialize returns 200 OK; assets present in `plans` bucket
- [ ] Notebook contains real dataset loader (no synthetic for known datasets)

## Troubleshooting

- **409 Storage Duplicate:** delete existing plan assets or update code to upsert.
- **o3-mini “web_search not supported”:** ensure web_search is filtered for o3-mini.
- **Claims not saved:** extractor now uses replace policy (delete-then-insert); check logs for `persist_*`.