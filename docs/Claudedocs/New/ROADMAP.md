# P2N Roadmap
**Updated:** 2025-10-05

## Milestone Map (next 6 weeks)

### 1) C‑RUN‑01 — Real Sandbox Execution (Week 1–2)
**Goal:** Replace run stub with containerized notebook execution (CPU‑only).
**Deliverables**
- Worker service (`worker/`) that:
  - Pulls plan artifacts (notebook + requirements) from Storage
  - Creates container (Docker) with resource caps (2 vCPU, 4 GB RAM)
  - Installs requirements; executes notebook; enforces timeout = `policy.budget_minutes`
  - Streams stdout/stderr lines as SSE events
  - Uploads `metrics.json`, `events.jsonl`, `logs.txt` back to Storage
- API changes:
  - `POST /api/v1/plans/{plan_id}/run` -> dispatches job to worker
  - `GET /api/v1/runs/{run_id}/events` -> proxies worker stream

**Acceptance criteria**
- Run completes under budget on 3 sample plans (≤ 20 min)
- SSE shows **real** progress lines, not stubbed
- Artifacts present + signed URLs resolve
- `runs.status` transitions: `queued → running → (succeeded|failed|timeout)`

**Owner:** Backend (worker) | Infra (Docker)  
**Risks:** Dependency install slowness → Mitigate with wheels cache & slim reqs

---

### 2) C‑RUN‑02 — Determinism Validation (Week 3)
**Goal:** Same seed ⇒ same outputs (3/3 runs identical).
**Deliverables**
- Determinism test harness (`api/tests/test_determinism.py`)
- Endpoint `POST /api/v1/runs/{run_id}/validate_determinism` (optional)
- Docs describing where determinism can break (e.g., torch.backends.cudnn, non‑seeded ops)

**Acceptance criteria**
- Metric JSON **byte‑identical** for 3 runs of the same plan
- Failures produce typed `error_code` with actionable text

**Owner:** Backend  
**Risks:** Library nondeterminism → Mitigate with controlled seeds & CPU ops only

---

### 3) C‑EXT‑02 — Extractor SDK Cleanup (Week 3–4)
**Goal:** Mirror the planner’s SDK 1.109.1 fixes in extractor.
**Deliverables**
- Remove `text_format`, `response_format`, `tool_resources`
- Ensure `vector_store_ids` placed inside file_search tool
- Add robust JSON parsing & schema checks

**Acceptance criteria**
- 3 real papers produce >= 1 valid claim each
- No 5xx from extractor due to malformed tool payloads

**Owner:** Agents  
**Risks:** Paper OCR noise → Mitigate with small rule‑based cleanups

---

### 4) C‑OBS‑02 — Worker Observability (Week 4)
**Goal:** Production‑grade traces & logs for runs.
**Deliverables**
- Structured logs with run_id, plan_id, paper_id
- Traces: `p2n.worker.prepare`, `p2n.worker.exec`, `p2n.worker.upload`
- Log redaction for signed URLs and IDs

**Acceptance criteria**
- Logs visible locally + redact secrets
- Trace spans stitched across API → Worker → Storage

**Owner:** Infra

---

### 5) C‑WEB‑01 — Thin React UI (Week 5–6)
**Goal:** First minimal UI for end‑to‑end flows.
**Deliverables**
- Upload PDF, watch SSE, view plan JSON, list artifacts, view report, read storyboard
- Use signed URLs; no secrets in the browser

**Acceptance criteria**
- 5 user flows pass in manual testing playbook
- No CORS or auth issues (single tenant)

**Owner:** Web

---

## Hard Gates & Checklists

**Before shipping C‑RUN‑01**
- [ ] Worker cancels >60s over budget
- [ ] `runs.env_hash` required; prevent run start otherwise
- [ ] Storage cleanup uses `from_(bucket).remove([path])`
- [ ] Plan JSON validated against v1.1 schema

**Before enabling public demos**
- [ ] Rate limit: 5 ingests / hour
- [ ] Storage quotas: per‑run artifacts < 25MB
- [ ] Backpressure: reject run if queue > N

---

## Model/Cost Optimizations (optional, low risk)
- Extractor: `gpt-4o-mini`
- Planner: `o1-mini`
- Kid‑Mode: `gpt-4o`

Expected: 90% lower extraction cost; similar/better plan quality.

---

## Risks & Mitigations
- **Dependency hell in containers** → Pre‑cache wheels, pin versions, small base image
- **PostgREST schema drift** → Run `NOTIFY pgrst, 'reload schema';` via admin tool if needed
- **Vector store ID invalid** → Validate at ingest; fail fast with typed error
