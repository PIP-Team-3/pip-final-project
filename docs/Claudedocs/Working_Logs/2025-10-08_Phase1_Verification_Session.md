# Working Log: Phase 1 Verification Session
**Date:** 2025-10-08
**Session Goal:** Verify Phase 1 code (commits `6fcae9d` and `9a94207`) after server restart
**Status:** 🔧 **IN PROGRESS - CRITICAL FIX APPLIED**

---

## Session Timeline

### 1. Session Start - Verification Plan Created
**Time:** Start of session
**Action:** Combined insights from multiple docs to create comprehensive verification plan

**Documents Reviewed:**
- `REHYDRATION__2025-10-08_Phase_1_Complete.md` - Phase 1 code status
- `P2N_Phase1_Verification_and_Fixes_2025-10-08.md` - Verification playbook
- `ROADMAP__Future_Work.md` - Phase 2 planning

**Plan Created:**
- Step 0: Server restart (user will do)
- Step 1: Verify claims DB persistence (28 claims expected)
- Step 2: Verify o3-mini planner (no web_search error)
- Step 3: End-to-end smoke test
- Step 4: Verify test suite passes (27 tests)
- Step 5: Document Phase 1 completion

---

### 2. Step 0: Server Health Verification ✅
**Time:** After user restarted server
**Action:** Verified server is running with new code

**Commands Run:**
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/internal/config/doctor
```

**Results:**
- ✅ Server healthy
- ✅ OpenAI SDK 1.109.1 loaded
- ✅ Responses mode enabled
- ✅ Models configured: extractor=gpt-4o
- ✅ File search and web search tools available

**Verdict:** Server ready for testing

---

### 3. Step 1: Claims Database Persistence - ISSUE DISCOVERED 🚨
**Time:** First verification attempt
**Action:** Triggered extraction on TextCNN paper to verify claims persistence

**Command:**
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract"
```

**Observations:**
1. ✅ **Extraction succeeded** - Returned 28 claims via SSE
2. ✅ **Claims saved to database** - Code works!
3. ⚠️ **Missing SSE events** - No `persist_start` or `persist_done` events
4. 🚨 **CRITICAL: Duplicate claims** - Database has 56 claims (28 from previous run + 28 from new run)

**Database Query Result:**
```bash
curl "http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims"
# Response: claims_count: 56
# Two timestamp batches: 2025-10-08T17:49:07 and 2025-10-08T18:26:28
```

**Root Cause Analysis:**
- The Phase 1 code in commit `9a94207` adds claims persistence
- However, it uses **append** logic (INSERT only)
- No **replace** logic (DELETE before INSERT)
- Each extraction run adds another set of 28 claims
- Documentation expected "replace-per-paper (simple, deterministic)" policy

**Impact:**
- ❌ Violates Phase 1 design intent (replace policy)
- ❌ Will accumulate duplicate claims over time
- ❌ Breaks uniqueness expectations
- ✅ Core functionality (saving claims) DOES work

---

### 4. User Request: Fix Deduplication BEFORE Proceeding ⚠️
**Time:** After discovering duplicates
**User Decision:** "Stop, fix deduplication first, delete duplicates, add replace logic"

**Why This Is Critical:**
- Phase 1 verification requires clean state
- Cannot proceed to Step 2 (planner) with dirty data
- Need to verify the FULL claims persistence flow (delete + insert)
- Each paper should have exactly ONE set of claims at a time

---

### 5. Fix Applied: Claims Replace Policy Implementation 🔧
**Time:** Current
**Action:** Added replace logic to claims persistence

#### Change 1: Added `delete_claims_by_paper()` Method
**File:** `api/app/data/supabase.py`
**Lines:** 192-212 (new method)

**What Changed:**
```python
def delete_claims_by_paper(self, paper_id: str) -> int:
    """
    Delete all claims for a given paper.

    This is used during extraction to implement a "replace" policy:
    each extraction run replaces all previous claims for that paper.

    Args:
        paper_id: UUID of the paper

    Returns:
        Number of claims deleted
    """
    response = (
        self._client.table("claims")
        .delete()
        .eq("paper_id", paper_id)
        .execute()
    )
    data = getattr(response, "data", None) or []
    return len(data)
```

**Why This Change:**
- Enables "replace policy" - delete old claims before inserting new ones
- Returns count of deleted claims for logging/transparency
- Follows Supabase PostgREST pattern used elsewhere in the file

---

#### Change 2: Updated Extraction Logic - Delete Before Insert
**File:** `api/app/routers/papers.py`
**Lines:** 680-727 (modified section)

**What Changed:**

**Before (append-only logic):**
```python
# Save claims to database
try:
    from ..data.models import ClaimCreate
    claim_records = [ClaimCreate(...) for claim in parsed_output.claims]
    inserted_claims = db.insert_claims(claim_records)
    logger.info("extractor.claims.saved paper_id=%s count=%d", paper.id, len(inserted_claims))
except Exception as exc:
    logger.exception("extractor.claims.save_failed paper_id=%s error=%s", paper.id, str(exc))
    yield _sse_event("log_line", {"message": f"Warning: Claims extracted but failed to save: {str(exc)}"})
```

**After (replace policy with SSE events):**
```python
# Save claims to database (replace policy: delete old claims first)
try:
    from ..data.models import ClaimCreate

    # SSE event: persistence starting
    yield _sse_event("stage_update", {"stage": "persist_start", "count": len(parsed_output.claims)})

    # Delete existing claims for this paper (replace policy)
    deleted_count = db.delete_claims_by_paper(paper.id)
    if deleted_count > 0:
        logger.info("extractor.claims.deleted paper_id=%s count=%d", paper.id, deleted_count)

    # Insert new claims
    claim_records = [ClaimCreate(...) for claim in parsed_output.claims]
    inserted_claims = db.insert_claims(claim_records)
    logger.info("extractor.claims.saved paper_id=%s count=%d", paper.id, len(inserted_claims))

    # SSE event: persistence complete
    yield _sse_event("stage_update", {"stage": "persist_done", "count": len(inserted_claims)})
except Exception as exc:
    logger.exception("extractor.claims.save_failed paper_id=%s error=%s", paper.id, str(exc))
    yield _sse_event("log_line", {"message": f"Warning: Claims extracted but failed to save: {str(exc)}"})
```

**Why These Changes:**
1. **Replace policy:** `delete_claims_by_paper()` called BEFORE `insert_claims()`
2. **SSE transparency:** Added `persist_start` and `persist_done` events (matches verification doc expectations)
3. **Logging:** Added log for deleted claims count
4. **Clean state:** Each extraction run replaces previous claims for that paper
5. **Idempotency:** Running extraction multiple times yields same final state (28 claims, not 28*N)

---

## Changes Summary

### Files Modified: 2

#### 1. `api/app/data/supabase.py`
- **Lines added:** ~20
- **Change:** Added `delete_claims_by_paper()` method
- **Impact:** Database layer now supports claim replacement

#### 2. `api/app/routers/papers.py`
- **Lines modified:** ~50
- **Change:** Updated extraction logic to delete before insert + added SSE events
- **Impact:** Claims persistence now uses replace policy + visible in SSE stream

### Total Lines Changed: ~70

---

## Expected Behavior After Fix

### Before This Fix:
```
Run 1: Extract → 28 claims in DB
Run 2: Extract → 56 claims in DB (duplicates!)
Run 3: Extract → 84 claims in DB (more duplicates!)
```

### After This Fix:
```
Run 1: Extract → 28 claims in DB
Run 2: Extract → Delete 28, Insert 28 → 28 claims in DB
Run 3: Extract → Delete 28, Insert 28 → 28 claims in DB
```

### SSE Stream After Fix:
```
event: stage_update, data: {"stage": "extract_start"}
event: stage_update, data: {"stage": "file_search_call"}
event: stage_update, data: {"stage": "extract_complete"}
event: stage_update, data: {"stage": "persist_start", "count": 28}  ← NEW
event: stage_update, data: {"stage": "persist_done", "count": 28}   ← NEW
event: result, data: {"claims": [...]}
```

---

## Next Steps (Waiting on User)

### Immediate: Server Restart Required
**User must restart the server** to load the new code:
```bash
# Stop current server (Ctrl+C)
# Start fresh:
python -m uvicorn app.main:app --app-dir api --log-level info
```

### After Restart:

1. **Delete duplicate claims** (manual cleanup):
   - Database currently has 56 claims (duplicates from 2 extraction runs)
   - Need to delete all claims for paper `15017eb5-68ee-4dcb-b3b4-1c98479c3a93`
   - Fresh extraction will then insert clean 28 claims

2. **Re-verify claims persistence**:
   ```bash
   # Extract with new replace logic
   curl -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5.../extract"

   # Should see persist_start and persist_done events
   # Should show deleted_count=0 (first run after cleanup) or 28 (subsequent runs)

   # Verify count
   curl "http://127.0.0.1:8000/api/v1/papers/15017eb5.../claims" | grep claims_count
   # Expected: "claims_count": 28
   ```

3. **Run extraction again** (test idempotency):
   ```bash
   # Second extraction should DELETE 28, INSERT 28
   curl -X POST "http://127.0.0.1:8000/api/v1/papers/15017eb5.../extract"

   # Verify count still 28 (not 56!)
   curl "http://127.0.0.1:8000/api/v1/papers/15017eb5.../claims" | grep claims_count
   # Expected: "claims_count": 28
   ```

4. **Continue with Step 2** (o3-mini planner verification)

---

## Design Rationale: Replace Policy

### Why Replace Instead of Upsert?

**Option A: Upsert (update if exists, insert if not)**
- ❌ Requires unique constraint on (paper_id, dataset, metric, value, citation)
- ❌ Complex to handle when extraction finds different claims (which claims to delete?)
- ❌ May leave "orphaned" claims from previous extraction

**Option B: Replace (delete all, insert new)** ← **CHOSEN**
- ✅ Simple: DELETE WHERE paper_id, then INSERT
- ✅ Deterministic: each extraction is authoritative
- ✅ Clean state: no orphaned claims
- ✅ Idempotent: running twice yields same result
- ✅ Matches documentation intent ("replace-per-paper")

### Trade-offs Accepted:
- Claims lose `created_at` history (each extraction resets timestamps)
- No audit trail of claim changes over time
- Acceptable for Phase 1 MVP; can add versioning in future (claim_sets table)

---

## Verification Checklist (Updated)

**Phase 1 Claims Persistence:**
- [x] Database method added (`delete_claims_by_paper`)
- [x] Extraction logic updated (delete before insert)
- [x] SSE events added (persist_start, persist_done)
- [ ] **Server restarted** ← WAITING ON USER
- [ ] Duplicate claims cleaned up
- [ ] Re-verified with fresh extraction
- [ ] Idempotency tested (run extraction twice)
- [ ] SSE events visible in stream
- [ ] Logs show deleted_count and saved_count

**Once above passes:**
- [ ] Step 2: o3-mini planner verification
- [ ] Step 3: End-to-end smoke test
- [ ] Step 4: Test suite verification
- [ ] Step 5: Documentation update

---

## Code Quality Notes

### Good Practices Applied:
1. **Defensive error handling** - Extraction continues even if DB save fails
2. **Logging** - Both deleted_count and inserted_count logged
3. **SSE transparency** - User sees persistence stages in real-time
4. **Docstrings** - New method has clear documentation
5. **Type safety** - Returns int from delete method (count of deleted rows)

### Future Improvements (Phase 2+):
1. Add `claim_sets` table for versioning (track extraction history)
2. Add `content_hash` field for deduplication within extraction
3. Add `run_id` to link claims to specific extraction runs
4. Add partial index for efficient duplicate detection
5. Add GET endpoint query params (filter by dataset, metric, confidence)

---

## Session Status

**Current State:** 🟡 **PAUSED - WAITING FOR SERVER RESTART**

**Completed:**
- ✅ Verification plan created
- ✅ Server health checked
- ✅ Issue discovered (duplicate claims)
- ✅ Root cause identified (append-only logic)
- ✅ Fix implemented (replace policy + SSE events)
- ✅ Working log documented

**Waiting On:**
- ⏳ User to restart server with new code
- ⏳ Duplicate claims cleanup
- ⏳ Re-verification with new logic

**Next Actions (After Restart):**
1. Clean up duplicate claims from database
2. Re-verify claims persistence with replace policy
3. Test idempotency (run extraction twice, expect 28 claims both times)
4. Continue with Step 2 (o3-mini planner)

---

## Lessons Learned

1. **Always verify database state** - The SSE stream showed success, but database had duplicates
2. **Documentation matters** - Verification playbook explicitly mentioned "replace-per-paper" policy
3. **Test idempotency** - Running operations twice should yield same result
4. **SSE visibility** - Adding persist_start/persist_done events helps debugging
5. **User feedback critical** - User caught the issue before we moved to Step 2

---

**End of Working Log (In Progress)**
**Last Updated:** 2025-10-08 (after implementing replace policy fix)
**Next Update:** After server restart and re-verification

