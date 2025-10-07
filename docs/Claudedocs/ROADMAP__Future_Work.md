# P2N Project - Future Roadmap
**Last Updated:** 2025-10-07
**Current Phase:** 🎉 Extraction pipeline operational - Ready for integration & expansion

---

## 🎯 Immediate Next Steps (High Priority)

### **1. Complete Extraction Integration**
**Status:** Claims extracted but not saved to database yet
**Why:** Guardrail currently trips on empty arrays, but extraction now returns valid claims

**Tasks:**
- [ ] Test extraction on ResNet paper (`f568a896-673c-452b-ba08-cc157cc8e648`)
- [ ] Verify claims save to `claims` table correctly
- [ ] Test guardrail with actual low-confidence claims
- [ ] Add claim count to extraction success response
- [ ] Update tests to verify database persistence

**Expected Outcome:** Claims auto-saved to database after successful extraction

---

### **2. End-to-End Pipeline Testing**
**Status:** Individual stages work, need full integration test

**Tasks:**
- [ ] Ingest → Extract → Plan → Materialize → Run (stub) flow
- [ ] Test with 3-5 different papers (varying complexity)
- [ ] Verify all artifacts persist correctly
- [ ] Document manual testing playbook
- [ ] Create automated integration test

**Papers to Test:**
1. ✅ TextCNN (1408.5882) - Extraction verified
2. ResNet (1512.03385) - In database, ready to test
3. BERT - Large tables, complex claims
4. Transformer (Attention is All You Need) - Multi-dataset
5. Simple paper - Edge case (few/no quantitative claims)

**Expected Outcome:** Reproducible end-to-end workflow from PDF → executable notebook

---

### **3. Improve Extraction Quality**
**Status:** Working but can be enhanced

**Tasks:**
- [ ] Add split detection (train/val/test) - currently null
- [ ] Improve citation granularity (page numbers, section IDs)
- [ ] Handle multi-row table claims (same metric, different configs)
- [ ] Add confidence calibration (vary by source type)
- [ ] Test with papers that have no quantitative claims (ensure graceful `{"claims": []}`)

**Expected Outcome:** Higher-quality claims with better metadata

---

## 🚀 Near-Term Features (Next 2-4 Weeks)

### **4. Real Sandbox Executor (C-RUN-01)**
**Status:** Currently using stub with simulated output
**Why Critical:** Core value proposition is reproducible execution

**Requirements:**
- Isolated execution environment (Docker or serverless)
- Deterministic RNG seeding
- CPU-only enforcement (no GPU/network)
- Timeout enforcement (20 min max)
- Artifact capture (metrics.json, logs, plots)
- SSE streaming of live output

**Implementation Options:**
A. **Docker-based local executor**
   - Pros: Full control, easy debugging
   - Cons: Requires Docker setup, resource limits

B. **Modal/Fly.io serverless**
   - Pros: Auto-scaling, pay-per-use
   - Cons: Cold starts, complexity

C. **E2B sandboxes**
   - Pros: Purpose-built for code execution
   - Cons: Cost, third-party dependency

**Recommended:** Start with Docker (A), migrate to Modal (B) for production

**Tasks:**
- [ ] Design sandbox API contract
- [ ] Implement Docker-based executor
- [ ] Add artifact collection logic
- [ ] Stream real notebook output via SSE
- [ ] Test with materialized notebooks
- [ ] Replace stub routes with real executor

---

### **5. Gap Analysis & Reporting (C-REPORT-01)**
**Status:** Database schema ready (`evals` table), logic not implemented

**Purpose:** Quantify reproduction success

**Metrics to Calculate:**
- Absolute gap: `|reproduced_value - paper_value|`
- Relative gap: `gap / paper_value`
- Pass/fail: `gap < tolerance_threshold`
- Aggregate stats: mean/median gap across all claims

**Tasks:**
- [ ] Implement gap calculation service
- [ ] Add gap tolerance policies (per-metric, per-dataset)
- [ ] Create report generation endpoint
- [ ] Store `evals` records in database
- [ ] Design report visualization (for web UI)

**Expected Output:**
```json
{
  "paper_id": "...",
  "run_id": "...",
  "overall_pass": true,
  "claims_evaluated": 28,
  "claims_passed": 26,
  "mean_relative_gap": 0.023,
  "gaps": [
    {"claim_id": "...", "paper_value": 88.1, "reproduced_value": 87.8, "gap": 0.3, "passed": true}
  ]
}
```

---

### **6. Kid-Mode Storybook Integration (C-KID-01)**
**Status:** Agent definition ready, generation logic implemented, needs integration

**Tasks:**
- [ ] Trigger storybook generation after run completion
- [ ] Store storyboard JSON in `storyboards` table
- [ ] Add image generation placeholders (DALL-E or stable diffusion)
- [ ] Create storybook viewer endpoint
- [ ] Test with completed run metrics

**Expected Outcome:** Automated kid-friendly explanation generated for each run

---

## 📊 Medium-Term Improvements (1-2 Months)

### **7. Multi-Tenancy & Security**
**Status:** RLS disabled for MVP, schema supports `created_by` fields

**Tasks:**
- [ ] Enable RLS policies on all tables
- [ ] Implement user authentication (Supabase Auth)
- [ ] Add `created_by` enforcement in application layer
- [ ] Test isolation between users
- [ ] Add admin role for cross-user access

---

### **8. Web UI (Basic MVP)**
**Status:** Placeholder React app exists, not functional

**Core Flows:**
1. Upload paper → Show ingestion progress
2. View paper details → Trigger extraction
3. Review claims → Edit/approve
4. Generate plan → Review JSON
5. Run notebook → Watch SSE stream
6. View results → Gap report + storybook

**Technology:**
- React + TypeScript
- Supabase client for auth/data
- EventSource for SSE streaming
- Tailwind for styling

**Tasks:**
- [ ] Design wireframes
- [ ] Implement paper upload flow
- [ ] Build SSE viewer component
- [ ] Create claim editor
- [ ] Add plan visualization
- [ ] Deploy to Vercel/Netlify

---

### **9. Planner Enhancements**
**Status:** Working but can be smarter

**Improvements:**
- [ ] Auto-detect dataset availability (HuggingFace, TensorFlow Datasets)
- [ ] Model architecture search (suggest similar models if original unavailable)
- [ ] Dependency resolution (auto-generate requirements.txt from plan)
- [ ] Cost estimation (compute time, dataset size)
- [ ] Feasibility scoring (0-1 likelihood of success)

---

### **10. Observability & Monitoring**
**Status:** Basic tracing exists, needs expansion

**Tasks:**
- [ ] Add Sentry for error tracking
- [ ] Create dashboard for run success rates
- [ ] Monitor File Search usage (cost tracking)
- [ ] Alert on failed extractions/runs
- [ ] Add performance metrics (extraction time, run duration)

---

## 🔮 Long-Term Vision (3-6 Months)

### **11. Multi-Paper Reproduction**
Compare reproduction quality across papers:
- Leaderboard of most reproducible papers
- Identify common failure patterns
- Build dataset of reproduction results

### **12. Citation Network Analysis**
- Extract paper citations from PDFs
- Build dependency graph (Paper A cites Paper B)
- Reproduce entire citation chains
- Quantify reproducibility debt

### **13. Automated Paper Discovery**
- Scrape arXiv for new papers
- Auto-ingest papers with code availability
- Pre-extract claims for quick browsing
- Alert on papers in specific domains

### **14. Collaborative Features**
- Share plans/notebooks between users
- Community-contributed plan improvements
- Upvote/downvote plan quality
- Discussion threads on reproduction attempts

### **15. Advanced Execution**
- GPU support (optional, with cost controls)
- Distributed execution (multi-node training)
- Checkpointing for long runs
- Resume from failure

---

## 📋 Technical Debt & Cleanup

### **Code Quality**
- [ ] Add type hints to all functions (currently ~70% coverage)
- [ ] Increase test coverage from 60% → 85%
- [ ] Refactor large router functions (papers.py `run_extractor` is 200+ lines)
- [ ] Add docstrings to all public APIs
- [ ] Create architecture decision records (ADRs)

### **Documentation**
- [ ] API reference documentation (OpenAPI/Swagger)
- [ ] Developer onboarding guide
- [ ] Deployment guide (production setup)
- [ ] Troubleshooting playbook
- [ ] Video walkthrough

### **Infrastructure**
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Automated database migrations
- [ ] Staging environment
- [ ] Load testing (handle 100+ concurrent extractions)
- [ ] Backup/restore procedures

---

## 🎓 Research Questions

### **Extraction Quality**
- Can we use multi-modal models to extract from figure captions?
- How to handle claims in supplementary materials?
- Can we validate extracted claims against paper text (fact-checking)?

### **Plan Generation**
- How to handle papers with custom/unavailable datasets?
- Can we auto-generate data preprocessing code?
- How to balance reproduction fidelity vs. cost?

### **Reproducibility Science**
- What % of papers can be reproduced within 20 min CPU?
- Which domains have highest/lowest reproducibility?
- Are newer papers more reproducible (better code practices)?

---

## 🛠️ Proposed Prompt Codex (Future Sessions)

### **C-RUN-01: Real Sandbox Executor**
**Goal:** Replace stub with Docker-based sandbox
**Prerequisites:** Materialized notebooks exist and pass manual tests
**Deliverables:**
- Docker executor service
- Real SSE streaming from notebook execution
- Artifact persistence (metrics.json, logs, plots)

### **C-RUN-02: Determinism Enforcement**
**Goal:** Ensure 100% reproducible runs
**Tasks:**
- Force CPU-only execution
- Validate RNG seeding in notebooks
- Hash notebook environment for bit-for-bit reproduction
- Add determinism audit to evals

### **C-REPORT-01: Gap Analysis**
**Goal:** Automated gap calculation and reporting
**Tasks:**
- Implement gap metrics service
- Store evals in database
- Generate PDF/HTML reports
- Add gap visualization

### **C-KID-01: Storybook Integration**
**Goal:** Auto-generate kid-friendly explanations
**Tasks:**
- Trigger generation post-run
- Add image placeholders
- Create viewer UI
- Test with real run data

### **C-WEB-01: React UI MVP**
**Goal:** Basic web interface for core flows
**Tasks:**
- Paper upload + extraction viewer
- Claim editor
- Plan reviewer
- Run watcher (SSE)
- Results dashboard

### **C-AUTH-01: Multi-Tenancy**
**Goal:** Enable RLS and user auth
**Tasks:**
- Supabase Auth integration
- RLS policy deployment
- User isolation testing
- Admin panel

---

## 📈 Success Criteria (Next Milestone)

**Milestone: Production-Ready Extraction (2 weeks)**
- [ ] Extract claims from 10+ papers successfully
- [ ] 95%+ accuracy on claim values (manual audit)
- [ ] <30s average extraction time
- [ ] Zero database persistence errors
- [ ] All claims have citations with >0.5 confidence

**Milestone: End-to-End MVP (1 month)**
- [ ] Ingest → Extract → Plan → Run → Report flow works
- [ ] 80%+ plans successfully materialize to notebooks
- [ ] Sandbox executor handles at least simple notebooks
- [ ] Gap analysis generates accurate reports
- [ ] Storybooks created for all successful runs

**Milestone: Public Beta (3 months)**
- [ ] Web UI allows full workflow
- [ ] Multi-user support with RLS
- [ ] 100+ papers ingested
- [ ] Community can submit papers
- [ ] Leaderboard of reproducible papers

---

## 🏆 North Star Metrics

**Adoption:**
- Papers ingested per week
- Active users
- Community-contributed plans

**Quality:**
- % papers with successful runs
- Average gap (lower is better)
- Claim extraction accuracy

**Impact:**
- Papers marked as "reproducible" by community
- Citations to P2N in academic papers
- Datasets/models made available due to P2N

---

**For current system status, see:** [CURRENT_STATUS__2025-10-07.md](CURRENT_STATUS__2025-10-07.md)
