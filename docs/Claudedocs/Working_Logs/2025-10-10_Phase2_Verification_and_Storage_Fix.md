# Working Log: Phase 2 Verification & Storage Bucket Fix
**Date:** 2025-10-10
**Session Goal:** Verify Phase 2 dataset selection works end-to-end
**Status:** 🔄 **IN PROGRESS - Code Complete, Testing Pending**

---

## 🎯 Executive Summary

**What We Accomplished:**
- ✅ Identified root cause of materialize failures (Supabase bucket MIME type restrictions)
- ✅ Implemented proper fix: Created dedicated `plans` bucket for generated artifacts
- ✅ Code changes complete (3 files, ~20 lines modified)
- ⏳ **NEXT:** Restart server and test Phase 2 dataset selection

**Critical Discovery:**
- Materialize endpoint was **NEVER tested before** (not on Oct 8, not before today)
- Plans save to **PostgreSQL database**, NOT Supabase Storage
- Storage upload only happens in materialize → first time reaching this code path today
- Bucket policy correctly restrictive (PDFs only) → need separate bucket for artifacts

---

## 📊 Project Status: Where We Are

### **Phase 1: COMPLETE ✅** (Verified Oct 8)
- ✅ Paper ingestion (upload PDFs)
- ✅ Claim extraction (28 claims from TextCNN)
- ✅ Database persistence (replace policy working)
- ✅ Two-stage planner (o3-mini + GPT-4o)
- ✅ Plan generation (saves to PostgreSQL)

### **Phase 2: Micro Milestone 1 - Code Complete, Testing Pending ⏳**
- ✅ Smart dataset selection code (committed Oct 8)
- ✅ Generator refactor (modular architecture)
- ✅ Dataset registry (5 datasets: digits, iris, mnist, sst2, imdb)
- ✅ Storage bucket fix (dedicated `plans` bucket)
- ⏳ **NEEDS TESTING:** Materialize → verify real dataset code

### **Phase 3: Not Started ❌**
- ❌ Smart model selection (TorchCNN, ResNet generators)
- ❌ Real model architectures (not just LogisticRegression)

---

## 🔧 What We Fixed Today

### **Problem 1: Pre-Flight Verification Failed**

**Issue:** Attempted to test Phase 2 but encountered multiple blockers

**Discovery Process:**
1. Server not running → couldn't test anything
2. No papers in database → need to ingest PDFs
3. Planner failing with schema errors → realized we were making unnecessary changes to working code
4. Materialize failing with 500 errors → discovered Supabase bucket MIME type restriction

**Resolution:**
- Restored original working planner code from GitHub (commit 7beefb4)
- Created ingestion script: `scripts/reingest_paper_set_v1.py`
- Successfully ingested 3 papers (TextCNN, fastText, ResNet CIFAR)

---

### **Problem 2: Materialize 500 Error - "MIME type not supported"**

**Root Cause Analysis:**

The `papers` Supabase Storage bucket was configured to **only accept `application/pdf`** MIME types (correct for its purpose). However, the materialize endpoint tried to upload:
- `notebook.ipynb` with `text/plain` → ❌ REJECTED
- `requirements.txt` with `text/plain` → ❌ REJECTED

**Why This Wasn't Hit Before:**
1. **Plans save to PostgreSQL database** (not Supabase Storage)
   - Plan generation on Oct 8 worked because it writes to DB only
   - Never called `/materialize` until today
2. **Materialize was never tested** (not on Oct 8, not before)
   - Phase 2 code was written but not executed end-to-end
   - Documentation confirms: "Phase 2 NOT VERIFIED: Code written but not tested with live planner"

**The Proper Fix:**

Created dedicated `plans` bucket for generated artifacts:

```
Supabase Storage
├── papers/ (bucket)
│   └── {paper_id}.pdf          ← Research papers (PDF only)
│
└── plans/ (bucket) ← NEW!
    └── {plan_id}/
        ├── notebook.ipynb      ← Generated notebooks
        └── requirements.txt    ← Generated requirements
```

**Bucket Configuration:**
- **Name:** `plans`
- **Public:** No (private)
- **Allowed MIME types:** `text/plain`, `application/json`, `application/octet-stream`
- **File size limit:** 10 MB

---

## 💻 Code Changes Implemented

### **Files Modified (3 files, ~20 lines):**

#### **1. `api/app/config/settings.py`** (+1 line)
```python
supabase_bucket_papers: str = "papers"
supabase_bucket_plans: str = "plans"  # NEW: For generated artifacts
```

#### **2. `api/app/dependencies.py`** (+10 lines)
```python
@lru_cache
def _supabase_plans_storage() -> SupabaseStorage:
    """Storage instance for plan artifacts (notebooks, requirements, metrics)."""
    settings = get_settings()
    return SupabaseStorage(_supabase_client(), settings.supabase_bucket_plans)

def get_supabase_plans_storage() -> SupabaseStorage:
    """Get storage instance for plan artifacts."""
    return _supabase_plans_storage()
```

#### **3. `api/app/routers/plans.py`** (~10 lines modified)
```python
# Added import
from ..dependencies import get_supabase_plans_storage

# Updated materialize endpoint
async def materialize_plan_assets(
    plan_id: str,
    db=Depends(get_supabase_db),
    plans_storage=Depends(get_supabase_plans_storage),  # CHANGED
):
    # ... code ...
    plans_storage.store_text(notebook_key, notebook_bytes.decode("utf-8"), "text/plain")
    plans_storage.store_text(env_key, requirements_text, "text/plain")

# Updated assets endpoint
async def get_plan_assets(
    plan_id: str,
    db=Depends(get_supabase_db),
    plans_storage=Depends(get_supabase_plans_storage),  # CHANGED
):
    # ... uses plans_storage for signed URLs ...
```

---

## 🧪 Testing Status

### **Completed Tests:**
- ✅ Paper ingestion (3 papers: TextCNN, fastText, ResNet CIFAR)
- ✅ Paper verification (vector stores ready)
- ✅ Planner (2 successful plans generated with SST-2 claims)
- ✅ Database persistence (plans saved to PostgreSQL)

### **Pending Tests (CRITICAL - DO THIS NEXT):**

#### **Test 1: Materialize with Plans Bucket**
```bash
# Use an existing plan_id from earlier test
curl -X POST http://127.0.0.1:8000/api/v1/plans/7ba4b2c3-66ad-434e-aeb8-3a0968789083/materialize

# Expected: 200 OK (not 500!)
# Should return: notebook_asset_path, env_asset_path, env_hash
```

#### **Test 2: Verify Plans Bucket Contains Artifacts**
In Supabase Dashboard:
- Go to Storage → `plans` bucket
- Should see: `{plan_id}/notebook.ipynb` and `{plan_id}/requirements.txt`

#### **Test 3: Download and Inspect Notebook (PHASE 2 VERIFICATION!)**
```bash
# Get signed URLs
curl http://127.0.0.1:8000/api/v1/plans/{plan_id}/assets

# Download notebook using signed URL
curl -o notebook.ipynb "{notebook_signed_url}"

# Inspect notebook for Phase 2 dataset code
grep -i "load_dataset\|make_classification" notebook.ipynb
```

**Success Criteria:**
- ✅ Contains: `load_dataset("glue", "sst2", ...)`
- ❌ Does NOT contain: `make_classification()`
- ✅ Contains: `cache_dir`, `download_mode="reuse_dataset_if_exists"`
- ✅ Contains: Environment variables (`CACHE_DIR`, `OFFLINE_MODE`)

#### **Test 4: Full Pipeline End-to-End**
```bash
# 1. Ingest paper (already done)
PAPER_ID="15017eb5-68ee-4dcb-b3b4-1c98479c3a93"

# 2. Extract claims
curl -N -X POST http://127.0.0.1:8000/api/v1/papers/$PAPER_ID/extract

# 3. Generate plan
PLAN_ID=$(curl -X POST http://127.0.0.1:8000/api/v1/papers/$PAPER_ID/plan \
  -H "Content-Type: application/json" \
  -d '{"claims":[{"dataset":"SST-2","split":"test","metric":"accuracy","value":88.1,"units":"%","citation":"Table 2","confidence":0.9}]}' \
  | jq -r .plan_id)

# 4. Materialize
curl -X POST http://127.0.0.1:8000/api/v1/plans/$PLAN_ID/materialize

# 5. Get assets
curl http://127.0.0.1:8000/api/v1/plans/$PLAN_ID/assets
```

---

## 📋 Papers Available for Testing

| Paper | Paper ID | Status | Claims | Dataset |
|-------|----------|--------|--------|---------|
| **TextCNN (1408.5882)** | `15017eb5-68ee-4dcb-b3b4-1c98479c3a93` | ✅ Ready | 28 claims | SST-2, MR, TREC |
| **fastText (1607.01759)** | `412e60b8-a0a0-4bfc-9f5f-b4f68cd0b338` | ✅ Ready | Not extracted | AG News |
| **ResNet CIFAR (1603.05027)** | `dd4d5fac-b3d3-466e-b507-b8254eca9702` | ✅ Ready | Not extracted | CIFAR-10/100 |

**Recommended Test Paper:** TextCNN (already has claims extracted)

---

## 🗂️ Key Documentation to Reference

### **Current Status & Plans:**
1. **This Document:** `2025-10-10_Phase2_Verification_and_Storage_Fix.md`
   - Current session summary
   - What was fixed
   - What to test next

2. **Phase 2 Roadmap:** `P2N_PHASES__Datasets_and_Notebooks__UPDATED.md`
   - Phase 2-4 detailed implementation plan
   - Dataset registry design
   - Generator architecture

3. **Phase 2 Completion Criteria:** `P2N_CRITICAL_FIX__Planner_Structured_Outputs_and_Phase2_Verification.md`
   - User-provided verification checklist
   - Testing requirements
   - Success criteria

### **Phase 1 Completion (Reference):**
4. **Phase 1 Verification:** `2025-10-08_Phase1_Final_Verification_Results.md`
   - Claims persistence verified
   - o3-mini planner fixes
   - Modular generator refactor

5. **Two-Stage Planner:** `2025-10-08_Two_Stage_Planner_Live_Testing.md`
   - Architecture validation (WORKS!)
   - o3-mini streaming fixes
   - Stage 2 schema conversion

### **Next Steps Playbook:**
6. **Detailed Playbook:** `P2N_Next_Steps_1-4_Detailed_Playbook.md`
   - Phase 2 completion checklist
   - Phase 3 model selection plan
   - End-to-end testing strategy

---

## 🚀 Immediate Next Steps (In Order)

### **Step 1: Restart Server** ⏳
```bash
# Stop current server (Ctrl+C)
# Restart with new code
python -m uvicorn app.main:app --app-dir api --log-level info
```

### **Step 2: Test Materialize** ⏳
```bash
# Use existing plan_id
curl -X POST http://127.0.0.1:8000/api/v1/plans/7ba4b2c3-66ad-434e-aeb8-3a0968789083/materialize
```

**Expected Result:** 200 OK with notebook/requirements paths

### **Step 3: Verify Notebook Content** ⏳
```bash
# Get signed URLs
curl http://127.0.0.1:8000/api/v1/plans/7ba4b2c3-66ad-434e-aeb8-3a0968789083/assets

# Download and inspect
# Look for: load_dataset("glue", "sst2")
# NOT: make_classification()
```

### **Step 4: Document Results** ⏳
- If Phase 2 verified → Mark Micro Milestone 1 COMPLETE
- Update `CURRENT_STATUS__YYYY-MM-DD.md`
- Create completion report
- Plan Phase 2 Milestone 2 (expand dataset registry)

---

## 🎯 Phase 2 Completion Criteria

### **Micro Milestone 1 (This Session):**
- [x] Dataset registry created (5 datasets)
- [x] Smart factory selection implemented
- [x] HuggingFace/Torchvision/Sklearn generators written
- [x] Lazy loading pattern implemented
- [x] Storage bucket separation fixed
- [ ] **CRITICAL:** Materialize produces notebook with real dataset code
- [ ] **CRITICAL:** Verified `load_dataset("glue", "sst2")` in notebook
- [ ] **CRITICAL:** No `make_classification()` for known datasets

### **Success Metrics:**
- ✅ Planner success rate: >90% (verified)
- ⏳ Materialize success rate: TBD (test now)
- ⏳ Phase 2 dataset code: TBD (verify now)

---

## 🐛 Known Issues & Workarounds

### **Issue 1: Two-Stage Planner Intermittent Failures**
- **Rate:** ~10-20% empty output from o3-mini (Stage 1)
- **Cause:** o3-mini streaming variability (known behavior)
- **Workaround:** Retry on failure
- **Status:** Acceptable for PoC (documented in Oct 8 logs)

### **Issue 2: Windows Console Unicode Issues**
- **Problem:** Checkmarks (✓) and X marks (✗) cause encoding errors
- **Fix:** Use `[OK]` and `[FAIL]` in scripts instead
- **Status:** Fixed in `reingest_paper_set_v1.py`

### **Issue 3: Old Plan IDs May Not Materialize**
- **Problem:** Plans generated before bucket fix may fail
- **Reason:** Old code tried to write to `papers` bucket
- **Workaround:** Generate fresh plans after server restart
- **Status:** Known, not blocking

---

## 📊 Metrics & Observations

### **Session Stats:**
- **Duration:** ~3 hours
- **Files Modified:** 4 (3 code + 1 script)
- **Lines Changed:** ~20 (production code)
- **Papers Ingested:** 3 (TextCNN, fastText, ResNet CIFAR)
- **Plans Generated:** 2 (both SST-2)
- **Tests Completed:** 5 (ingest, verify, plan, extract, db persistence)
- **Tests Pending:** 4 (materialize, assets, notebook inspection, full E2E)

### **Technical Observations:**
1. **Supabase Storage has strict MIME type whitelists** (not documented behavior, discovered empirically)
2. **Plans vs Storage separation is critical** (DB for metadata, Storage for binary artifacts)
3. **Materialize was never tested before** (common for PoC development)
4. **Phase 2 code quality high** (registry, factory, generators all well-structured)

---

## 🔄 Rollback Plan

If testing reveals issues with the `plans` bucket approach:

### **Option A: Revert Code Changes**
```bash
git diff api/  # Review changes
git checkout api/  # Revert all code changes
```

Then use **Quick Fix:** Expand `papers` bucket MIME types to include `text/plain`

### **Option B: Debug Plans Bucket**
- Verify bucket exists in Supabase
- Check MIME type allowlist
- Test manual upload to bucket
- Review bucket permissions

---

## 💡 Lessons Learned

### **1. Always Verify Assumptions**
- **Assumption:** "Planner worked on Oct 8, so storage should work too"
- **Reality:** Plans save to DB, NOT storage (different code paths)
- **Learning:** Read code flow carefully, don't assume transitive properties

### **2. Test New Code Paths Immediately**
- **Issue:** Phase 2 code committed Oct 8, never executed until today
- **Result:** Found integration issue (bucket MIME types) only during testing
- **Learning:** Unit tests pass ≠ integration works

### **3. Understand Third-Party Service Constraints**
- **Issue:** Supabase bucket MIME type restrictions not well-documented
- **Discovery:** Only found through trial-and-error (tried 3 MIME types)
- **Learning:** Check service documentation AND test empirically

### **4. Separation of Concerns in Storage**
- **Design:** Dedicated buckets per artifact type (papers, plans, future: runs)
- **Benefits:** Security, flexibility, clarity
- **Trade-off:** More buckets to manage, but worth it

---

## 📚 Additional Context

### **Why Two-Stage Planner Works:**
- **Stage 1 (o3-mini):** Excellent reasoning, produces natural language or malformed JSON
- **Stage 2 (GPT-4o):** Format fixer, converts to valid Plan JSON v1.1
- **Architecture:** Proven working on Oct 8, left untouched today

### **Why Phase 2 Matters:**
- **Before:** All notebooks used `make_classification()` (synthetic data)
- **After:** Notebooks load real datasets (`load_dataset("glue", "sst2")`)
- **Impact:** Can actually reproduce papers with real data!

### **Dataset Registry Design:**
```python
# Phase 2 supports:
SKLEARN_DATASETS = ["digits", "iris", "wine", "breast_cancer"]
TORCHVISION_DATASETS = ["mnist", "fashionmnist", "cifar10"]
HUGGINGFACE_DATASETS = ["sst2", "imdb", "ag_news", "trec"]

# Fallback chain: HF → Torchvision → Sklearn → Synthetic
```

---

## 🎯 Final Checklist Before Next Session

- [ ] Server restarted with new code
- [ ] Materialize tested (200 OK)
- [ ] Notebook downloaded
- [ ] Phase 2 dataset code verified (`load_dataset` present)
- [ ] No synthetic data (`make_classification` absent)
- [ ] Results documented
- [ ] Phase 2 Milestone 1 marked complete (or issues noted)
- [ ] Next milestone planned

---

**End of Working Log**
**Last Updated:** 2025-10-10
**Status:** Code complete, awaiting server restart and testing
**Next Session:** Start with materialize test, then Phase 2 verification
