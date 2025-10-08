# Session Rehydration: Phase 1 Complete - Real Notebook Generation Refactor + Critical Fixes

**Date:** 2025-10-08
**Session Focus:** Phase 1 Notebook Generator Refactor + Claims DB Persistence + o3-mini Fix
**Status:** ⚠️ **PHASE 1 CODE COMPLETE - VERIFICATION PENDING**
**Commits:** `6fcae9d`, `9a94207`

---

## ⚠️ CRITICAL: CLAIMS DATABASE SAVE NOT YET VERIFIED!

**The code to save claims was written and committed, but we ran out of time to verify it actually works.**

**What we did:**
- ✅ Added ClaimCreate/ClaimRecord models
- ✅ Added insert_claims() database method
- ✅ Updated extractor to call db.insert_claims()
- ✅ Added GET /api/v1/papers/{paper_id}/claims endpoint
- ✅ Committed and pushed all code

**What we did NOT do:**
- ❌ Restart server with new code
- ❌ Verify claims actually saved to database
- ❌ Test GET /api/v1/papers/{paper_id}/claims endpoint
- ❌ Confirm database has 28 claims

**MUST DO NEXT SESSION FIRST:**
```bash
# 1. Restart server
# 2. Test GET endpoint:
curl.exe "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims"
# Expected: 28 claims OR error if claims weren't saved during extraction

# 3. If no claims returned, run extraction again:
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract"
# Then check claims again
```

**Do NOT proceed to Phase 2 until claims DB save is verified!**

---

## 🎯 Session Objectives (Code Complete, Not Verified)

1. ✅ **Implement Phase 1 of Real Notebook Generation (C-NOTEBOOK-01)**
   - Refactor notebook generator to modular architecture
   - Zero behavior change (still generates synthetic + logistic)
   - Foundation for Phases 2-4
   - **VERIFIED:** All 27 tests pass

2. ⚠️ **Fix Critical Blocker: Claims Not Saving to Database (Roadmap #1)**
   - Claims were extracted but never persisted
   - Added database models and insert methods
   - Updated extractor to save after validation
   - **NOT VERIFIED:** Code written but not tested with live database

3. ⚠️ **Fix Critical Blocker: o3-mini + web_search Incompatibility**
   - Planner failed: "web_search_preview not supported with o3-mini"
   - Filter out web_search tool for o3-mini models
   - Planner now works with o3-mini
   - **NOT VERIFIED:** Code written but not tested with live planner

---

## 📦 What Was Delivered

### 1. Phase 1: Modular Notebook Generator Architecture ✅

**Files Created:**
- `api/app/materialize/generators/__init__.py` - Package exports
- `api/app/materialize/generators/base.py` - CodeGenerator ABC (interface)
- `api/app/materialize/generators/dataset.py` - SyntheticDatasetGenerator
- `api/app/materialize/generators/model.py` - SklearnLogisticGenerator
- `api/app/materialize/generators/factory.py` - GeneratorFactory (selection logic)
- `api/tests/test_generators.py` - 24 comprehensive unit tests

**Files Modified:**
- `api/app/materialize/notebook.py` - Now uses GeneratorFactory pattern

**Architecture:**
```
api/app/materialize/
├── notebook.py (orchestrator)
└── generators/
    ├── __init__.py
    ├── base.py           # CodeGenerator ABC
    ├── dataset.py        # SyntheticDatasetGenerator (Phase 1)
    ├── model.py          # SklearnLogisticGenerator (Phase 1)
    └── factory.py        # Always returns synthetic + logistic (Phase 1)
```

**Key Design Patterns:**
- **Abstract Base Class:** `CodeGenerator` defines interface for all generators
- **Factory Pattern:** `GeneratorFactory` selects appropriate generators
- **Phase 1 Behavior:** Factory always returns synthetic + logistic (no change from before)
- **Extensibility:** Ready for Phases 2-4 to add real dataset/model generators

**Testing:**
- ✅ 24/24 new generator unit tests pass
- ✅ 3/3 existing materialize integration tests pass (no regression)
- ✅ Regression tests verify notebook structure unchanged
- ✅ Generated code compiles successfully

### 2. Claims Database Persistence ✅

**Problem:** Extractor extracted claims correctly but NEVER saved them to database. Claims only returned via SSE, then lost.

**Files Modified:**
- `api/app/data/models.py` - Added `ClaimCreate` and `ClaimRecord` models
- `api/app/data/supabase.py` - Added `insert_claims()` and `get_claims_by_paper()` methods
- `api/app/data/__init__.py` - Export new claim models
- `api/app/routers/papers.py` - Save claims after extraction + validation

**Schema Mapping:**
```python
# Database: claims table (schema_v1_nuclear.sql line 75-95)
CREATE TABLE claims (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    dataset_name text,
    split text,
    metric_name text NOT NULL,
    metric_value numeric NOT NULL,
    units text,
    method_snippet text,
    source_citation text NOT NULL,
    confidence numeric NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT NOW()
);
```

**Flow:**
1. Extractor extracts claims from paper (OpenAI Responses API)
2. Claims validated with Pydantic (`ExtractorOutputModel`)
3. Claims converted to `ClaimCreate` objects
4. Bulk inserted via `db.insert_claims(claim_records)`
5. Returns `ClaimRecord` objects with generated UUIDs
6. Extraction continues even if DB save fails (logs warning)

**New Endpoint:**
```
GET /api/v1/papers/{paper_id}/claims
```
Returns all claims for a paper with full details.

### 3. o3-mini Web Search Fix ✅

**Problem:** Planner failed with error:
```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Hosted tool 'web_search_preview' is not supported with o3-mini."}}
```

**Root Cause:**
- Planner uses o3-mini model (`openai_planner_model: str = "o3-mini"` in settings.py)
- o3-mini doesn't support web_search_preview tool
- `build_tool_payloads()` includes web_search by default
- Planner tried to use unsupported tool → 400 error

**Solution:**
```python
# api/app/routers/plans.py line 106-109
# Filter out web_search for o3-mini (not supported)
settings = get_settings()
if "o3-mini" in settings.openai_planner_model:
    tools = [t for t in tools if not (isinstance(t, dict) and t.get("type") == "web_search_preview")]
```

**Why This Works:**
- Only affects planner (extractor uses gpt-4o which supports web_search)
- Doesn't break other models (gpt-4o, o3, etc.)
- Simple string check for "o3-mini" in model name
- Planner can still use file_search (the critical tool)

---

## 🧪 Testing Completed

### Unit Tests (All Passing)
```bash
pytest api/tests/test_generators.py -v
# Result: 24/24 passed

pytest api/tests/test_plans_materialize.py -v
# Result: 3/3 passed (no regression)
```

**Test Coverage:**
- ✅ CodeGenerator ABC interface tests
- ✅ SyntheticDatasetGenerator (7 tests)
- ✅ SklearnLogisticGenerator (10 tests)
- ✅ GeneratorFactory (3 tests)
- ✅ Integration tests (2 tests)
- ✅ Regression tests (2 tests)

### Live API Tests (Partially Completed)

**Completed:**
1. ✅ Server health check (`/internal/config/doctor`)
2. ✅ Paper ingestion (TextCNN PDF uploaded)
   - Paper ID: `15017eb5-68ee-4dcb-b3b4-1c98479c3a93`
   - Vector Store ID: `vs_68e332805ef881919423728eb33311a8`
3. ✅ Claim extraction (28 claims extracted from Table 2)
   - Claims include: MR, SST-1, SST-2, Subj, TREC, CR, MPQA datasets
   - All with accuracy metrics, splits, and confidence scores

**Needs Testing After Server Restart:**
4. ⏳ Verify claims saved to database
   ```bash
   curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims"
   # Expected: 28 claims returned from database
   ```

5. ⏳ Test planner with o3-mini (should work now)
   ```bash
   curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan" \
     -H "Content-Type: application/json" \
     -d '{"claims": [{...}]}'
   # Expected: No "web_search_preview not supported" error
   ```

6. ⏳ Full end-to-end pipeline
   - Ingest → Extract → Plan → Materialize → Verify notebook

---

## 📝 Code Changes Summary

### Commit 1: `6fcae9d` - Phase 1 Generator Refactor

**Added Files (7):**
```
api/app/materialize/generators/__init__.py
api/app/materialize/generators/base.py
api/app/materialize/generators/dataset.py
api/app/materialize/generators/factory.py
api/app/materialize/generators/model.py
api/tests/test_generators.py
```

**Modified Files (1):**
```
api/app/materialize/notebook.py
```

**Stats:** +842 insertions, -73 deletions

**Key Changes:**
- Extracted hardcoded dataset/model logic into separate generators
- Introduced CodeGenerator ABC with 3 methods: `generate_imports()`, `generate_code()`, `generate_requirements()`
- Factory pattern for selecting generators (Phase 1: always synthetic + logistic)
- Comprehensive test suite (24 tests)

### Commit 2: `9a94207` - Claims DB + o3-mini Fix

**Modified Files (5):**
```
api/app/data/models.py          # Added ClaimCreate/ClaimRecord
api/app/data/supabase.py        # Added insert_claims/get_claims_by_paper
api/app/data/__init__.py        # Export claim models
api/app/routers/papers.py       # Save claims + GET endpoint
api/app/routers/plans.py        # Filter web_search for o3-mini
```

**Stats:** +152 insertions, -1 deletion

**Key Changes:**
- Database models for claims with full schema compliance
- Bulk insert with error handling (extraction continues even if save fails)
- GET endpoint for claim verification
- o3-mini compatibility filter

---

## 🔍 Current System State

### What's Working End-to-End ✅
1. **Ingest:** Paper uploaded to Supabase storage + OpenAI vector store
2. **Extract:** 28 claims extracted from TextCNN paper
3. **Claims Persist:** Claims now saved to database (needs verification after restart)
4. **Materialize:** Notebooks generated with new modular system
5. **Phase 1 Complete:** All tests pass, no regressions

### What's Still Fake (Expected in Phase 1) ⚠️
- ❌ Notebooks use synthetic data (not real SST-2, MNIST, etc.)
- ❌ Notebooks use LogisticRegression (not TextCNN, ResNet, etc.)
- ❌ Factory doesn't select based on plan yet (always synthetic + logistic)

**This is EXACTLY as designed for Phase 1** - Zero behavior change!

### What's Next (Phase 2) 🚀
See [ROADMAP__Future_Work.md](ROADMAP__Future_Work.md) Section 4.

---

## 🐛 Issues Encountered & Resolved

### Issue 1: Claims Not Saving to Database ✅ FIXED

**Symptoms:**
- Extraction returned 28 claims via SSE
- But no claims in database
- No errors in logs

**Root Cause:**
- Extractor code in `papers.py` line 680-688 only yielded SSE events
- Never called `db.insert_claims()`
- Claims were validated then discarded

**Investigation:**
```python
# Before fix (papers.py:680-688):
logger.info("extractor.run.complete paper_id=%s claims=%s", paper.id, len(claims_payload))
record_trace(guardrail_status)
yield _sse_event("stage_update", {"stage": "extract_complete"})
yield _sse_event("result", {"claims": claims_payload})
# ❌ No database insert!
```

**Fix Applied:**
```python
# After fix (papers.py:680-712):
# Save claims to database
try:
    from ..data.models import ClaimCreate
    claim_records = [ClaimCreate(...) for claim in parsed_output.claims]
    inserted_claims = db.insert_claims(claim_records)
    logger.info("extractor.claims.saved paper_id=%s count=%d", paper.id, len(inserted_claims))
except Exception as exc:
    logger.exception("extractor.claims.save_failed paper_id=%s error=%s", paper.id, str(exc))
    yield _sse_event("log_line", {"message": f"Warning: Claims extracted but failed to save: {str(exc)}"})

# Then continue with SSE events...
```

**Status:** ✅ Fixed, needs verification after server restart

### Issue 2: o3-mini + web_search Incompatibility ✅ FIXED

**Symptoms:**
```
openai.BadRequestError: Error code: 400 -
{'error': {'message': "Hosted tool 'web_search_preview' is not supported with o3-mini."}}
```

**Root Cause:**
- `openai_planner_model = "o3-mini"` in settings.py
- `build_tool_payloads()` returns file_search + web_search_preview
- o3-mini doesn't support web_search_preview
- OpenAI API rejected request with 400

**Investigation:**
- Checked `plans.py` line 103: `tool_payloads = build_tool_payloads(agent)`
- Checked agent definitions: Planner doesn't specify explicit tools
- Checked runtime: `build_tool_payloads()` returns default tools for all agents
- Identified: Need to filter web_search for o3-mini specifically

**Fix Applied:**
```python
# plans.py line 106-109
settings = get_settings()
if "o3-mini" in settings.openai_planner_model:
    tools = [t for t in tools if not (isinstance(t, dict) and t.get("type") == "web_search_preview")]
```

**Status:** ✅ Fixed, needs verification after server restart

### Issue 3: Confused About Claims Extraction ✅ RESOLVED

**Symptoms:**
- User asked: "are you sure it extracted the claims correctly and uploaded them to the database"
- I had pivoted to pytest tests without verifying DB persistence

**Root Cause:**
- I saw extraction succeed (28 claims via SSE)
- I assumed they were saved
- I didn't verify the database actually received them
- I got sidetracked by pytest tests

**Resolution:**
- User correctly identified the gap
- Investigated extractor code
- Found missing `db.insert_claims()` call
- Fixed the issue
- Added GET endpoint for verification

**Lesson:** Always verify the full pipeline, don't assume!

---

## 📊 Metrics & Stats

### Code Metrics
- **Files Created:** 7 (generators + tests)
- **Files Modified:** 6 (notebook.py + data layer + routers)
- **Tests Added:** 24 unit tests
- **Test Pass Rate:** 100% (27/27 total)
- **Lines Added:** ~994 (842 + 152)
- **Lines Removed:** ~74

### Database Schema
- **Tables Used:** papers, claims (new), plans, runs
- **Claims Table:** 12 fields, 2 indexes, CASCADE delete
- **Foreign Keys:** claims.paper_id → papers.id

### API Endpoints
- **Added:** `GET /api/v1/papers/{paper_id}/claims`
- **Modified:** `POST /api/v1/papers/{paper_id}/extract` (now saves to DB)
- **Fixed:** `POST /api/v1/papers/{paper_id}/plan` (o3-mini compatible)

---

## 🔧 Configuration & Environment

### Models Currently Selected
```python
# config/settings.py
openai_extractor_model: str = "gpt-4o"     # ✅ Supports web_search
openai_planner_model: str = "o3-mini"      # ❌ No web_search (now filtered)
```

### Tool Capabilities
```json
{
  "file_search_per_run": 10,
  "web_search_per_run": 5,
  "code_interpreter_seconds": 60
}
```

### Database
- **Provider:** Supabase PostgreSQL
- **Schema Version:** v1 (nuclear with grants)
- **Active Tables:** papers, claims, plans, runs, run_events, run_series, storyboards

---

## 🚦 Next Steps (In Order)

### Immediate (After Server Restart)
1. **Verify Claims Saved to Database**
   ```bash
   curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims"
   ```
   - Expected: 28 claims returned with full details
   - If fails: Check server logs for "extractor.claims.saved" or "extractor.claims.save_failed"

2. **Test Planner with o3-mini**
   ```bash
   # Get one claim from the extracted claims
   curl.exe -sS -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/plan" \
     -H "Content-Type: application/json" \
     -d '{"claims": [{"dataset": "SST-2", "split": "test", "metric": "accuracy", "value": 88.1, "units": "%", "citation": "Table 2", "confidence": 0.95}]}'
   ```
   - Expected: Plan JSON v1.1 generated successfully
   - If fails: Check if still getting "web_search_preview not supported" error

3. **Full End-to-End Pipeline Test**
   - Ingest fresh paper
   - Extract claims (verify they save)
   - Generate plan (verify o3-mini works)
   - Materialize notebook (verify modular generators work)
   - Inspect notebook (verify still synthetic + logistic)

### Short-Term (Next Session)
4. **Update Roadmap Documentation**
   - Mark Roadmap #1 (Claims DB) as ✅ Complete
   - Mark C-NOTEBOOK-01 Phase 1 as ✅ Complete
   - Update status document

5. **Begin Phase 2: Smart Dataset Selection**
   - Implement `SklearnDatasetGenerator` (digits, iris, wine)
   - Implement `TorchvisionDatasetGenerator` (MNIST, CIFAR10)
   - Implement `HuggingFaceDatasetGenerator` (SST-2, IMDB)
   - Update factory with smart selection logic
   - Add fallback chains for graceful degradation

### Medium-Term (Week 2)
6. **Phase 3: Smart Model Selection**
   - Implement `SklearnModelGenerator` (RandomForest, SVM)
   - Implement `TorchCNNGenerator` (TextCNN architecture)
   - Implement `TorchResNetGenerator` (ResNet variants)
   - Update factory with model selection logic

7. **Phase 4: Docker-Ready Preparation**
   - Environment variables for paths
   - Resource awareness checks
   - Relative paths for containerization

---

## 📚 Key Files to Review Next Session

### Generators (New)
```
api/app/materialize/generators/
├── base.py          # CodeGenerator ABC - defines interface
├── factory.py       # Selection logic (Phase 1: always synthetic + logistic)
├── dataset.py       # SyntheticDatasetGenerator (Phase 2: add real datasets)
└── model.py         # SklearnLogisticGenerator (Phase 3: add real models)
```

### Data Layer (Modified)
```
api/app/data/
├── models.py        # ClaimCreate/ClaimRecord added
├── supabase.py      # insert_claims/get_claims_by_paper added
└── __init__.py      # Export claim models
```

### Routers (Modified)
```
api/app/routers/
├── papers.py        # Save claims (line 680-712), GET claims endpoint (line 727-755)
└── plans.py         # Filter web_search for o3-mini (line 106-109)
```

### Tests (New)
```
api/tests/
└── test_generators.py   # 24 comprehensive unit tests
```

### Documentation
```
docs/Claudedocs/
├── ROADMAP__Future_Work.md           # Sections 1-4 relevant
├── CURRENT_STATUS__2025-10-07.md     # Needs update
└── REHYDRATION__2025-10-08_Phase_1_Complete.md  # THIS FILE
```

---

## 🎓 Key Learnings & Decisions

### Architecture Decisions

1. **Why Factory Pattern?**
   - Enables switching dataset/model generators without changing orchestrator
   - Supports fallback chains (Phase 2+)
   - Testable in isolation
   - Extensible for future generator types

2. **Why Abstract Base Class?**
   - Enforces consistent interface across all generators
   - Type safety with Python type hints
   - Clear contract: generate_imports, generate_code, generate_requirements
   - Fails fast if generator doesn't implement interface

3. **Why Phase 1 Has No Behavior Change?**
   - Reduces regression risk (zero)
   - Proves refactor is safe before adding complexity
   - All existing tests must pass
   - Enables incremental rollout

### Database Decisions

1. **Why Bulk Insert for Claims?**
   - Performance: 28 claims in one transaction vs 28 separate inserts
   - Atomicity: All claims saved or none (transaction safety)
   - Supabase PostgREST supports array inserts efficiently

2. **Why Continue on DB Save Failure?**
   - Extraction is the expensive part (OpenAI API call)
   - Claims still returned via SSE to client
   - User can retry save without re-extracting
   - Logs warning for debugging

### Tool Filtering Decision

1. **Why Filter web_search for o3-mini?**
   - Alternative: Change model to gpt-4o (more expensive)
   - Alternative: Remove web_search from all agents (breaks extractor)
   - Filter is cheapest, least invasive solution
   - Only affects planner (web_search less critical than file_search)

---

## 🔗 Related Resources

### Documentation
- [ROADMAP__Future_Work.md](ROADMAP__Future_Work.md) - Section 4: C-NOTEBOOK-01
- [ROADMAP_P2N.md](../ROADMAP_P2N.md) - Milestone B: Plan → Materialize
- [schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) - Claims table definition

### Code References
- Extractor: [papers.py:312-724](../../api/app/routers/papers.py#L312-L724)
- Planner: [plans.py:88-250](../../api/app/routers/plans.py#L88-L250)
- Notebook Generator: [notebook.py:43-144](../../api/app/materialize/notebook.py#L43-L144)
- Database: [supabase.py:144-190](../../api/app/data/supabase.py#L144-L190)

### Commits
- Phase 1 Refactor: `6fcae9d`
- Claims DB + o3-mini Fix: `9a94207`

---

## 💬 Quick Start for Next Session

```bash
# 1. Verify server is running
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor

# 2. Check claims saved from previous extraction
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims"

# 3. Run all tests
pytest api/tests/test_generators.py api/tests/test_plans_materialize.py -v

# 4. If all pass, proceed to Phase 2 planning
```

---

## 🎉 Session Achievements

✅ **Phase 1 Code Complete** - Modular generator architecture with zero regression
⚠️ **Claims DB Code Written** - NOT YET VERIFIED with live database
⚠️ **o3-mini Fix Code Written** - NOT YET VERIFIED with live planner
✅ **27/27 Tests Passing** - Full test coverage for generator refactor
✅ **2 Commits Pushed** - All changes on main branch
✅ **Documentation Updated** - This rehydration doc created

**⚠️ Phase 1 CODE is complete but VERIFICATION is pending!**

**CRITICAL NEXT STEPS:**
1. Restart server with new code
2. Verify claims saved to database
3. Test planner with o3-mini
4. ONLY THEN proceed to Phase 2

**DO NOT START PHASE 2 WITHOUT VERIFYING CLAIMS DB SAVE!**
