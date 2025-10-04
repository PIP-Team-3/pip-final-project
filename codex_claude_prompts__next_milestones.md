
# Codex/Claude Prompts — **Next Milestones** (Runner caps, Report, Kid-Mode)
_Last updated: 2025-10-04_

> Use the Context Hydration prompt from the hotfix file first. Then execute these prompts in order.

---

## N-1) Prompt — **Runner caps & determinism (C-RUN-02)**

**Intent:** Enforce deterministic seeds, CPU-only execution, and artifact caps. Emit typed errors and SSE stages accordingly.

**Files:**
- `api/app/run/runner_local.py`
- `api/app/routers/runs.py`
- `api/app/schemas/events.py` (if present)
- `api/tests/test_runs_stub.py` (unit) and `api/tests/test_runs_sse.py` (integration)

**Tasks:**
- Seeds: set for `random`, `numpy`, and if torch present, `torch` CPU mode only.
- On detecting CUDA/GPU request, abort with `E_GPU_REQUESTED` (guardrail) and SSE `stage_update: guardrail_stop`.
- Cap artifact sizes (e.g., logs 2MB, events 5MB, metrics 64KB). If exceeded, truncate and attach warning in SSE (`event: log_line`, text starts with `[WARN]`).
- Attach `env_hash` to run row; persist `metrics.json`, `events.jsonl`, `logs.txt` under `runs/{run_id}/`.

**Acceptance:**
- Unit test verifies warnings & truncation paths without real kernel.
- Integration test shows `seed_check` stage and CPU enforcement message.

---

## N-2) Prompt — **Pro-Mode Report (C-REP-01)**

**Intent:** Compute reproduction gap versus the paper’s primary claim and return a simple JSON report with artifact links.

**Files:**
- `api/app/routers/reports.py`
- `api/app/services/reports.py`
- `api/tests/test_report.py`

**Tasks:**
- `GET /api/v1/papers/{paper_id}/report -> { claimed, observed, gap_percent, citations, artifacts }`
- Compute `gap = (observed - claimed)/max(|claimed|, epsilon) * 100` for the primary metric (from planner `targets[0]` or first metric).
- Use latest successful run for `observed`; sign URLs to `metrics.json` and `events.jsonl`.
- Persist an `evals` row referencing paper_id and run_id (v0 schema).

**Acceptance:**
- Unit test with fixtures (claimed=75.3, observed=74.1 => gap ~= -1.59%). 
- Manual curl returns JSON and short-TTL artifact URLs.

---

## N-3) Prompt — **Kid-Mode Storybook (C-KID-01)**

**Intent:** Produce a 5–7 page grade-3 storyboard JSON for the paper/run, with alt-text and final scoreboard update post-run.

**Files:**
- `api/app/routers/explain.py`
- `api/app/services/explain_kid.py`
- `api/tests/test_explain_kid.py`

**Tasks:**
- `POST /api/v1/explain/kid -> { storyboard_id, pages:[...], glossary:[...] }`
- Require alt-text; forbid personal images. Final page updated when a run completes (two-bar score: claim vs ours).
- Persist storyboard JSON in Storage + DB, v0 tables only.

**Acceptance:**
- Unit test validates schema (pages 5–7, alt-text present).
- After run completion, final page updates successfully.

---

## N-4) Prompt — **Observability & tracing polish (C-OBS-01)**

**Intent:** Standardize spans: `p2n.ingest.*`, `p2n.extractor.*`, `p2n.planner.*`, `p2n.materialize.*`, `p2n.run.*`. Add `traced_subspan` around tool calls, parse/validate, and storage I/O.

**Files:**
- `api/app/config/llm.py`
- `api/app/utils/redaction.py`
- Any router using tool calls

**Acceptance:**
- Span names consistent; caps/guardrail trips tagged as `policy.cap.exceeded`.
- Unit test asserts the presence of expected span labels in a captured trace log.

---

## N-5) Prompt — **Docs hardening**

**Intent:** Expand README with end-to-end examples (PowerShell), add troubleshooting, and an integration testing section.

**Files:**
- `README.md`
- `docs/PLAYBOOK_MA.md`

**Tasks:**
- Add “Why planner 422?” (missing JSON, missing `created_by`, malformed UUID).
- Add “Why 502 in planner?” (wrong Responses attachments shape; fix by moving to message).
- Add “Runner hangs?” (mock `execute_notebook`; run integration suite separately).

**Acceptance:**
- New contributors can follow the README to green-path the pipeline in under 10 minutes.
