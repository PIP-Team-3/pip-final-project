# Roadmap — Claude Drift Recovery & E2E Guardrails
**Owner:** P2N Team  
**Goal:** Eliminate extractor/planner drift; keep SDK 1.109.1 semantics green end‑to‑end

---

## Milestone M0 — Lock the Invariants (Today)
**Objective:** Make drift impossible to miss.

- [ ] Add **payload linter tests** (unit):  
  - No `attachments` in Responses API input  
  - Has `response_format.json_schema.strict==true`  
  - `tools` includes `file_search` with `vector_store_ids`  
  - No `text_format` key anywhere
- [ ] Add **extractor E2E test**: sample 3‑page PDF → SSE `result` parses as `ExtractorOutput` with ≥1 claim
- [ ] Add **planner E2E test**: sample claims → Plan v1.1 JSON validates; `estimated_runtime ≤ budget`
- [ ] Add **DB enum test**: rejects `papers.status='ingested'`, accepts `'ready'|'processing'|'failed'`
- [ ] Add **storage MIME test**: upload bytes with `application/pdf` passes

**Definition of Done:** CI fails loudly if any invariant is violated.

---

## Milestone M1 — Batch Validation (20 Papers)
**Objective:** Prove scale and diversity (CV/NLP/Tabular/GNN/Optimization).

- [ ] Place PDFs under `uploads/`
- [ ] Ingest all 20 (idempotent; skip duplicates)
- [ ] For first 5 papers: run **extract → plan → materialize** (stop before real run)
- [ ] Verify: ≥1 claim each; Plan v1.1 passes; `env_hash` set after materialize
- [ ] Generate reports (stubbed runs allowed) to validate signed URL flow

**DoD:** 20 ingested, 5 materialized, all validations passing.

---

## Milestone M2 — Real Execution Prep (C‑RUN‑01 Design)
**Objective:** Replace stub with container worker spec + acceptance tests drafted.

- [ ] Worker API: `POST /runs.dispatch`, SSE log stream, timeout enforcement
- [ ] Container spec: 2 vCPU / 4 GB RAM / CPU‑only; pip wheels cache
- [ ] Artifact schema: `metrics.json`, `events.jsonl`, `logs.txt`, `output.ipynb`
- [ ] Acceptance test plan: 3 plans execute under budget; status transitions correct

**DoD:** Written design + checklists merged; smoke runner script ready.

---

## Milestone M3 — Observability & Drift Watchdogs
**Objective:** Make regressions visible in minutes.

- [ ] Trace spans: `extractor.run`, `planner.run`, `materialize.codegen` with payload fingerprints (no PII)
- [ ] Nightly **drift canary**: run 1 known‑good PDF; alert if schema result missing
- [ ] Log scrapers: count OpenAI 400/422 with param name histograms
- [ ] Slack hook (optional): post “green bar” summary nightly

**DoD:** Canary green 3 nights in a row; payload linter never red.

---

## Milestone M4 — Determinism Pass (C‑RUN‑02)
**Objective:** Prove seeds + env make runs repeatable.

- [ ] Execute same plan thrice; assert identical `metrics.json`  
- [ ] Check NB output cells stable (tolerate timestamps)  
- [ ] Document determinism levers (random, numpy, torch)

**DoD:** 3/3 identical metrics for at least one plan.

---

## Risks / Mitigations
- **SDK drift**: pin 1.109.1; add version assertion test.  
- **ArXiv redirects**: httpx `follow_redirects=True`; curl `-L`.  
- **Supabase MIME**: use `content-type` header key (not camelCase).  
- **Enum mismatches**: centralize constants in tests and code.