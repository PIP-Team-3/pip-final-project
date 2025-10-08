# Working Log: Two-Stage Planner Implementation
**Date:** 2025-10-08
**Session Goal:** Implement two-stage planner architecture (o3-mini + GPT-4o schema fix)
**Status:** ✅ **CODE COMPLETE - NOT YET TESTED WITH LIVE API**

---

## ⚠️ CRITICAL: IMPLEMENTATION COMPLETE BUT UNTESTED

**The two-stage planner code has been written and unit tests pass, but we have NOT yet:**
- ❌ Tested with live OpenAI API
- ❌ Verified o3-mini Stage 1 output with real paper
- ❌ Confirmed GPT-4o Stage 2 successfully fixes real malformed plans
- ❌ Measured actual success rate improvement
- ❌ Run end-to-end planner call with TextCNN paper

**DO NOT assume this works until live API testing is complete!**

---

## 📋 Session Timeline

### 1. Session Start - Plan Approved
**Time:** Start of session
**Action:** User reviewed comprehensive two-stage planner plan and approved implementation

**Context:**
- Phase 1 complete (claims DB + o3-mini compatibility fixes verified)
- o3-mini planner has ~40% success rate due to schema issues
- Proposed solution: Two-stage architecture (reasoning + schema fix)

---

### 2. Settings Configuration ✅
**Time:** First implementation step
**File:** `api/app/config/settings.py`

**Changes Made:**
```python
# Lines 28-29 added
openai_schema_fixer_model: str = "gpt-4o"  # Model for Stage 2 schema fixing
planner_two_stage_enabled: bool = True     # Enable two-stage planner
```

**Why:**
- Allow configuration of schema fixer model (defaults to gpt-4o)
- Feature flag to enable/disable two-stage behavior
- Can be overridden via environment variables

**Status:** ✅ Implemented, not tested

---

### 3. Schema Fixer Function Implementation ✅
**Time:** Main implementation phase
**File:** `api/app/routers/plans.py`

**Changes Made:**
Added `_fix_plan_schema()` async function (lines 83-180, ~98 lines)

**Function Signature:**
```python
async def _fix_plan_schema(
    raw_plan: dict,
    budget_minutes: int,
    paper_title: str,
    span: Any = None,
) -> dict
```

**Key Implementation Details:**
1. **Uses Chat Completions API** (not Responses API)
   - Simpler for this use case
   - `response_format={"type": "json_object"}` ensures JSON output
   - `temperature=0.0` for determinism

2. **Prompt Strategy:**
   - System: "You are a JSON schema expert"
   - User: Provides raw plan + target schema + context
   - Emphasizes: "Preserve ALL reasoning, justifications, quotes"

3. **Error Handling:**
   - Catches all exceptions
   - Converts to HTTPException with code `E_SCHEMA_FIX_FAILED`
   - Logs errors for debugging

4. **Tracing:**
   - Uses `traced_subspan(span, "p2n.planner.stage2.schema_fix")`
   - Logs model, raw fields, fixed fields

**Status:** ✅ Implemented, not tested with real API

---

### 4. Integration into create_plan Flow ✅
**Time:** Main implementation phase
**File:** `api/app/routers/plans.py`

**Changes Made:**
Modified `create_plan` endpoint to call Stage 2 after Stage 1 (lines 387-403)

**Flow Before:**
```
o3-mini → Parse JSON → Validate schema → If invalid: FAIL
```

**Flow After:**
```
Stage 1: o3-mini → Parse JSON → Log Stage 1 complete
    ↓
Stage 2 Check: If two_stage_enabled AND o3-mini model
    ↓
Stage 2: Call _fix_plan_schema() → Fixed JSON
    ↓
Then: Validate schema → Success (or fail with better error)
```

**Code Added:**
```python
logger.info("planner.stage1.complete model=%s fields=%s", planner_model, list(plan_raw.keys()))

# TWO-STAGE PLANNER: Stage 2 schema fixing (if enabled)
settings_for_stage2 = get_settings()
if settings_for_stage2.planner_two_stage_enabled and "o3-mini" in planner_model:
    logger.info("planner.stage2.start paper_id=%s", paper.id)
    plan_raw = await _fix_plan_schema(
        raw_plan=plan_raw,
        budget_minutes=policy_budget,
        paper_title=paper.title,
        span=span
    )
    logger.info("planner.stage2.applied paper_id=%s", paper.id)
```

**Why This Logic:**
- Only activates for o3-mini (smart detection via model name)
- Feature flag allows disabling without code changes
- Logs clearly identify Stage 1 vs Stage 2
- Preserves span for tracing

**Status:** ✅ Implemented, not tested with real API

---

### 5. Planner Prompt Update ✅
**Time:** Implementation phase
**File:** `api/app/agents/definitions.py`

**Changes Made:**
Updated planner system prompt (lines 120-130, ~10 lines modified)

**Old Prompt:**
```python
"Produce a deterministic Plan JSON v1.1 under 20 CPU minutes. "
"Include dataset, model, config, metrics, visualizations, explain steps, and a justifications map"
" with verbatim paper quotes."
```

**New Prompt:**
```python
"You are an ML reproduction expert. Analyze the paper and create a detailed reproduction plan.\n\n"
"FOCUS ON REASONING (not exact schema format):\n"
"1. Dataset choice: Assess availability, licensing, size constraints\n"
"2. Model architecture: Match paper's approach or adapt for CPU execution under 20 minutes\n"
"3. Training configuration: Select epochs, batch size, optimizer, learning rate\n"
"4. Metrics: Identify metrics from the paper to reproduce\n"
"5. Justifications: Include verbatim quotes from the paper explaining your choices\n\n"
"Include dataset, model, config, metrics, visualizations, explain steps, and justifications with paper quotes.\n"
"Aim for correctness and strong reasoning - schema formatting will be handled separately."
```

**Why This Change:**
- Emphasizes **reasoning quality** over schema compliance
- Explicitly tells model "schema formatting will be handled separately"
- Focuses o3-mini on what it does best (multi-step reasoning)
- Lists specific reasoning steps to guide thinking

**Expected Impact:**
- Stage 1 (o3-mini) produces better justifications and reasoning
- Stage 1 may produce more schema variance (acceptable - Stage 2 fixes it)
- Overall quality should improve

**Status:** ✅ Implemented, not tested with real API

---

### 6. Unit Tests Implementation ✅
**Time:** Implementation phase
**File:** `api/tests/test_two_stage_planner.py`

**Tests Created:**
1. ✅ `test_fix_plan_schema_with_malformed_input` - Tests schema correction (budget_minutes in wrong location)
2. ✅ `test_fix_plan_schema_with_valid_input` - Tests idempotency with already-valid plans
3. ✅ `test_fix_plan_schema_preserves_justifications` - Tests that reasoning is preserved
4. ✅ `test_two_stage_planner_settings` - Tests configuration settings exist

**Test Results:**
```bash
api/tests/test_two_stage_planner.py .... 4/4 PASSED ✅
```

**Mocking Strategy:**
- Mock `api.app.config.llm.get_client` to avoid real OpenAI calls
- Mock `traced_subspan` to avoid tracing infrastructure
- Mock settings to control configuration
- Use anyio backend for async tests

**What Tests Verify:**
- ✅ Schema fixer can correct malformed JSON
- ✅ Schema fixer preserves justifications and reasoning
- ✅ Settings are correctly configured
- ✅ Basic code paths don't crash

**What Tests DO NOT Verify:**
- ❌ Real o3-mini output structure
- ❌ Real GPT-4o schema fixing capability
- ❌ Actual API latency and cost
- ❌ Integration with real planner flow
- ❌ Edge cases with complex papers

**Status:** ✅ Implemented and passing, but tests use mocks (not real API)

---

### 7. Regression Testing ✅
**Time:** Verification phase

**Tests Run:**
```bash
# Generator tests (Phase 1)
api/tests/test_generators.py ............... 24/24 PASSED ✅

# Materialize tests (Phase 1)
api/tests/test_plans_materialize.py ........ 3/3 PASSED ✅

# Two-stage planner tests (new)
api/tests/test_two_stage_planner.py ........ 4/4 PASSED ✅

TOTAL: 31/31 tests passing ✅
```

**Verdict:** Zero regressions - all existing functionality intact

**Status:** ✅ Verified, no code regressions

---

## 📦 Code Changes Summary

### Files Created (1):
- `api/tests/test_two_stage_planner.py` (+224 lines) - Unit tests with mocks

### Files Modified (3):
1. `api/app/config/settings.py` (+3 lines) - Feature flag and model config
2. `api/app/routers/plans.py` (+105 lines) - Schema fixer function + integration
3. `api/app/agents/definitions.py` (~10 lines modified) - Reasoning-focused prompt

### Total Changes:
- **Lines Added:** ~342
- **Lines Modified:** ~10
- **Tests Added:** 4 comprehensive unit tests
- **Test Pass Rate:** 31/31 (100%)

---

## 🎯 Architecture: How Two-Stage Planner Works

### Flow Diagram:

```
┌─────────────────────────────────────────────────────────┐
│  POST /api/v1/papers/{paper_id}/plan                    │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────────┐
│  STAGE 1: o3-mini (Reasoning Engine)                    │
│  ─────────────────────────────────────────────────────  │
│  • Model: o3-mini (reasoning model)                     │
│  • Tools: file_search (no web_search, no temperature)   │
│  • Prompt: "Focus on reasoning, not schema"             │
│  • Output: Raw plan JSON (may have schema issues)       │
│                                                          │
│  Potential Issues:                                       │
│  - budget_minutes at top level instead of policy.*      │
│  - Missing required fields                               │
│  - Excellent reasoning and justifications ✅             │
└──────────────────┬──────────────────────────────────────┘
                   │ Raw Plan Dict
                   │
                   ↓
         ┌─────────────────────┐
         │  Check Feature Flag  │
         │  + Model Detection   │
         └─────────┬───────────┘
                   │
         YES (two_stage_enabled AND o3-mini)
                   │
                   ↓
┌─────────────────────────────────────────────────────────┐
│  STAGE 2: GPT-4o (Schema Fixer)                         │
│  ─────────────────────────────────────────────────────  │
│  • Model: gpt-4o (fast, accurate, cheap)                │
│  • API: Chat Completions (simpler than Responses)       │
│  • Temp: 0.0 (deterministic)                            │
│  • Format: JSON object (guaranteed valid JSON)          │
│                                                          │
│  Prompt Strategy:                                        │
│  - System: "You are a JSON schema expert"               │
│  - User: Raw plan + PlanDocumentV11 schema + context    │
│  - Rules: Preserve ALL reasoning, move fields, add      │
│           missing required fields                        │
│                                                          │
│  Output: Fixed plan matching PlanDocumentV11 exactly    │
└──────────────────┬──────────────────────────────────────┘
                   │ Fixed Plan Dict
                   │
                   ↓
┌─────────────────────────────────────────────────────────┐
│  Validation & Storage                                    │
│  ─────────────────────────────────────────────────────  │
│  • Convert to PlannerOutput dataclass                    │
│  • Run output guardrails                                 │
│  • Validate against PlanDocumentV11 Pydantic schema      │
│  • Save to database as JSONB                             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ↓
              Return Plan
```

### Conditional Logic:

```python
# Stage 1 always runs
plan_raw = json.loads(output_text)
logger.info("planner.stage1.complete model=%s fields=%s", planner_model, list(plan_raw.keys()))

# Stage 2 only runs if:
settings = get_settings()
if settings.planner_two_stage_enabled and "o3-mini" in planner_model:
    plan_raw = await _fix_plan_schema(...)  # Fix schema issues
```

**Why This Design:**
- ✅ Non-invasive: Only activates for o3-mini
- ✅ Configurable: Feature flag to disable
- ✅ Future-proof: Other models (gpt-4o, o1) bypass Stage 2
- ✅ Traceable: Clear logging at each stage

---

## 🔍 Expected Benefits (UNVERIFIED)

**These are predictions based on design - NOT measured results:**

| Metric | Before (o3-mini only) | After (Two-Stage) | Improvement |
|--------|----------------------|------------------|-------------|
| **Success Rate** | ~40% | **~95%+** | +137% (predicted) |
| **Reasoning Quality** | Excellent | **Excellent** | Maintained |
| **Schema Compliance** | Poor | **Excellent** | Fixed |
| **Latency** | ~10s | ~12-13s | +2-3s (acceptable) |
| **Cost per Plan** | ~$0.05 | ~$0.06 | +$0.01 (negligible) |

**⚠️ WARNING: These numbers are ESTIMATES based on:**
- GPT-4o typical response time (~2s)
- GPT-4o cost (~$0.01 for this prompt size)
- Assumption that GPT-4o can fix schema issues

**We will NOT know real metrics until live API testing!**

---

## 🧪 Testing Status

### ✅ Completed Testing:
1. **Unit Tests:** 4/4 passing with mocked OpenAI client
2. **Regression Tests:** 27/27 existing tests still passing
3. **Code Compilation:** All code compiles without errors
4. **Settings:** Configuration loads correctly

### ❌ NOT Yet Tested:
1. **Live o3-mini Call:** Have not called o3-mini with two-stage enabled
2. **Real Schema Issues:** Have not seen actual malformed o3-mini output
3. **GPT-4o Schema Fix:** Have not verified GPT-4o can fix real issues
4. **End-to-End Flow:** Have not tested full pipeline with TextCNN paper
5. **Performance:** Have not measured actual latency or cost
6. **Success Rate:** Have not measured improvement over baseline
7. **Edge Cases:** Have not tested with complex/unusual papers

---

## 🚦 Next Steps (CRITICAL - DO BEFORE PHASE 2)

### Immediate: Live API Testing Required

**Step 1: Verify Settings**
```bash
# Check server loaded new settings
curl http://127.0.0.1:8000/internal/config/doctor

# Expected output should include:
# - planner_two_stage_enabled: true
# - openai_schema_fixer_model: gpt-4o
# - openai_planner_model: o3-mini
```

**Step 2: Test with TextCNN Paper**
```bash
# Use existing paper with extracted claims
PAPER_ID="15017eb5-68ee-4dcb-b3b4-1c98479c3a93"

# Get claims for plan input
curl "http://127.0.0.1:8000/api/v1/papers/${PAPER_ID}/claims" > claims.json

# Extract first claim as test input
# Build planner request with budget_minutes=20

# Call planner endpoint
curl -X POST "http://127.0.0.1:8000/api/v1/papers/${PAPER_ID}/plan" \
  -H "Content-Type: application/json" \
  -d @planner_request.json
```

**Step 3: Monitor Logs for Two-Stage Execution**
```bash
# Watch server logs during planner call
# Should see:
# - planner.stage1.complete model=o3-mini fields=[...]
# - planner.stage2.start paper_id=15017eb5...
# - planner.stage2.complete model=gpt-4o raw_fields=[...] fixed_fields=[...]
# - planner.stage2.applied paper_id=15017eb5...
```

**Step 4: Analyze Results**
- ✅ Did Stage 1 (o3-mini) complete without errors?
- ✅ Did Stage 2 (GPT-4o) get called?
- ✅ Did Stage 2 fix any schema issues?
- ✅ Did final plan validate against PlanDocumentV11?
- ✅ What fields did Stage 2 modify?
- ✅ Were justifications preserved?

**Step 5: Test Multiple Runs**
Run planner 10 times to measure:
- Success rate (should be >90% if working)
- Average latency (Stage 1 + Stage 2)
- Cost per run (check OpenAI dashboard)
- Schema issues fixed by Stage 2 (how often?)

**Step 6: Compare to Baseline**
- Disable two-stage: `planner_two_stage_enabled=false`
- Run planner 10 times with o3-mini only
- Measure baseline success rate (~40% expected)
- Re-enable two-stage and compare

---

## 🐛 Known Issues & Risks (BEFORE TESTING)

### Issue 1: Untested with Real o3-mini Output
**Status:** Unknown schema variance
**Risk:** High
**Impact:** If o3-mini produces very different JSON than expected, Stage 2 may fail
**Mitigation:** Test with multiple papers, review Stage 1 logs

### Issue 2: GPT-4o Schema Fix Capability Unknown
**Status:** Assumed GPT-4o can fix schemas
**Risk:** Medium
**Impact:** If GPT-4o can't restructure plans, two-stage provides no benefit
**Mitigation:** Manual review of Stage 2 output, add error logging

### Issue 3: Cost May Be Higher Than Expected
**Status:** Estimated ~$0.01 per Stage 2 call
**Risk:** Low
**Impact:** If prompts are larger than expected, cost could double
**Mitigation:** Monitor OpenAI dashboard, optimize prompts if needed

### Issue 4: Latency May Exceed Acceptable Range
**Status:** Estimated +2-3s
**Risk:** Low
**Impact:** If Stage 2 takes >5s, total latency becomes problematic
**Mitigation:** Use async calls, consider caching, profile slow calls

### Issue 5: Feature Flag May Not Work
**Status:** Logic seems correct but untested
**Risk:** Medium
**Impact:** Stage 2 might run for all models (waste) or never run (no benefit)
**Mitigation:** Test with both o3-mini and gpt-4o, verify logs

---

## 📊 Success Criteria for Live Testing

**Before declaring this feature "working", we must verify:**

1. ✅ Stage 1 (o3-mini) completes successfully
2. ✅ Stage 2 (GPT-4o) is called when `two_stage_enabled=True` and model is o3-mini
3. ✅ Stage 2 is NOT called when `two_stage_enabled=False`
4. ✅ Stage 2 is NOT called when model is gpt-4o (not o3-mini)
5. ✅ Stage 2 successfully fixes at least one schema issue
6. ✅ Final plan validates against PlanDocumentV11
7. ✅ Justifications from Stage 1 are preserved in Stage 2 output
8. ✅ Success rate improves from baseline (e.g., 40% → 90%+)
9. ✅ Latency is acceptable (<15s total)
10. ✅ Cost is acceptable (<$0.10 per plan)

**If ANY of the above fail, this implementation needs refinement!**

---

## 🔧 Configuration & Rollback

### Enable Two-Stage (Default):
```python
# api/app/config/settings.py
planner_two_stage_enabled: bool = True
```

Or via environment variable:
```bash
PLANNER_TWO_STAGE_ENABLED=true
```

### Disable Two-Stage (Rollback):
```python
# api/app/config/settings.py
planner_two_stage_enabled: bool = False
```

Or via environment variable:
```bash
PLANNER_TWO_STAGE_ENABLED=false
```

**Rollback is INSTANT - just restart server with setting changed.**

---

## 📝 Code Quality Notes

### Good Practices Applied:
1. ✅ **Feature flag** for safe rollout
2. ✅ **Comprehensive logging** at each stage
3. ✅ **Tracing integration** for observability
4. ✅ **Error handling** with structured HTTPExceptions
5. ✅ **Docstrings** on new functions
6. ✅ **Type hints** throughout
7. ✅ **Unit tests** with proper mocking
8. ✅ **Zero regressions** (all 27 existing tests pass)

### Areas for Future Improvement:
1. ⏳ Add integration tests with real API (pending live testing)
2. ⏳ Add metrics collection (success rate, latency, cost)
3. ⏳ Add Prometheus/Grafana dashboards for monitoring
4. ⏳ Optimize Stage 2 prompt if success rate <90%
5. ⏳ Add caching for repeated plans (future optimization)

---

## 💬 Session Achievements

**✅ Code Complete:**
- Schema fixer function implemented (~100 lines)
- Integration with create_plan flow
- Reasoning-focused prompt updates
- Configuration settings
- 4 unit tests (all passing)
- Zero regressions

**⚠️ Not Yet Verified:**
- Live API testing pending
- Success rate improvement unmeasured
- Cost and latency unconfirmed
- Edge cases untested

**Status:** Ready for live API testing, but DO NOT assume it works until verified!

---

## 🎯 CRITICAL NEXT ACTION

**DO THIS BEFORE PROCEEDING TO PHASE 2:**

1. **Restart server** with new code
2. **Run live planner test** with TextCNN paper
3. **Monitor logs** for two-stage execution
4. **Verify success** and schema fixing
5. **Measure metrics** (success rate, latency, cost)
6. **Compare to baseline** (o3-mini only)
7. **Document results** in new working log

**ONLY THEN can we confidently say:**
- ✅ "Two-stage planner is working"
- ✅ "Ready to proceed to Phase 2"

---

**End of Working Log**
**Last Updated:** 2025-10-08 (after implementation, before live testing)
**Next Update:** After live API testing with TextCNN paper

