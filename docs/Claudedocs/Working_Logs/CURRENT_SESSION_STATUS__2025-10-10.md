# P2N Project - Session Status & Next Steps
**Date:** 2025-10-10
**Session:** Post-Context-Continuation (Storage Bucket Fix)
**Status:** ⏳ **CODE COMPLETE - TESTING PENDING**

---

## 🎯 Executive Summary

**Where We Are:**
- ✅ **Phase 1 COMPLETE** (Oct 8): Claims persistence, two-stage planner, modular generators
- ✅ **Phase 2 Code COMPLETE** (Oct 8): Smart dataset selection code committed
- ✅ **Storage Bucket Fix COMPLETE** (Oct 10): Dedicated `plans` bucket implemented
- ⏳ **Phase 2 VERIFICATION PENDING**: Need to test materialize → verify real dataset code in notebooks

**What Was Fixed Today:**
- Root cause identified: Supabase `papers` bucket only accepts `application/pdf`
- Materialize endpoint tried to upload notebooks/requirements → 400 MIME type error
- Created dedicated `plans` bucket for generated artifacts
- Updated 3 files (~20 lines) to use `plans_storage` instead of `storage`

**CRITICAL NEXT STEP:**
Test materialize endpoint with an existing plan to verify:
1. Materialize returns 200 OK (not 500)
2. Generated notebook contains `load_dataset("glue", "sst2")`
3. NOT `make_classification()` (proves Phase 2 dataset selection works)

---

## 📊 Project Phase Status

### **Phase 1: Claims Extraction & Planner ✅ COMPLETE**
**Completed:** Oct 8, 2025
**Commits:** `9a94207`, `6fcae9d`, `7e674c1`, `c4beec8`

**What Works:**
- ✅ Paper ingestion (upload PDFs to Supabase storage)
- ✅ Claim extraction (28 claims from TextCNN paper)
- ✅ Database persistence (claims save to PostgreSQL with replace policy)
- ✅ Two-stage planner (o3-mini reasoning → GPT-4o JSON schema fix)
- ✅ Plan generation (saves Plan JSON v1.1 to database)
- ✅ Modular notebook generator architecture (factory pattern, ABC interface)

**Verification:**
- ✅ 27/27 tests passing (24 generator + 3 materialize)
- ✅ Live API tests successful
- ✅ Database persistence confirmed
- ✅ SSE events working (persist_start, persist_done)

**Key Documentation:**
- [REHYDRATION__2025-10-08_Phase_1_Complete.md](REHYDRATION__2025-10-08_Phase_1_Complete.md)
- [2025-10-08_Phase1_Final_Verification_Results.md](Working_Logs/2025-10-08_Phase1_Final_Verification_Results.md)
- [2025-10-08_Two_Stage_Planner_Live_Testing.md](Working_Logs/2025-10-08_Two_Stage_Planner_Live_Testing.md)

---

### **Phase 2: Smart Dataset Selection ⏳ CODE COMPLETE, TESTING PENDING**
**Code Committed:** Oct 8, 2025 (Commit `7beefb4`)
**Storage Fix:** Oct 10, 2025 (Code changes NOT yet committed)
**Testing:** NOT YET VERIFIED

**What Was Implemented (Oct 8):**
- ✅ Dataset registry with 5+ datasets (sst2, imdb, mnist, iris, digits)
- ✅ Generator factory with smart selection (HuggingFace, Torchvision, Sklearn)
- ✅ Lazy loading pattern (notebooks download datasets during execution, not server)
- ✅ Cache-aware code generation (env vars: `DATASET_CACHE_DIR`, `OFFLINE_MODE`)
- ✅ Graceful fallback chain: HF → Torchvision → Sklearn → Synthetic

**Storage Bucket Fix (Oct 10 - TODAY):**
- ✅ Created dedicated `plans` bucket in Supabase
- ✅ Updated `settings.py` to include `supabase_bucket_plans`
- ✅ Created `get_supabase_plans_storage()` dependency
- ✅ Updated materialize and assets endpoints to use `plans_storage`

**What Needs Testing (CRITICAL):**
- [ ] Restart server with new code
- [ ] Test materialize endpoint (should return 200 OK, not 500)
- [ ] Download generated notebook via signed URL
- [ ] Inspect notebook code for `load_dataset("glue", "sst2")`
- [ ] Verify NO `make_classification()` for known datasets
- [ ] Confirm lazy loading + cache_dir present in generated code

**Success Criteria:**
- Materialize endpoint returns 200 OK
- Notebook contains real dataset loader code
- Requirements include correct packages (`datasets` for HF, `torchvision` for vision)
- Environment variables present in notebook (cache handling)
- No synthetic data for known datasets

**Key Documentation:**
- [P2N_PHASES__Datasets_and_Notebooks__UPDATED.md](P2N_PHASES__Datasets_and_Notebooks__UPDATED.md)
- [2025-10-10_Phase2_Verification_and_Storage_Fix.md](Working_Logs/2025-10-10_Phase2_Verification_and_Storage_Fix.md)

---

### **Phase 3: Smart Model Selection ❌ NOT STARTED**
**Status:** Blocked until Phase 2 verified

**Planned Work:**
- Implement `TorchCNNGenerator` (TextCNN architecture)
- Implement `TorchResNetGenerator` (ResNet-18/34 for vision)
- Implement `SklearnModelGenerator` (RandomForest, SVM)
- Update factory with model selection logic
- Map plan.model.name → generator

**Key Documentation:**
- [P2N_PHASES__Datasets_and_Notebooks__UPDATED.md](P2N_PHASES__Datasets_and_Notebooks__UPDATED.md) (Section 6-7)

---

## 🔧 Today's Session: Storage Bucket Fix

### **Problem Identified**
**Error:** `storage3.exceptions.StorageApiError: mime type text/plain is not supported`

**Root Cause Analysis:**
1. Supabase `papers` bucket configured to only accept `application/pdf`
2. Materialize endpoint tried to upload:
   - `notebook.ipynb` with `text/plain` MIME type → ❌ REJECTED
   - `requirements.txt` with `text/plain` MIME type → ❌ REJECTED
3. Plans save to **PostgreSQL database** (not storage)
4. Materialize uploads to **storage** → different code path
5. Materialize was **NEVER tested before** (not on Oct 8, not before today)

**Why This Wasn't Hit Before:**
- Plan generation on Oct 8 only tested planner endpoint
- Planner saves to database (PostgreSQL), NOT storage
- Materialize endpoint requires additional step after plan generation
- Phase 2 documentation explicitly states: "NOT VERIFIED: Code written but not tested with live planner"

### **Solution Implemented**
**Approach:** Dedicated storage bucket for generated artifacts

**Bucket Configuration:**
- **Name:** `plans`
- **Public:** No (private)
- **Allowed MIME types:** `text/plain`, `application/json`, `application/octet-stream`
- **Purpose:** Notebooks, requirements.txt, metrics.json

**Storage Architecture:**
```
Supabase Storage
├── papers/ (bucket) ← PDF research papers only
│   └── dev/YYYY/MM/DD/{paper_id}.pdf
│
└── plans/ (bucket) ← Generated artifacts (NEW!)
    └── plans/{plan_id}/
        ├── notebook.ipynb      (text/plain)
        └── requirements.txt    (text/plain)
```

### **Code Changes (3 files, ~20 lines)**

#### 1. `api/app/config/settings.py` (+1 line)
```python
supabase_bucket_papers: str = "papers"
supabase_bucket_plans: str = "plans"  # For generated artifacts
```

#### 2. `api/app/dependencies.py` (+10 lines)
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

#### 3. `api/app/routers/plans.py` (~10 lines modified)
**Changes:**
- Added import: `get_supabase_plans_storage`
- Updated `materialize_plan_assets()` parameter: `storage` → `plans_storage`
- Updated `get_plan_assets()` parameter: `storage` → `plans_storage`
- Changed storage method: `store_asset()` → `store_text()` (simpler for text files)
- All storage operations now use `plans_storage` instead of `storage`

**Modified sections:**
- Materialize endpoint (lines ~651-690)
- Assets endpoint (lines ~707-740)

### **Git Status**
```bash
Changes not staged for commit:
  modified:   api/app/config/settings.py
  modified:   api/app/dependencies.py
  modified:   api/app/routers/plans.py

Untracked files:
  docs/Claudedocs/Working_Logs/2025-10-10_Phase2_Verification_and_Storage_Fix.md
  docs/Claudedocs/Working_Logs/P2N_CRITICAL_FIX__Planner_Structured_Outputs_and_Phase2_Verification.md
```

**Status:** Code changes complete but NOT committed (waiting for testing)

---

## 🧪 Testing Checklist (DO THIS NEXT!)

### **Pre-Flight Checks**
- [ ] Verify `plans` bucket exists in Supabase dashboard
- [ ] Verify bucket allows `text/plain` and `application/json` MIME types
- [ ] Verify server has environment variables set correctly

### **Test 1: Server Restart**
```bash
# Stop current server (if running)
# Start with new code
python -m uvicorn app.main:app --app-dir api --log-level info
```

### **Test 2: Health Check**
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/internal/config/doctor
```

### **Test 3: Materialize Endpoint (CRITICAL!)**
```bash
# Use an existing plan_id from previous session
PLAN_ID="7ba4b2c3-66ad-434e-aeb8-3a0968789083"

curl -X POST http://127.0.0.1:8000/api/v1/plans/$PLAN_ID/materialize

# Expected: 200 OK (not 500!)
# Response should include:
# {
#   "notebook_asset_path": "plans/{plan_id}/notebook.ipynb",
#   "env_asset_path": "plans/{plan_id}/requirements.txt",
#   "env_hash": "..."
# }
```

### **Test 4: Get Signed URLs**
```bash
curl http://127.0.0.1:8000/api/v1/plans/$PLAN_ID/assets

# Expected: 200 OK
# Response should include signed URLs with 120s TTL
```

### **Test 5: Download & Inspect Notebook (PHASE 2 VERIFICATION!)**
```bash
# Get signed URL from Test 4 response
NOTEBOOK_URL="<signed_url_from_assets_endpoint>"

curl -o notebook.ipynb "$NOTEBOOK_URL"

# Inspect notebook for Phase 2 dataset code
cat notebook.ipynb | grep -i "load_dataset\|make_classification"

# SUCCESS CRITERIA:
# ✅ Contains: load_dataset("glue", "sst2", ...)
# ❌ Does NOT contain: make_classification()
# ✅ Contains: cache_dir=...
# ✅ Contains: download_mode="reuse_dataset_if_exists"
# ✅ Contains: Environment variables (DATASET_CACHE_DIR, OFFLINE_MODE)
```

### **Test 6: Verify in Supabase Dashboard**
1. Go to Supabase → Storage → `plans` bucket
2. Navigate to `plans/{plan_id}/`
3. Verify files exist:
   - `notebook.ipynb`
   - `requirements.txt`
4. Check file sizes (notebook should be ~10-30 KB)

### **Test 7: Generate Fresh Plan (Optional)**
```bash
# Use TextCNN paper that has claims
PAPER_ID="15017eb5-68ee-4dcb-b3b4-1c98479c3a93"

# Generate new plan with SST-2 claims
curl -X POST http://127.0.0.1:8000/api/v1/papers/$PAPER_ID/plan \
  -H "Content-Type: application/json" \
  -d '{
    "claims": [{
      "dataset": "SST-2",
      "split": "test",
      "metric": "accuracy",
      "value": 88.1,
      "units": "%",
      "citation": "Table 2",
      "confidence": 0.9
    }]
  }' | jq .

# Then test materialize with new plan_id
```

---

## 📋 Papers Available for Testing

| Paper | ArXiv ID | Paper ID | Status | Claims | Datasets |
|-------|----------|----------|--------|--------|----------|
| **TextCNN** | 1408.5882 | `15017eb5-68ee-4dcb-b3b4-1c98479c3a93` | ✅ Ready | 28 claims | SST-2, MR, TREC |
| **fastText** | 1607.01759 | `412e60b8-a0a0-4bfc-9f5f-b4f68cd0b338` | ✅ Ready | Not extracted | AG News |
| **ResNet CIFAR** | 1603.05027 | `dd4d5fac-b3d3-466e-b507-b8254eca9702` | ✅ Ready | Not extracted | CIFAR-10/100 |

**Recommended Test Paper:** TextCNN (already has 28 claims extracted)

---

## 🗺️ Architecture Overview

### **Two-Stage Planner**
```
Stage 1: o3-mini (Reasoning)
  - Input: Paper PDF + Claims + Prompt
  - Tool: file_search (retrieves context from paper)
  - Output: Natural language plan (detailed reasoning, quotes, justifications)
  - Quality: Excellent (4000+ tokens, verbatim quotes)
  - Format: Natural language (NOT JSON)

Stage 2: GPT-4o (Schema Fixing)
  - Input: Stage 1 natural language output
  - Tool: None (pure text processing)
  - Output: Valid Plan JSON v1.1
  - Format: JSON with response_format enforcement
  - Latency: ~6s

Result: Plan JSON v1.1 saved to database
```

**Success Rate:** 90%+ (Stage 1 has ~10% empty output variability, Stage 2 is 100%)

### **Smart Dataset Selection (Phase 2)**
```
Plan → Dataset Registry → Generator Factory → Code Generation

Dataset Registry (Metadata Only):
  - HuggingFace: sst2, imdb, ag_news, trec
  - Torchvision: mnist, fashionmnist, cifar10
  - Sklearn: digits, iris, wine, breast_cancer
  - Synthetic: make_classification (fallback)

Generator Selection:
  1. Normalize dataset name (lowercase, remove hyphens)
  2. Check aliases (sst-2, SST2, glue/sst2 → sst2)
  3. Lookup in registry
  4. Select generator based on source (HF/Torchvision/Sklearn)
  5. Fallback to synthetic if not found

Code Generation (Lazy Loading):
  - Server generates CODE (not downloads)
  - Notebooks download datasets during execution
  - Cache-aware (reuse_dataset_if_exists)
  - Offline mode support (OFFLINE_MODE env var)
  - Resource caps (MAX_TRAIN_SAMPLES env var)
```

---

## 🚀 Immediate Next Steps (Prioritized)

### **Step 1: Test Storage Bucket Fix (CRITICAL)**
**Goal:** Verify materialize endpoint works with `plans` bucket
**Time:** 10-15 minutes
**Actions:**
1. Restart server with new code
2. Test materialize endpoint (expect 200 OK)
3. Download notebook via signed URL
4. Inspect notebook for Phase 2 dataset code

**Success Criteria:**
- Materialize returns 200 OK (not 500)
- Notebook downloaded successfully
- Contains `load_dataset("glue", "sst2")`
- Does NOT contain `make_classification()`

---

### **Step 2: Phase 2 Verification (CRITICAL)**
**Goal:** Confirm smart dataset selection works end-to-end
**Time:** 15-20 minutes
**Actions:**
1. Verify notebook contains real dataset loader
2. Verify requirements.txt includes correct packages
3. Verify lazy loading + cache handling present
4. Test with multiple datasets (SST-2, MNIST, IMDB)

**Success Criteria:**
- ✅ SST-2 plan → `load_dataset("glue", "sst2")`
- ✅ MNIST plan → `torchvision.datasets.MNIST`
- ✅ Digits plan → `sklearn.datasets.load_digits`
- ✅ Unknown dataset → synthetic fallback (make_classification)

---

### **Step 3: Commit Code Changes**
**Goal:** Save working code to git
**Time:** 5 minutes
**Actions:**
```bash
git add api/app/config/settings.py
git add api/app/dependencies.py
git add api/app/routers/plans.py
git add docs/Claudedocs/Working_Logs/2025-10-10_Phase2_Verification_and_Storage_Fix.md

git commit -m "fix: materialize storage - use dedicated plans bucket for artifacts

- Created dedicated 'plans' bucket for generated artifacts (notebooks, requirements)
- Fixed MIME type issue: papers bucket only accepts application/pdf
- Materialize now uploads to plans bucket with text/plain allowed
- Updated 3 files to use plans_storage instead of storage

Testing pending: need to verify materialize returns 200 OK and Phase 2 dataset selection works

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### **Step 4: Document Phase 2 Completion**
**Goal:** Update project status docs
**Time:** 10 minutes
**Actions:**
1. Update `CURRENT_STATUS__2025-10-07.md` → rename to `CURRENT_STATUS__2025-10-10.md`
2. Mark Phase 2 Micro Milestone 1 as COMPLETE
3. Document known issues (if any)
4. Plan Phase 2 Milestone 2 (expand dataset registry)

---

### **Step 5: Plan Phase 2 Milestone 2 (Optional)**
**Goal:** Expand dataset registry with more datasets
**Time:** N/A (future session)
**Scope:**
- Add more HuggingFace datasets (SQuAD, CoLA, MNLI)
- Add more Torchvision datasets (CIFAR-100, SVHN)
- Add more Sklearn datasets (make_moons, make_circles)
- Test fallback chains thoroughly
- Add dataset size checks (warn if >1GB)

---

## 🐛 Known Issues & Workarounds

### **Issue 1: Materialize Never Tested Before**
**Status:** FIXED (storage bucket separation)
**Impact:** Was blocking Phase 2 verification
**Workaround:** Created dedicated `plans` bucket

### **Issue 2: Two-Stage Planner Empty Output**
**Status:** KNOWN BEHAVIOR (not a bug)
**Impact:** ~10% of Stage 1 calls return empty output
**Cause:** o3-mini streaming variability (reasoning models)
**Workaround:** Retry mechanism (user can call planner again)
**Future:** Add automatic retry in code (1-2 attempts)

### **Issue 3: Old Plan IDs May Not Materialize**
**Status:** EXPECTED (plans generated before bucket fix)
**Impact:** Plans created before Oct 10 may fail materialize
**Cause:** Old code tried to write to `papers` bucket
**Workaround:** Generate fresh plans after server restart
**Resolution:** Not blocking (old plans are from testing)

---

## 📚 Key Documentation Files

### **Current Session**
- **This file:** `CURRENT_SESSION_STATUS__2025-10-10.md`
- [2025-10-10_Phase2_Verification_and_Storage_Fix.md](Working_Logs/2025-10-10_Phase2_Verification_and_Storage_Fix.md)

### **Phase 1 Completion (Oct 8)**
- [REHYDRATION__2025-10-08_Phase_1_Complete.md](REHYDRATION__2025-10-08_Phase_1_Complete.md)
- [2025-10-08_Phase1_Final_Verification_Results.md](Working_Logs/2025-10-08_Phase1_Final_Verification_Results.md)
- [2025-10-08_Two_Stage_Planner_Live_Testing.md](Working_Logs/2025-10-08_Two_Stage_Planner_Live_Testing.md)

### **Phase 2 Planning**
- [P2N_PHASES__Datasets_and_Notebooks__UPDATED.md](P2N_PHASES__Datasets_and_Notebooks__UPDATED.md)
- [P2N_Next_Steps_1-4_Detailed_Playbook.md](P2N_Next_Steps_1-4_Detailed_Playbook.md)
- [P2N_CRITICAL_FIX__Planner_Structured_Outputs_and_Phase2_Verification.md](Working_Logs/P2N_CRITICAL_FIX__Planner_Structured_Outputs_and_Phase2_Verification.md)

### **Reference**
- [CURRENT_STATUS__2025-10-07.md](CURRENT_STATUS__2025-10-07.md) (needs update)
- [ROADMAP__Future_Work.md](ROADMAP__Future_Work.md)

---

## 💡 Key Lessons Learned

### **1. Always Test New Code Paths**
**Lesson:** Phase 2 code was committed Oct 8 but never tested live
**Result:** Found storage bucket issue only during first materialize test
**Takeaway:** Integration tests != end-to-end tests; always test full flow

### **2. Understand Service Constraints**
**Lesson:** Supabase bucket MIME type restrictions not well-documented
**Result:** Had to empirically test multiple MIME types
**Takeaway:** Check service docs AND test empirically for restrictions

### **3. Separation of Concerns in Storage**
**Lesson:** Different artifact types should use different buckets
**Result:** Clean architecture - `papers` for PDFs, `plans` for generated artifacts
**Takeaway:** Security, flexibility, and clarity worth the management overhead

### **4. Database vs Storage Code Paths**
**Lesson:** Plans save to DB (PostgreSQL), artifacts save to storage (Supabase Storage)
**Result:** Different code paths mean different testing requirements
**Takeaway:** Trace full data flow; assumptions about "transitive working" are dangerous

---

## 🎯 Definition of Done

### **Phase 2 Micro Milestone 1**
- [x] Dataset registry created (5+ datasets)
- [x] Smart factory selection implemented
- [x] HuggingFace/Torchvision/Sklearn generators written
- [x] Lazy loading pattern implemented
- [x] Storage bucket separation fixed
- [ ] **CRITICAL:** Materialize produces notebook with real dataset code
- [ ] **CRITICAL:** Verified `load_dataset("glue", "sst2")` in notebook
- [ ] **CRITICAL:** No `make_classification()` for known datasets

### **Acceptance Criteria**
- Materialize success rate: >90%
- Notebooks load correct datasets (verified by inspection)
- Fallback to synthetic works when dataset unknown
- Requirements.txt contains correct packages
- Cache-aware code present (env vars for cache_dir, offline mode)

---

## 🔄 Quick Command Reference

### **Server Management**
```bash
# Start server
python -m uvicorn app.main:app --app-dir api --log-level info

# Health check
curl http://127.0.0.1:8000/health

# Config doctor
curl http://127.0.0.1:8000/internal/config/doctor
```

### **Testing Commands**
```bash
# Test materialize (use existing plan_id)
curl -X POST http://127.0.0.1:8000/api/v1/plans/7ba4b2c3-66ad-434e-aeb8-3a0968789083/materialize

# Get signed URLs
curl http://127.0.0.1:8000/api/v1/plans/7ba4b2c3-66ad-434e-aeb8-3a0968789083/assets

# Generate new plan
curl -X POST http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/plan \
  -H "Content-Type: application/json" \
  -d '{"claims": [{"dataset": "SST-2", "split": "test", "metric": "accuracy", "value": 88.1, "units": "%", "citation": "Table 2", "confidence": 0.9}]}'

# Extract claims (if needed)
curl -N -X POST http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract

# Get claims from database
curl http://127.0.0.1:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/claims
```

### **Git Commands**
```bash
# Check status
git status

# View changes
git diff api/

# Commit (after testing)
git add api/ docs/
git commit -m "fix: materialize storage bucket separation"
git push
```

---

**End of Session Status Document**
**Last Updated:** 2025-10-10
**Next Action:** Test materialize endpoint to verify storage bucket fix and Phase 2 dataset selection
