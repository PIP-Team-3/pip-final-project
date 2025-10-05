# Master Prompt Pack for Claude — Post‑Planner Fix (Responses + Agents 0.3.3, SDK 1.109.1)

Paste the **Context Hydration** section at the top of a *fresh chat* with Claude, then run each **Task Card** in order. Each card includes *edits*, *tests*, *acceptance*, and *commit message* guidance.

---

## 0) Context Hydration

**Project:** P2N (Paper‑to‑Notebook Reproducer)  
**Stack:** FastAPI, Responses API, Supabase (DB + Storage), Windows dev, Python 3.12.5.  
**Pinned versions:** `openai==1.109.1`, `openai-agents==0.3.3` (do **not** upgrade yet).  
**Key rule:** In Responses API, use **top‑level** `tools=[{"type":"file_search"}]` and **tool_resources.file_search.vector_store_ids`; use `response_format={"type":"json_object"}`. No message attachments; no `text=<PydanticModel>`.  
**SSE vocabulary:** `stage_update`, `log_line`, final JSON payload.  
**DB posture (v0):** no FKs/RLS; app performs validation.

**Artifacts to consult (download & open locally):**
- `ROADMAP_COMPAT__Responses_Agents_v1091.md`
- `PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md`

---

## TASK A — Fix Planner v1.1 (C‑PLAN‑FIX‑109)

**Goal:** Planner endpoint returns a valid Plan v1.1 using Responses JSON mode and file_search bound to the paper’s vector store.

**Edits (surgical):**
- `api/app/routers/plans.py`
  - Remove `text=PlannerOutput` / `text_format` / `attachments` / inline `vector_store_ids` args to `.stream(...)`.
  - Call shape:
    ```py
    stream = client.responses.stream(
        model=settings.openai_model,
        input=planner_prompt,
        system=[{"text": PLANNER_SYSTEM_PROMPT}],
        tools=[{"type":"file_search","max_num_results":8}],
        tool_resources={"file_search":{"vector_store_ids":[vector_store_id]}},
        response_format={"type":"json_object"},
    )
    ```
  - Accumulate `response.output_text.delta` → `plan_json = json.loads(text)` → validate with `PlanDocumentV11`.
  - Preserve SSE `stage_update`/`log_line` and typed errors.

**Tests to update/run:**
- `api/tests/test_planner.py` (assert top‑level `tools` and presence of `tool_resources.file_search.vector_store_ids`; schema validation remains).
- Entire suite: `..\ .venv\Scripts\python.exe -m pytest -q` (Windows).

**Acceptance:**
- `POST /api/v1/papers/{paper_id}/plan` → 200 with `{plan_id, plan: {...}}` validated.
- No 502; no `Unsupported response_format type` errors.

**Commit message:**
```
planner: fix Responses call for SDK 1.109.1 — json_object format + tool_resources.vector_store_ids; remove typed text/attachments; validate Plan v1.1
```

---

## TASK B — Align Extractor (C‑EXT‑109)

**Goal:** Mirror the same Responses call shape for Extractor.

**Edits:**
- `api/app/routers/papers.py` extractor route → same `tools` / `tool_resources` / `response_format` approach.
- Validate `claims[]`; enforce citations+confidence; maintain SSE.

**Tests:** `api/tests/test_papers_extract.py` assertions for `tools`/`tool_resources` and SSE.

**Commit message:**
```
extractor: Responses json_object + tool_resources.file_search.vector_store_ids; enforce citations/confidence; SSE unchanged
```

---

## TASK C — Guardrails & Caps sanity (no code churn)

- Ensure file_search call cap enforced and correctly labeled (`policy.cap.exceeded`).
- Re-run full tests. Keep redactions intact.

**Commit message:** `guards: verify caps and redaction after Responses call shape change`

---

## TASK D — Manual validation (follow the playbook)

- Start API, ingest, plan, materialize, run, report, kid‑mode. Capture outputs for the PR.

**Commit message:** `docs: add manual validation notes + artifacts links (signed URLs redacted)`

---

## Next prompts (optional, after green build)

- **Confidence propagation (Planner v1.2)** — propagate extractor confidences → plan.confidence with thresholds and warnings.
- **Self-healing runner (retry)** — classify failure → propose patch → retry ≤ N with diff applied.
- **DB v1 migrations (FK/RLS)** — generate SQL only; do not apply.
