# MASTER PROMPTS — vNext after C‑KID‑01 & C‑OBS‑01
_Last updated: 2025-10-04_

## 0) Context Hydration (paste at the top of a **fresh** Codex/Claude chat)

**Project:** P2N (Paper‑to‑Notebook Reproducer)  
**State:** Ingest → Extractor (SSE) → Planner v1.1 → Materialize → Run (deterministic, CPU‑only, caps) → Report → Kid‑Mode; Doctor shows runner posture & last_run.  
**Versions:** Python 3.12.5; `openai==1.109.1`, `openai-agents==0.3.3`.  
**DB posture:** **Schema v0** (no FKs/RLS/CHECK/UNIQUE/defaults). App supplies all IDs/values.  
**Responses API guardrails:** declare `{"type":"file_search","max_num_results": N}` at **top‑level** `tools`; message‐level `attachments`: `[{"type":"file_search"}]`. No `attachments=` on `responses.stream()` params.  
**Redaction:** Never leak keys; redact signed URL tokens.  
**Runner:** deterministic seeds (random/numpy/torch), CPU‑only, artifact caps (logs 2 MiB; events 5 MiB), typed errors.

**What to return in each PR:** file paths changed, diff bullets, tests (happy + negative), manual steps, **no schema changes** (v0).

---

## 1) C‑CACHE‑01 — Dataset & Env Caching

**Intent:** Reduce cold‑start times by caching datasets / env layers and surfacing cache metrics.

**Deliverables**
- `api/app/cache/registry.py`: simple LRU with size/age policy (env and dataset namespaces).
- Runner: cache probe & record hit/miss in `run_series` (v0 row) and emit `stage_update: cache_probe`.
- Doctor: cache section `{ hits, misses, size_mib, entries }`.

**Tests**
- Unit: cache insert/evict; TTL/size policy.
- Runner stub: emits `cache_probe`, records hit/miss.
- Doctor: shows cache stats; redaction intact.

**Acceptance**
- Cache improves local repeated runs (manual observation).
- Stats visible via doctor; no schema migrations.

---

## 2) C‑RETRY‑01 — Resume & Retry

**Intent:** Resume a run from last safe boundary (cell) or provide idempotent retry.

**Deliverables**
- Runner: resume token persisted to Storage `runs/{run_id}/resume.json`.
- SSE: `stage_update: resume_check`.
- API: `POST /api/v1/runs/{run_id}/retry` → new run tied to same plan; links to previous run.

**Tests**
- Happy path: retry creates new run and references prior artifacts.
- Negative: resume requested but no token → typed error `E_RESUME_TOKEN_MISSING`.

**Acceptance**
- Manual retry works; SSE shows `resume_check` then normal flow.

---

## 3) C‑UI‑01 — Minimal UI (static)

**Intent:** Provide a zero‑build static UI to kick the tires.

**Deliverables**
- `web/index.html` (no framework): form to ingest, plan, materialize, run; live SSE viewer; storybook viewer.
- `web/sse.js`: SSE helper (reconnect, backoff, append).

**Tests**
- `pytest` static file smoke (200 OK) via test client; not an E2E browser test.

**Acceptance**
- Open `web/index.html`; can trigger endpoints and see live events and artifacts links.

---

## 4) C‑LEADERBOARD‑01 — Paper Cards & Runs Leaderboard

**Intent:** Summarize runs per paper with metric direction and artifacts.

**Deliverables**
- `GET /api/v1/papers/{paper_id}/runs` → list with `{ run_id, status, observed_metric, completed_at }`.
- `GET /api/v1/leaderboard` → top N by metric (respect direction).

**Tests**
- Sorting by maximize/minimize; ties; missing metrics handled.

**Acceptance**
- Simple JSON output; short‑TTL signed URLs for artifacts; redaction maintained.

---

## 5) C‑DEPLOY‑01 — Containerized Local Deploy

**Intent:** One‑command local compose deploy, prod‑like.

**Deliverables**
- `docker-compose.yml` for API + worker.
- Healthchecks; `.env.example`; README deploy steps.

**Tests**
- Lint docker compose; ping health endpoint in CI (without secrets).

**Acceptance**
- `docker compose up` serves API; trivial smoke succeeds.

---

## 6) C‑RLS‑PREP‑01 — Prepare (but do not apply) DB Migrations

**Intent:** Stage SQL files for v1 hardening without changing live DB.

**Deliverables**
- `db/migrations/preview/*.sql`: FKs, RLS policies, CHECK/UNIQUE, defaults, indexes, (optional) pgvector.
- CI job: **parse‑only** (sqlfluff or psql `-f` explain stub).

**Tests**
- Parse‑only success; lints pass.

**Acceptance**
- SQL compiles; not applied. Document cutover plan and backout.

---

## Constraints & Notes (global)

- **No schema changes now** (v0); everything simulated via app logic.
- **Redaction**: never log raw tokens or signed URL query strings.
- **Pin OpenAI deps** until we explicitly migrate off Agents SDK 0.3.3.
- **Traces**: use `p2n.*` spans for all new work (cache, retry, ui, leaderboard, deploy).
