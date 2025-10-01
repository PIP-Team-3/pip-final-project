# P2N — Claude 4.5 Review Cards for Prompt Pack (P‑A0 … P‑A18) • v1.0

> Use these **per‑task cards** after Codex completes each Prompt Pack item. Each card has a **Hydration**, **Checks**, **Run**, and **Pass/Fail** section.

---

## P‑A0 • Agents SDK bootstrap & tracing

**Hydration (paste into Claude):**  
You are validating SDK bootstrap. Verify a single config point selects the model, tracing is ON by default with an env override, and no secrets leak to client code.

**Checks:**  
- `/api/app/config/llm.py` exists; model/temperature/tokens/max_turns centralized.  
- Tracing default ON; env var to disable documented.  
- A “hello agent” demo route exists and prints/stores a **trace id**.

**Run:**  
- Call the demo route; capture trace id; ensure a valid trace is created.

**Pass/Fail:**  
- Pass if trace visible and config is centralized; fail if tracing missing or secrets exposed.

---

## P‑A1 • Function tools registry

**Hydration:**  
Ensure core function tools exist with schemas and allow‑lists; invalid args raise typed errors.

**Checks:**  
- `dataset_resolver`, `license_checker`, `budget_estimator`, `env_lock_builder`, `sandbox_submit (stub)`, `gap_calculator`.  
- Tool registration limited to appropriate agents.

**Run:**  
- Invoke each tool through an agent; pass an invalid argument once to confirm validation.

**Pass/Fail:**  
- Pass if tools work and errors are typed; fail on silent coercion or missing allow‑lists.

---

## P‑A2 • Hosted tools enablement (File Search, Web Search, Code Interpreter preflight)

**Hydration:**  
Validate hosted tool registration and **per‑run caps**; confirm Code Interpreter is restricted to EnvSpec preflight.

**Checks:**  
- File Search enabled for Extractor/Planner; Web Search for Planner; Interpreter for EnvSpec only.  
- Caps: FS≤10, WS≤5, CI≤60s with server‑side enforcement.

**Run:**  
- Run Extract/Plan; ensure tool calls appear in traces; attempt to exceed caps → policy error with remediation.

**Pass/Fail:**  
- Pass if caps enforced and traces show correct tools; fail if tools are globally enabled or uncapped.

---

## P‑A3 • Agents with structured outputs + guardrails

**Hydration:**  
Validate each agent has typed outputs and **output guardrails** with tripwires; Planner checks schema/license/budget.

**Checks:**  
- Extractor/Planner/EnvSpec/CodeGenDesign/Kid‑Explainer outputs defined; guardrails wired.  
- Tripwires raise typed errors and halt orchestration.

**Run:**  
- Force a Plan schema miss and a license block; confirm tripwires and remediation messaging.

**Pass/Fail:**  
- Pass if violations stop execution and surface remediation; fail if plan proceeds.

---

## P‑A4 • Orchestrator state machine

**Hydration:**  
Check deterministic transitions; bounded retries; content‑hash caching; typed errors.

**Checks:**  
- States: INGESTED→EXTRACTED→PLANNED→MATERIALIZED→RUNNING→COMPLETED/FAILED.  
- Invalid transitions rejected; cache hits logged.

**Run:**  
- Execute same paper twice; confirm cache path; try “run before plan” (should reject).

**Pass/Fail:**  
- Pass if deterministic and cache works; fail on loops or side‑effects.

---

## P‑A5 • Streaming bridge (SDK → SSE)

**Hydration:**  
Verify mapping from token + run‑item events to SSE payloads.

**Checks:**  
- Outbound SSE events: `progress`, `stage_update`, `log_line` (plus later metric/sample).  
- Backpressure and connection close handled.

**Run:**  
- Trigger Extract/Plan; collect SSE transcript.

**Pass/Fail:**  
- Pass if transcripts show mapped events; fail if empty/partial.

---

## P‑A6 • Tracing surface (admin)

**Hydration:**  
Ensure admin list shows runs with **trace links** and tool call counters.

**Checks:**  
- Per‑run trace link/ID; daily counters; remaining budget.

**Run:**  
- Open admin; verify counters increment after runs.

**Pass/Fail:**  
- Pass if links/counters work; fail if missing.

---

## P‑A7 • Handoffs (optional triage → human review)

**Hydration:**  
If implemented, verify handoffs are **tools**; no infinite loops.

**Checks:**  
- `transfer_to_human_review` and back to Planner; max handoffs per run defined.

**Run:**  
- Force low confidence in Extractor; observe handoff event in trace.

**Pass/Fail:**  
- Pass if handoff bounded and visible; fail if loops or hidden.

---

## P‑A8 • Ingest pipeline → Storage + File Search

**Hydration:**  
Confirm upload stores to Storage and indexes in File Search; persist `vector_store_id`.

**Checks:**  
- `/api/v1/papers/ingest` returns `{paper_id, vector_store_id}`; DB row has Storage path + hash.

**Run:**  
- Upload 2 PDFs; verify both sides (Storage object + vector store id).

**Pass/Fail:**  
- Pass if both stored; fail if only one side or missing ids.

---

## P‑A9 • Planner policies & budgets

**Hydration:**  
Planner must not exceed 20‑min budget or blocked licenses; show fidelity warnings on downscales.

**Checks:**  
- Guardrails enforce budget/license; justifications map contains paper quotes.

**Run:**  
- Inflate epochs to exceed budget; verify downscale or tripwire.  
- Choose blocked license; expect immediate stop.

**Pass/Fail:**  
- Pass if enforced; fail if plan ignores policy.

---

## P‑A10 • Admin caps (per‑day)

**Hydration:**  
Daily caps must block politely when exceeded.

**Checks:**  
- Config for per‑day caps; admin shows remaining.

**Run:**  
- Simulate reaching cap; attempt another run.

**Pass/Fail:**  
- Pass if blocked with friendly message; fail if unbounded.

---

## P‑A11 • Seed tests (no training)

**Hydration:**  
Smoke script validates M‑A flow for two seed papers.

**Checks:**  
- Script prints trace URLs and SSE transcript summary; fails on missing guardrails/outputs.

**Run:**  
- Execute script end‑to‑end.

**Pass/Fail:**  
- Pass if both papers succeed; fail otherwise.

---

## P‑A12 • SQL DDL + RLS + seed data

**Hydration:**  
Schema and RLS must match AGENTS.md; seeds load without errors.

**Checks:**  
- UUID/BIGINT keys; cascades; indexes; RLS owner policies and join‑based run_* reads.

**Run:**  
- Apply schema, RLS, seed; query counts; test RLS denies unauthorized reads.

**Pass/Fail:**  
- Pass if schema valid and RLS enforced; fail if leaks or errors.

---

## P‑A13 • Demo Web UI (read‑only)

**Hydration:**  
UI should display streaming, claim cards (with citations), plan JSON, storyboard.

**Checks:**  
- Accessibility basics; alt‑text present; motion‑reduced toggle.

**Run:**  
- Perform M‑A flow in UI.

**Pass/Fail:**  
- Pass if views render and stream; fail if broken.

---

## P‑A14 • Tracing polish + labels

**Hydration:**  
Traces should include workflow labels (e.g., “P2N: Planner”).

**Checks:**  
- Labeling consistent; guardrail violations labeled by rule id.

**Run:**  
- Execute plan with induced violation; inspect trace labels.

**Pass/Fail:**  
- Pass if labeled; fail if generic.

---

## P‑A15 • Evaluate‑only endpoint (M‑B)

**Hydration:**  
Validate eval‑only metrics generation and artifacts.

**Checks:**  
- Endpoint exists; writes `metrics.json`; updates Storybook final page.

**Run:**  
- Run eval‑only; verify gap computed.

**Pass/Fail:**  
- Pass if metrics/gap present; fail otherwise.

---

## P‑A16 • Full run executor (M‑C)

**Hydration:**  
Sandbox must be network‑off, CPU‑only, with event protocol adherence.

**Checks:**  
- Config matches policy; artifacts complete.

**Run:**  
- Execute Top‑3; confirm time budgets and events.

**Pass/Fail:**  
- Pass if all runs succeed; fail on timeouts/protocol breaks.

---

## P‑A17 • Admin/Usage dashboards

**Hydration:**  
Dashboards show tool usage, budgets, last failures, and trace links.

**Checks:**  
- Accurate counters; clear errors; exportable logs.

**Run:**  
- Trigger runs and violations; verify dashboard updates.

**Pass/Fail:**  
- Pass if accurate; fail if stale/wrong.

---

## P‑A18 • End‑to‑end smoke (CI)

**Hydration:**  
CI should run smoke for M‑A and at least one M‑B path.

**Checks:**  
- Workflow defined; fails on guardrail regressions; prints trace links in logs.

**Run:**  
- Trigger CI manually if needed.

**Pass/Fail:**  
- Pass if CI green with expected artifacts; fail otherwise.

