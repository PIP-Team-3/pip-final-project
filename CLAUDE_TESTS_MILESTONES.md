# P2N — Claude 4.5 Milestone Tests • v1.0

> Paste relevant sections into Claude 4.5 after Codex completes each milestone. Each test block includes **Inputs**, **What to Inspect**, **Run/Observe**, **Expected Evidence**, and **Pass/Fail**.

---

## Milestone A — Agents + Hosted Tools + Streaming (no training)

**Objective:** End‑to‑end: Upload → Extract (citations) → Plan (validated) → Storybook (static) with **streaming** and **tracing** visible.

### Inputs
- Two seed PDFs (CIFAR‑10 baseline, SST‑2 baseline).  
- AGENTS.md v1.1 present; Prompt Pack P‑A0…P‑A15 completed.

### What to Inspect
- `/api/app/config/llm.py`: model selection, tracing default ON.  
- `/api/app/agents/*`: Extractor/Planner/EnvSpec/CodeGenDesign/Kid‑Explainer definitions with **structured outputs** and **guardrails**.  
- `/api/app/tools/*`: function tools; hosted tools registration and **per‑run caps**.  
- `/api/app/routes/`: endpoints for ingest, extract (stream), plan (stream), kid explain.  
- `/api/app/streaming/*`: SSE mapping of token + run‑item events.  
- `/sql/*`: schema + RLS.  
- `/web/`: minimal UI shows streaming and JSON views.

### Run / Observe
1) Ingest both PDFs. Confirm: `{paper_id, vector_store_id}` stored; Storage path present.  
2) Extract: run extractor; confirm **File Search** calls appear in traces; output claims have **citations + confidence**.  
3) Plan: run planner; confirm **Web Search** calls (≤ cap); plan passes schema + license + budget guardrails.  
4) Kid‑Explainer: storyboard JSON (5–7 pages + alt‑text).  
5) Streaming: observe SSE receiving token deltas + tool events.  
6) Tracing: capture trace URLs for both runs.  
7) Admin caps: verify counters increment and caps block at limits with friendly error.

### Expected Evidence
- File paths + line ranges showing structured outputs and guardrails.  
- API responses: claims (with citations), Plan JSON (redacted), storyboard JSON.  
- SSE transcript snippet: `stage_update`, `log_line`.  
- Trace URLs, with tool calls visible.  
- Admin usage counters before/after.

### Pass/Fail
- **Pass** if: all outputs present, guardrails enforce policy, SSE + tracing work, caps enforced.  
- **Fail** if: missing citations, unguarded plan, no traces, caps ignored, or SSE silent.

---

## Milestone B — Evaluate‑Only (no training)

**Objective:** Compute metrics on small eval set; produce `metrics.json`, `gap` report; update Storybook final page.

### Inputs
- A plan referencing an eval‑only flow (tiny subset).  
- Worker stub that computes metrics deterministically (no GPU/network).

### What to Inspect
- `/api/app/routes/run_eval_only.*` (or equivalent).  
- Metrics writer and `gap_calculator` tool usage.  
- Artifact persistence (metrics.json, logs).  
- Pro report page (claims, plan, gap).

### Run / Observe
1) Trigger evaluate‑only run; watch SSE for `metric_update`.  
2) Confirm `metrics.json` written and stored; `gap` computed.  
3) Storybook’s final bar updates with observed vs claimed.  
4) Tracing shows run + tool calls; no hosted Code Interpreter here.

### Expected Evidence
- `metrics.json` excerpt with metric name/value/split.  
- Gap calculation output (delta %).  
- SSE snippet showing `metric_update`.  
- Trace link.

### Pass/Fail
- **Pass**: metrics produced and stored; gap reported; Storybook updated.  
- **Fail**: missing metrics, no gap, no storage, or Storybook not updated.

---

## Milestone C — Full CPU Runs (Top‑3)

**Objective:** Deterministic notebook execution in sandbox (network‑off), ≤ 20‑min; artifacts persisted; Pro report complete.

### Inputs
- Materialized notebook design spec; sandbox executor config.  
- Dataset cache available (worker‑side).

### What to Inspect
- Sandbox launch config: 2 CPU / 6 GB / 25‑min hard cap, **network‑off**.  
- Event protocol adherence (`metric_update`, `sample_pred`, `progress`, `stage_update`, `log_line`).  
- Artifact bundle: notebook, env, logs, metrics, confusion matrix image (if present).

### Run / Observe
1) Run each Top‑3 task; watch SSE; ensure time‑to‑first‑signal ≤ 90s.  
2) Verify metrics and events arrive as per spec; no tool misuse during execution.  
3) Check artifacts in Storage; Pro report renders gaps & citations.

### Expected Evidence
- Sandbox config path and values (no network).  
- SSE stream showing all event types.  
- Artifact manifest listing; download links present.  
- Report screenshot showing gap & citations.

### Pass/Fail
- **Pass**: all three runs finish ≤ 20‑min; artifacts complete; Pro report correct.  
- **Fail**: timeouts, missing artifacts, or protocol deviations.

