# P2N — CRITICAL FIX PLAN: Two‑Stage Planner Structured Outputs & Phase‑2 Verification
**Date:** 2025-10-10 00:41:26 UTC  
**Scope:** Fix Stage‑2 planner failures, verify dataset‑aware notebooks (Phase 2), keep two‑stage architecture stable.

---

## 🔎 Executive Summary

- **Observed issue:** Two‑stage planner fails schema validation ~80–90% of the time; errors like _“Input should be a valid number”_ indicate **numeric fields returned as strings**.
- **Root cause:** Stage‑2 (gpt‑4o) currently emits **unstructured JSON**; the prompt asks to “match schema”, but no hard schema is enforced.
- **Decision:** **Adopt Structured Outputs for Stage‑2** (Responses API `response_format: json_schema`) and **keep the two‑stage approach**. Add small prompt guardrails as a belt‑and‑suspenders.
- **Status elsewhere:** Materialize MIME issue fixed; Phase‑2 dataset selection logic exists but has **not been validated live** yet.
- **Goal for this cycle:** Raise Stage‑2 success rate to **≥ 90%**, then prove Phase‑2 by generating & inspecting real notebooks that **load the right dataset** (not synthetic).

---

## ✅ Recommended Path (Options compared)

| Option | What it does | Pros | Cons | Decision |
|---|---|---|---|---|
| **A. Prompt hardening only** | Tell Stage‑2 to emit numbers as JSON numbers | Quick | Still brittle; won’t prevent structural drift | **Use as back‑up only** |
| **B. Structured Outputs** | Stage‑2 uses **Responses API** `response_format=json_schema` with our **PlanDocumentV11** schema | Robust typing; fewer retries; deterministic | Slightly more wiring; must pass full schema | **PRIMARY** |
| **C. One‑stage (gpt‑4o only)** | Disable o3‑mini; do analysis + JSON in one step | Less moving parts | Loses the high‑quality reasoning of o3‑mini; cost/quality tradeoffs | **No** (keep two‑stage) |

**We will implement B (Structured Outputs) and retain A as textual guardrails in the prompt.**

---

## 🧩 Exact Implementation (no code changes applied here — use as a patch plan)

### 1) Stage‑2: call **Responses API** with **Structured Outputs**

**Where:** `api/app/routers/plans.py` — Stage‑2 “schema fixer” block.

**Key changes:**  
- Use `client.responses.create(stream=False, …)` with:
  - `response_format={"type": "json_schema", "json_schema": {"name": "plan_document", "schema": PlanDocumentV11.model_json_schema()}}`
  - `temperature=0` (allowed on gpt‑4o) to stabilize JSON
- **Do not stream Stage‑2**; retrieve the **final JSON string**; parse and validate.

**Pseudo‑diff (illustrative):**
```python
# before: streaming + freeform JSON parsing

# after (Stage‑2 structured output, non‑stream):
schema = PlanDocumentV11.model_json_schema()
resp = client.responses.create(
    model=settings.openai_jsonizer_model,  # gpt-4o
    input=[
        { "type": "message", "role": "developer", "content": [{
            "type": "input_text",
            "text": STAGE2_DEV_INSTRUCTIONS  # see below
        }]},
        { "type": "message", "role": "user", "content": [{
            "type": "input_text",
            "text": stage1_output_text  # the o3-mini reasoning text or malformed JSON
        }]}        
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "plan_document",
            "schema": schema,  # full Pydantic v2 JSON schema
            # Optional: "strict_schema": True  (if supported in your SDK build)
        },
    },
    temperature=0,
    max_output_tokens=4096,
)

# extract the single JSON doc from resp.output_text or resp.output[...]
json_text = resp.output_text  # (use the SDK’s accessor you already standardized)
plan = PlanDocumentV11.model_validate_json(json_text)  # strict validation
```

### 2) Stage‑2 prompt guardrails (belt‑and‑suspenders)

**Where:** the Stage‑2 developer message (your “schema fixer” prompt).

Add a block like:
```
CRITICAL JSON RULES:
- All numeric fields **must** be JSON numbers (not strings). Example: "epochs": 10 (✅), "epochs": "10" (❌)
- Use `null` for truly unknown optionals; avoid empty strings.
- Arrays must contain elements of the correct type (e.g., integers for kernel sizes).
- The output must be a **single JSON object** matching the provided JSON Schema **exactly**.
- Do not include any commentary outside the JSON.
```

Keep the rest of your Stage‑2 guidance (mapping from free text → schema) unchanged.

### 3) Stage‑1 (o3‑mini) call hygiene

- Ensure **no unsupported params**: remove `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`.
- Keep `max_output_tokens` high enough (e.g., **8192**) and **filter out `web_search_preview`** in tools.
- Continue to **stream** Stage‑1 and **buffer deltas**; use buffered text if the completion event is flaky.

---

## 🧪 Test Plan (raise Stage‑2 success ≥ 90%)

### A. Unit / Contract tests (fast, no API)

1. **Schema snapshot test**  
   - Assert `PlanDocumentV11.model_json_schema()` contains numeric types for: `epochs`, `batch_size`, `learning_rate`, etc.
   - Rejects strings for numeric fields when `model_validate_json` runs under strict config.

2. **Type coercion negative test**  
   - Feed `"epochs": "10"` to `model_validate_json` and **expect failure** (guards remain strict).

3. **Generator smoke tests (no downloads)**  
   - Given `dataset.name="sst2"`, `GeneratorFactory.get_dataset_generator(plan)` → `HuggingFaceDatasetGenerator`.  
   - Generated code contains `load_dataset("glue", "sst2")` and `cache_dir` handling.  
   - No `make_classification()` appears.

### B. Stage‑2 live tests (API hitting OpenAI)

4. **Deterministic golden case**  
   - Construct a minimal Stage‑1 output with intentionally string‑typed numbers (e.g., `"epochs": "10"`).  
   - Stage‑2 must output the same fields as **JSON numbers**. Validate with Pydantic.

5. **Long reasoning case**  
   - Provide a ~2–4k token Stage‑1 rationale including quotes/citations.  
   - Confirm Stage‑2 produces valid JSON on first try ≥ 80% of runs; if not, retry once.

### C. End‑to‑End plan → notebook

6. **Planner endpoint full run**  
   - Input: claims (e.g., SST‑2 accuracy).  
   - Expect: `200 OK`, valid Plan JSON v1.1, DB persisted.

7. **Materialize**  
   - Generate notebook; **assert** code contains the correct dataset loader:  
     - For SST‑2: `load_dataset("glue", "sst2", cache_dir=...)`  
     - For Fashion‑MNIST: `torchvision.datasets.FashionMNIST(..., download=...)`
   - Assert requirements include: `datasets` (HF) or `torchvision` (vision) as needed.

8. **Smoke execute (optional)**  
   - Run in sandbox with `OFFLINE_MODE=true` and a pre‑seeded cache directory to avoid downloads.  
   - Assert it produces `metrics.json` and logs `dataset_samples` metric.  

**Acceptance:** Stage‑2 structured output success rate **≥ 90%** on 10 consecutive runs; materialized notebooks load the right dataset (no synthetic).

---

## 📦 Phase‑2 Verification Checklist (Datasets & Notebooks)

- [ ] Registry present with: `sst2`, `imdb`, `ag_news`, `trec`, `mnist`, `fashionmnist`, `cifar10` (+ aliases).  
- [ ] Factory routes to correct generator per dataset family (HF/torchvision/sklearn).  
- [ ] Notebook includes cache/offline env vars (`DATASET_CACHE_DIR`, `OFFLINE_MODE`, `MAX_TRAIN_SAMPLES`).  
- [ ] Requirements reflect the chosen generator (`datasets` or `torchvision` or pure sklearn).  
- [ ] No `make_classification()` if a known dataset is selected.  
- [ ] SSE emits `stage_update: dataset_load` before data prep.  

---

## 📚 Paper Selection Policy (what to reproduce first)

To ensure reliable demos and fast runs under CPU limits, prioritize:

### Tier A — Fast & fully accessible
1. **Kim (2014) – CNN for Sentence Classification** — focus on **SST‑2**, **TREC**, **IMDB**, **AG News**.  
   - Paper: https://arxiv.org/abs/1408.5882  
   - Datasets:  
     - GLUE **SST‑2**: https://huggingface.co/datasets/glue  
     - **TREC**: https://huggingface.co/datasets/trec  
     - **AG News**: https://huggingface.co/datasets/ag_news  
     - **IMDB**: https://huggingface.co/datasets/imdb  

2. **Fashion‑MNIST** (Xiao et al., 2017) — torchvision loader.  
   - Paper: https://arxiv.org/abs/1708.07747

3. **IMDB** sentiment (Maas et al., 2011) — HF loader.  
   - Paper: https://ai.stanford.edu/~amaas/papers/wvSent_acl2011.pdf

### Tier B — Common baselines (OK with subsampling)
4. **Char‑CNNs** (Zhang et al., 2015) — start with **AG News**.  
   - Paper: https://arxiv.org/abs/1509.01626

5. **MNIST / CIFAR‑10** baselines — torchvision loaders.  
   - MNIST: http://yann.lecun.com/exdb/mnist/  
   - CIFAR‑10: https://www.cs.toronto.edu/~kriz/cifar.html  

### Tier C — Heavier / partial reproductions
6. **ResNet (2015)** — run on **CIFAR‑10** with ResNet‑18/34 under CPU.  
   - Paper: https://arxiv.org/abs/1512.03385

7. **BERT (2018)** — **fine‑tune** on SST‑2; no pre‑training.  
   - Paper: https://arxiv.org/abs/1810.04805

---

## ⚙️ Guardrails & Resilience

- **Stage‑1 toolset:** o3‑mini **without** `web_search_preview`; keep File Search only.  
- **Stage‑2 determinism:** `temperature=0` and structured output; re‑try once on parse error.  
- **Strict validation stays on:** we want the model to conform, not the validator to coerce.  
- **Fallbacks:** if dataset unresolved → synthetic generator; log a `WARN` and add the dataset to registry in a follow‑up PR.  

---

## 📈 Observability & Tuning

- Log Stage‑2 payload keys: `response_format`, `model`, `max_output_tokens`, and the byte length of JSON.  
- Emit SSE `stage_update` milestones: `plan_stage2_start`, `plan_stage2_done`, and `schema_validate_pass|fail`.  
- Track rolling success rate (last 20 runs) and median latency for Stage‑1 and Stage‑2 separately.  

---

## 🗺️ Milestones & Acceptance

1) **M1 — Stage‑2 Structured Outputs**  
   - Code switched to Responses API structured outputs (non‑stream).  
   - ≥ 90% success on 10 consecutive runs.  
   - Pydantic strict validation passes.  

2) **M2 — Phase‑2 Dataset Verification**  
   - Planner → Materialize produces notebooks that load real datasets for **SST‑2**, **IMDB**, **Fashion‑MNIST**.  
   - Requirements correctly reflect loaders.  
   - SSE shows `dataset_load` and `dataset_samples`.  

3) **M3 — Execution Dry‑Run (optional)**  
   - Run notebooks in sandbox with `OFFLINE_MODE=true` and pre‑cached datasets.  
   - Capture `metrics.json` and logs.  

When M1 & M2 pass, Phase‑2 can be marked **complete**.

---

## 🧰 Rollback / Fallback Paths

- If structured outputs become unstable, **temporarily**:
  - Add pre‑validation sanitizer that converts known numeric fields from strings → numbers.
  - As a last resort, run single‑stage gpt‑4o with `response_format=json_schema` (lower reasoning quality).

---

## 📋 Action Items (sequenced)

1. Wire Stage‑2 to Responses API **structured outputs** (non‑stream).  
2. Add prompt guardrails for numeric types & “JSON only” output.  
3. Remove unsupported params from Stage‑1 (o3‑mini); keep file_search only.  
4. Write unit + live tests above; run 10× loop to confirm ≥ 90% pass.  
5. Validate notebooks for **SST‑2 / IMDB / Fashion‑MNIST** (no synthetic).  
6. Document results; update status docs and roadmap.  

---

*Prepared for implementation; copy/paste diffs into your codebase. No runtime changes were made by this document.*
