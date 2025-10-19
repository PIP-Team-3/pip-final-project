# P2N — Planner Refactor & Next Milestones (Soft Sanitizer Path)
**Date:** 2025-10-19  
**Branch:** `clean/phase2-working`

---

## 🔎 Synopsis — What broke, why, and what we’re changing

### The symptom (what you saw)
- **Stage‑1 (o3‑mini)** produced excellent prose with File Search citations for CharCNN (AG News, DBpedia, Yelp, etc.). ✅
- **Stage‑2 (gpt‑4o)** sometimes returned:
  - **Invalid types** (numbers as strings) → `E_PLAN_SCHEMA_INVALID`.
  - **Guardrail failure** when **any unregistered/blocked dataset** appeared (e.g., ImageNet / unknown license) → `E_PLAN_GUARDRAIL_FAILED`.
  - With strict `json_schema` we then hit the platform rule: **schema must set `additionalProperties: false`** everywhere, otherwise the API rejects the response‑format.

### The root cause (why this is happening)
- We upgraded Stage‑2 to strict structured outputs but:
  1) Some of our Pydantic‑generated schema objects do **not** enforce `additionalProperties: false` at every nested level, which Responses API requires in strict mode.  
  2) The **license guardrail** was **hard‑fail**: if Stage‑1 mentions any dataset that isn’t in our registry (or is large / restricted), Stage‑2 dutifully encodes that → guardrail rejects the whole plan even though we could simply **resolve** to an allowed dataset (e.g., AG News) or **omit** the restricted one.

### The ask (what we need now)
- **Unblock planning immediately** while we finish the full strict‑schema migration:
  - Use a **soft sanitizer** in Stage‑2 result handling to coerce types, strip extraneous keys, and **resolve/omit** out‑of‑policy datasets **without failing the whole plan**.
  - Keep hard guardrails for truly dangerous items, but **downgrade** dataset‑license failures to **rewrite + warn** so we still produce a runnable plan for covered datasets.

---

## 🧭 Proposed refactor — “Soft Sanitizer” in Stage‑2

### What stays the same
- **Two‑stage planner**: o3‑mini → gpt‑4o (Responses API).  
- Stage‑1 uses **File Search**; Stage‑2 formats to Plan v1.1.

### What changes
1) **Response sanitization layer** (post Stage‑2):
   - **Type coercion**: `"10"` → `10`, `"0.5"` → `0.5`; `"true"`/`"false"` → booleans.
   - **Key pruning**: drop unknown fields per schema (“`additionalProperties: false`” effect).
   - **Dataset resolution**:
     - If **not** in registry or **blocked**: remove that claim/dataset from plan and add a **`warnings[]`** entry.
     - Prefer **canonical registry name** (e.g., `"AG News"` → `"ag_news"`).
   - **Justifications fixup**: if Stage‑1 prose provided paper quotes, move them into the required nested `justifications.{dataset|model|config}.{quote,citation}` shape.
   - **If after pruning no datasets remain** → fail closed with a **clear typed error** telling the user how to proceed (“add DBpedia to registry or choose a covered dataset”).

2) **Guardrail policy tweak**:
   - Dataset license / registry issues → **rewrite + warn**, not fatal.  
   - Still fatal for: prohibited tools, missing mandatory sections, or empty final plan.

3) **Non‑strict Stage‑2 request** (temporary):
   - Use `response_format={"type": "json_object"}` for Stage‑2 to maximize yield, and let the **sanitizer** enforce (and document) strictness **post‑hoc**.
   - Keep a feature flag to re‑enable **strict `json_schema`** once we finish the schema pass adding `additionalProperties: false` recursively.

> Result: we ship runnable plans for **covered datasets** immediately, and the pipeline won’t stall just because Stage‑1 mentions an unregistered dataset.

---

## ✅ What we already fixed / verified
- **Phase‑2 Micro‑Milestone 1**: notebooks load **real datasets** (HF/torchvision/sklearn) with lazy caching; ImageNet intentionally falls back to synthetic.  
- **Supabase**: SDK update chaining; artifacts in `plans` bucket; duplicate upload handling; claims persistence is **idempotent** with delete‑then‑insert.

---

## 🧩 What we’ll implement now (F‑series milestones)

### F1 — Soft Sanitizer in Stage‑2 (NOW)
**Goal:** Always return a runnable plan for covered datasets; coerce types; prune extras; resolve/omit restricted datasets; add `warnings[]`.

**Changes**
- `api/app/routers/plans.py`
  - After Stage‑2, run `sanitize_plan(plan_json, registry, policy)`:
    - Coerce numbers/booleans/nulls.
    - Remove unknown keys (simulate `additionalProperties: false`).
    - Map datasets to canonical registry IDs; drop and warn blocked/unknown.
    - Normalize justifications `{quote,citation}` from Stage‑1 prose.
  - If `datasets[]` becomes empty → `E_PLAN_NO_ALLOWED_DATASETS` with actionable message.
- **Logs & SSE**: add `stage_update: "sanitize_start"|"sanitize_done"`, include `warnings_count`.

**Acceptance**
- CharCNN (AG News) → PASS (no failure if DBpedia also appears in prose).
- ResNet (CIFAR‑10) → PASS.
- DenseNet (CIFAR‑100) → PASS.
- MobileNetV2 (ImageNet) → plan excludes ImageNet, warns, still materializes.

---

### F2 — Registry‑only Planner Mode (Prompt + Allowlist)
**Goal:** Reduce Stage‑2 work by **constraining Stage‑1** to registry items.

**Changes**
- Planner system prompt: “**Only** plan for datasets present in our registry and **present in the claims**; omit others.”
- Optional allowlist passed in request (`claims[].dataset`) is included in Stage‑1 input (“pick from these only”).

**Acceptance**
- Stage‑1 prose focuses on covered datasets; Stage‑2 receives cleaner content; sanitizer produces 0–1 warnings.

---

### F3 — DBpedia‑14 & SVHN (Registry + Tools Sync)
**Goal:** Cover more CharCNN/fastText and DenseNet claims.

**Changes**
- `dataset_registry.py`: add `dbpedia_14` (HF) & `SVHN` (torchvision).
- Sync **function tools** dataset map (if still enabled) to registry entries.

**Acceptance**
- CharCNN + DBpedia → emits `load_dataset("dbpedia_14")`.
- DenseNet + SVHN → emits `torchvision.datasets.SVHN`.

---

### F4 — TorchTextCNNGenerator (Phase‑3 start)
**Goal:** First “smart” model generator for NLP; runnable within 20‑minute CPU budget.

**Changes**
- `generators/model.py`: `TorchTextCNNGenerator`
  - Small embeddings + 1–2 conv filter widths + max‑pool + linear head.
  - Deterministic seeding; sub‑sampled dataset; metrics logged to `metrics.json`.
- `factory.py`: map plan.model ~ “textcnn” or dataset family to this generator.

**Acceptance**
- Materialized SST‑2 notebook trains a tiny CNN and logs accuracy; ≤ 20 min CPU on dev laptop.

---

### F5 — Runner Shim & Metrics (M3.1)
**Goal:** Execute notebooks locally (CPU) and upload `metrics.json`, `logs`, `events` to `assets` bucket; SSE live progress.

**Changes**
- `runs/executor_local.py` and `routers/runs.py`
- Use `papermill` or `nbclient` + time/memory limits; stream console to SSE.

**Acceptance**
- `/runs` produces artifacts; deterministic metrics between runs (within tolerance).

---

### F6 — Gap Analyzer (M3.2)
**Goal:** Compare observed vs. claimed metrics; store to `evals` and surface in UI.

**Acceptance**
- Paper page shows claimed vs. observed; CSV export works.

---

## 🧪 Test plan (thin but strong)

- **Unit**: sanitizer coercion (`"10"`→10), key pruning, dataset mapping (aliases→canonical), quote extraction shim → nested justifications.  
- **Integration**: CharCNN(AG‑News), ResNet(CIFAR‑10), DenseNet(CIFAR‑100), MobileNetV2(ImageNet) → **no fatal guardrail**; sanitized plans materialize.  
- **Smoke**: ingest→extract→plan→materialize for one NLP + one vision in CI within 10 minutes.

---

## 📣 Developer notes

- Keep **Stage‑2 strict mode** behind a feature flag; once we propagate `additionalProperties:false` through the Pydantic schema tree, flip back to strict Responses `json_schema`.  
- Prefer **warnings and rewrites** over hard failures for dataset licensing unless the user explicitly requests “strict licensing”.  
- Document `warnings[]` in plan payload; surface to UI so users understand substitutions/omissions.

---

## 🧰 Context rehydration prompt (for a fresh Claude Code chat)

> **Role:** You are the PromptOps/Code copilot for the P2N project.  
> **Branch:** `clean/phase2-working`.  
> **Authoritative docs:**  
> – `docs/Claudedocs/P2N_MILESTONE_UPDATE__PLANNER_REFACTOR_2025-10-19.md` (this file)  
> – `docs/Claudedocs/SeedSetup/INGEST_GUIDE.md`  
> – `api/app/materialize/generators/dataset_registry.py`  
> – `api/app/routers/plans.py`  
>  
> **Invariants:** Use **OpenAI Responses API**; File Search uses the paper’s `vector_store_id`; planner is two‑stage (o3‑mini → gpt‑4o).  
>  
> **First actions (don’t ask, do):**  
> 1) Implement **F1 Soft Sanitizer** in `plans.py` (coercion, pruning, dataset resolve/omit with warnings, justifications shim).  
> 2) Add `stage_update` logs for `sanitize_start/done`.  
> 3) Add unit tests for sanitizer functions.  
>  
> **Acceptance:** CharCNN(AG‑News) & ResNet(CIFAR‑10) plans pass and materialize; MobileNetV2(ImageNet) warns and omits ImageNet but plan still materializes.  
>  
> **Do not** modify extractor. Avoid adding new tools; prefer registry + sanitizer.

---

## 📍 File path to commit

Place this file at:  
`docs/Claudedocs/Milestones/P2N_MILESTONE_UPDATE__PLANNER_REFACTOR_2025-10-19.md`

> **Archive relocation (2025-10-19):** This document now lives at
> `docs/history/2025-10-19_P2N_Planner_Refactor.md`. Keep the original instruction
> above for historical accuracy.
