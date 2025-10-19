# F1 Soft Sanitizer - Risk Mitigation & Testing Strategy

**Date:** 2025-10-19
**Branch:** `clean/phase2-working`
**Status:** Pre-Live Testing Review

---

## **Risk Assessment Summary**

| Risk | Severity | Likelihood | Mitigation Status | Priority |
|------|----------|------------|-------------------|----------|
| **R1: Complete Dataset Dropout** | High | Medium | ✅ Acceptable + Tests | P1 (F2) |
| **R2: No Auto-Substitution** | Medium | Low | ✅ By Design | P2 (F3) |
| **R3: Warnings Not Surfaced** | Critical | High | ⚠️ Needs UI Work | P0 |

---

## **Risk 1: Complete Dataset Dropout → Hard 422**

### **Description**
If Stage 1 mentions only unsupported datasets, sanitizer drops everything → `E_PLAN_NO_ALLOWED_DATASETS` (422).

**Example Scenario:**
```
User: Plan for paper about ImageNet classification
Stage 1: Mentions only ImageNet, ImageNet-21K
Sanitizer: Blocks both → ValueError
User: ❌ 422 error "No allowed datasets"
```

### **Current Behavior**
```python
# From sanitizer.py:94-99
if "dataset" not in pruned or not pruned.get("dataset", {}).get("name"):
    raise ValueError(
        "No allowed datasets in plan after sanitization. "
        "Add datasets to registry or adjust planner to use covered datasets."
    )
```

### **Analysis**
✅ **This is ACCEPTABLE** for MVP because:

1. **Forces visibility** - Better than silent failures or wrong substitutions
2. **Actionable error message** - Tells user exactly what to do
3. **F2 will prevent 90% of cases** - Registry-only prompts constrain Stage 1
4. **Temporary state** - Once F3 adds more datasets, issue diminishes

### **Mitigation Strategy**

#### **Short-term (Now - F1)**
- ✅ Clear error message with remediation
- ✅ Comprehensive logging for debugging
- ✅ Test coverage for this scenario

#### **Medium-term (F2 - Registry-Only Prompts)**
**Priority: P1 - Ship within 1 week**

Add to Stage 1 prompt:
```python
system_prompt += """
DATASET CONSTRAINT: Only plan for datasets present in our registry:
{registry_list}

If the paper uses datasets not in this list, explain the limitation
and recommend the closest available alternative.
"""
```

**Expected outcome:** Stage 1 won't mention blocked datasets → 0 sanitizer failures

**Test:** Zero-warnings regression test (already added in `test_planner_warnings_e2e.py`)

#### **Long-term (F3+ - Registry Expansion)**
**Priority: P2 - Ongoing**

Expand registry to cover common paper datasets:
- DBpedia-14 (smaller alternative to DBpedia)
- Tiny ImageNet (alternative to ImageNet)
- SVHN (vision dataset for DenseNet)
- CoLA, MNLI (GLUE suite)

**Test:** Track warning rate in production logs

### **Test Coverage** ✅

```python
# test_planner_warnings_e2e.py:18-46
def test_sanitizer_warnings_for_blocked_dataset():
    """Blocked dataset should generate warning."""
    # ... ImageNet plan ...
    with pytest.raises(ValueError, match="No allowed datasets"):
        sanitize_plan(raw_plan, DATASET_REGISTRY, {})
```

**Status:** ✅ 8/8 tests passing

---

## **Risk 2: No Auto-Substitution for Blocked Datasets**

### **Description**
Sanitizer warns but doesn't auto-substitute (e.g., ImageNet → CIFAR-10).

**Example:**
```
User: Plan for ImageNet classification
Sanitizer: Warns "ImageNet blocked" but doesn't auto-use CIFAR-10
User: Gets error or needs manual adjustment
```

### **Analysis**
✅ **This is CORRECT DESIGN** because:

1. **Semantic accuracy** - ImageNet (1000 classes, 224x224) ≠ CIFAR-10 (10 classes, 32x32)
2. **User trust** - Silent substitution would break trust
3. **Reproducibility** - User should know what dataset is actually used
4. **Transparency** - Better to warn and let user decide

### **Why Auto-Substitution is Dangerous**

| Auto-Substitution | Problem |
|-------------------|---------|
| ImageNet → CIFAR-10 | Wrong # classes (1000→10), wrong resolution (224→32) |
| DBpedia → AG News | Wrong domain (knowledge graph → news classification) |
| SQuAD → GLUE/STS-B | Wrong task (Q&A → sentence similarity) |

**Better approach:** Expand registry with **semantically similar** datasets

### **Mitigation Strategy**

#### **F3: Add Smaller Alternatives**
**Priority: P2 - Ship within 2 weeks**

Instead of substitution, add compatible smaller datasets:

| Blocked | Alternative (Add to Registry) | Semantic Match |
|---------|------------------------------|----------------|
| ImageNet | Tiny ImageNet (200 classes, 64x64) | ✅ Same domain |
| ImageNet | CIFAR-100 (100 classes, 32x32) | ⚠️ Smaller but similar |
| DBpedia | DBpedia-14 (14 classes, HF) | ✅ Same source |
| SQuAD | SQuAD v2 (subset) | ✅ Same task |

**Outcome:** Warnings → coverage gains naturally

#### **Future: Smart Fallback (Optional)**
If user explicitly allows fallbacks:
```python
# In request payload
{
  "claims": [...],
  "allow_fallback_datasets": true  # Opt-in
}
```

Sanitizer could suggest alternatives with warnings:
```json
{
  "warnings": [
    "ImageNet blocked. Suggested fallback: CIFAR-100 (similar domain, smaller scale)"
  ]
}
```

### **Test Coverage** ✅

```python
# test_sanitizer.py:204-228
def test_sanitize_blocked_dataset():
    """Blocked dataset should raise ValueError."""
    # ... ImageNet plan ...
    with pytest.raises(ValueError, match="No allowed datasets"):
        sanitize_plan(raw_plan, DATASET_REGISTRY, {})
```

**Status:** ✅ 31/31 sanitizer tests passing

---

## **Risk 3: Warnings Not Surfaced to UI**

### **Description**
Warnings are emitted but downstream consumers (UI, logs) don't display them clearly.

**Example:**
```
API Response: {
  "plan_id": "...",
  "warnings": ["Dataset 'ImageNet' blocked"]
}

UI: Shows plan successfully created ✅
User: Never sees warning about ImageNet
Result: Silent degradation, user confused later
```

### **Analysis**
🚨 **CRITICAL RISK** - Requires immediate action

**Why this matters:**
1. User won't understand why their plan differs from paper
2. Metrics gap might be attributed to wrong causes
3. Trust in system degrades if substitutions are invisible

### **Mitigation Strategy**

#### **Immediate (Before Live Testing)**
**Priority: P0 - MUST SHIP WITH F1**

**1. Enhanced Logging**
```python
# Already implemented in plans.py:554-558
logger.info(
    "planner.sanitize.complete warnings_count=%d dataset=%s",
    len(sanitizer_warnings),
    pruned.get("dataset", {}).get("name", "unknown")
)
```

**2. Log Warnings Individually**
Add to plans.py after sanitizer call:
```python
for warning in sanitizer_warnings:
    logger.warning(f"planner.sanitize.warning: {warning}")
```

**3. API Response Documentation**
Document in OpenAPI schema that `warnings` field is critical:
```python
class PlannerResponse(BaseModel):
    plan_id: str
    plan_version: str
    plan_json: PlanDocumentV11
    warnings: list[str] = Field(
        default_factory=list,
        description="IMPORTANT: Warnings about dataset omissions, type fixes, etc."
    )
```

#### **Short-term (UI Integration)**
**Priority: P1 - Coordinate with FE team**

**Frontend Requirements:**
1. **Display warnings prominently** in plan success response
2. **Warning badge** if `warnings.length > 0`
3. **Expandable warning panel** showing all warnings
4. **Color-code** by severity (yellow = normalization, orange = omission)

**Example UI:**
```
✅ Plan Created Successfully
⚠️ 2 Warnings - Click to view

Warnings:
  🟡 Dataset name normalized: 'SST-2' → 'sst2'
  🟠 Dataset 'ImageNet' is blocked (large/restricted) and was omitted
```

#### **Medium-term (Observability)**
**Priority: P2 - Production monitoring**

**Metrics to track:**
- `planner.warnings.total` (count per plan)
- `planner.warnings.type.{normalization|omission|defaults}` (breakdown)
- `planner.dataset.blocked.{imagenet|dbpedia|...}` (which datasets are being blocked)

**Alerts:**
- Spike in `E_PLAN_NO_ALLOWED_DATASETS` (indicates prompt drift)
- High rate of dataset omissions (indicates registry gaps)

### **Test Coverage** ✅

```python
# test_planner_warnings_e2e.py:87-151
class TestWarningLogging:
    """Test that warnings are logged properly."""

    def test_sanitizer_logs_blocked_dataset(self):
        # Verifies blocked datasets are logged

    def test_sanitizer_logs_completion(self):
        # Verifies warnings_count is logged
```

**Status:** ✅ 8/8 E2E tests passing

---

## **Testing Strategy**

### **Pre-Live Testing Checklist**

#### **Unit Tests** ✅
- [x] Sanitizer type coercion (9 tests)
- [x] Sanitizer key pruning (3 tests)
- [x] Sanitizer dataset resolution (6 tests)
- [x] Sanitizer justification extraction (5 tests)
- [x] Sanitizer full workflow (8 tests)
- [x] **Total: 31/31 passing**

#### **Integration Tests** ✅
- [x] Two-stage planner with sanitizer (5 tests)
- [x] Dataset registry updates (35 tests)
- [x] Warning propagation E2E (8 tests)
- [x] **Total: 48/48 passing**

#### **Live Testing (Manual)**
**Priority: Execute before declaring F1 complete**

| Test Case | Dataset | Expected Behavior | Pass/Fail |
|-----------|---------|-------------------|-----------|
| **T1: Happy Path** | SST-2 | Plan created, dataset=sst2, 0-1 warnings | ⏳ |
| **T2: Alias** | AG News | Plan created, dataset=agnews, warning about normalization | ⏳ |
| **T3: Blocked** | ImageNet | 422 error with clear message | ⏳ |
| **T4: Type Coercion** | (Force string numbers) | Plan validates, types fixed | ⏳ |
| **T5: Missing Defaults** | (No metrics/viz) | Warnings about defaults, plan valid | ⏳ |

**Execute via:**
```powershell
# Start server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info

# Run test cases (see testing instructions below)
```

---

## **Testing Instructions**

### **Setup**
```powershell
# 1. Start server with detailed logging
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info

# 2. Open second terminal for requests
```

### **Test Case 1: Happy Path (SST-2)**
```powershell
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan" `
  -H "Content-Type: application/json" `
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
```

**Expected Output:**
```json
{
  "plan_id": "...",
  "plan_version": "1.1",
  "plan_json": {...},
  "warnings": [
    "Dataset name normalized: 'SST-2' → 'sst2'"
  ]
}
```

**Logs to verify:**
```
planner.sanitize.start fields=[...]
sanitizer.dataset.resolved name=SST-2 canonical=sst2
planner.sanitize.complete warnings_count=1 dataset=sst2
```

### **Test Case 2: Blocked Dataset (ImageNet)**
```powershell
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan" `
  -H "Content-Type: application/json" `
  -d '{
    "claims": [{
      "dataset": "ImageNet",
      "split": "test",
      "metric": "accuracy",
      "value": 76.1,
      "units": "%",
      "citation": "Table 1",
      "confidence": 0.9
    }]
  }' | jq .
```

**Expected Output:**
```json
{
  "detail": {
    "code": "E_PLAN_NO_ALLOWED_DATASETS",
    "message": "No allowed datasets in plan after sanitization. Add datasets to registry or adjust planner to use covered datasets.",
    "remediation": "Add datasets to registry or adjust planner to use covered datasets"
  }
}
```

**Status:** 422 (expected)

**Logs to verify:**
```
sanitizer.dataset.blocked name=ImageNet normalized=imagenet
planner.sanitize.failed paper_id=... error=No allowed datasets
```

### **Test Case 3: Registry Dataset (CIFAR-10)**
```powershell
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan" `
  -H "Content-Type: application/json" `
  -d '{
    "claims": [{
      "dataset": "CIFAR-10",
      "split": "test",
      "metric": "accuracy",
      "value": 94.2,
      "units": "%",
      "citation": "Table 3",
      "confidence": 0.9
    }]
  }' | jq .
```

**Expected Output:**
```json
{
  "plan_id": "...",
  "plan_version": "1.1",
  "plan_json": {...},
  "warnings": [
    "Dataset name normalized: 'CIFAR-10' → 'cifar10'"
  ]
}
```

### **Test Case 4: Perfect Plan (Zero Warnings)**
```powershell
# Use canonical dataset name
curl -s -X POST "http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan" `
  -H "Content-Type: application/json" `
  -d '{
    "claims": [{
      "dataset": "sst2",
      "split": "test",
      "metric": "accuracy",
      "value": 88.1,
      "units": "%",
      "citation": "Table 2",
      "confidence": 0.9
    }]
  }' | jq .
```

**Expected Output:**
```json
{
  "plan_id": "...",
  "plan_version": "1.1",
  "plan_json": {...},
  "warnings": []  // ZERO warnings (F2 target)
}
```

---

## **Acceptance Criteria for F1**

### **Must Have (Blocking)**
- [x] ✅ Sanitizer handles string numbers
- [x] ✅ Sanitizer normalizes dataset names
- [x] ✅ Sanitizer blocks ImageNet/large datasets
- [x] ✅ Warnings returned in API response
- [x] ✅ Warnings logged for debugging
- [x] ✅ Unit tests: 31/31 passing
- [x] ✅ Integration tests: 48/48 passing
- [ ] ⏳ Live test: CharCNN (AG News) → PASS
- [ ] ⏳ Live test: ResNet (CIFAR-10) → PASS
- [ ] ⏳ Live test: MobileNetV2 (ImageNet) → 422 with clear error

### **Should Have (Nice-to-Have)**
- [ ] ⏳ Individual warning logging (1 log per warning)
- [ ] ⏳ OpenAPI schema documentation for warnings
- [ ] ⏳ Metrics dashboard for warning rates

### **Won't Have (Deferred to F2/F3)**
- [ ] Registry-only prompts (F2)
- [ ] Smart fallback datasets (F2)
- [ ] DBpedia-14, SVHN in registry (F3)
- [ ] UI warning display (FE team, P1)

---

## **Recommended Next Steps**

### **Before declaring F1 complete:**

1. ✅ **Run live tests** (see testing instructions above)
   - CharCNN (AG News) → should pass
   - ResNet (CIFAR-10) → should pass
   - MobileNetV2 (ImageNet) → should 422

2. ⏳ **Add individual warning logging**
   ```python
   # In plans.py after sanitizer call
   for warning in sanitizer_warnings:
       logger.warning(f"planner.sanitize.warning: {warning}")
   ```

3. ⏳ **Document warnings in API response**
   - Update OpenAPI schema with warning description
   - Add example response with warnings

4. ⏳ **Coordinate with FE team**
   - Share warning format
   - Discuss UI display strategy
   - Agree on severity levels (info/warning/error)

### **Immediate priorities after F1:**

**F2: Registry-Only Prompts** (P1 - Week 1)
- Update Stage 1 system prompt to constrain to registry
- Add regression test: assert zero warnings for registry datasets
- Target: 90% reduction in sanitizer warnings

**F3: Registry Expansion** (P2 - Week 2)
- Add DBpedia-14, SVHN, CoLA, MNLI
- Sync generators with new datasets
- Target: Cover 95% of common NLP/vision papers

**UI Integration** (P1 - Coordinate with FE)
- Warning badge in plan success response
- Expandable warning panel
- Color-coded severity

---

## **Monitoring & Observability**

### **Key Metrics to Track**

1. **Sanitizer Warnings Rate**
   - `planner.sanitize.warnings.count` (per plan)
   - **Target:** <2 warnings per plan after F2

2. **Dataset Blocking Rate**
   - `planner.dataset.blocked.{name}` (count by dataset)
   - **Alert:** Spike indicates new paper types

3. **No-Dataset Failures**
   - `planner.error.E_PLAN_NO_ALLOWED_DATASETS.count`
   - **Alert:** >10% indicates prompt drift or registry gaps

4. **Type Coercion Rate**
   - `planner.sanitize.type_coercion.count`
   - **Target:** 0 after Stage 2 is fixed

### **Dashboard Queries** (Future)

```sql
-- Warning rate by dataset
SELECT
  plan_json->>'dataset'->>'name' as dataset,
  AVG(array_length(warnings, 1)) as avg_warnings
FROM plans
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY dataset
ORDER BY avg_warnings DESC;

-- Most common warning messages
SELECT
  warning,
  COUNT(*) as count
FROM plans, unnest(warnings) as warning
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY warning
ORDER BY count DESC;
```

---

## **Status Summary**

| Area | Status | Notes |
|------|--------|-------|
| **R1: Dataset Dropout** | ✅ Mitigated | Acceptable for MVP; F2 will prevent |
| **R2: Auto-Substitution** | ✅ By Design | Registry expansion is better approach |
| **R3: Warning Surfacing** | ⚠️ In Progress | Need individual logging + UI coordination |
| **Unit Tests** | ✅ Complete | 31/31 passing |
| **Integration Tests** | ✅ Complete | 48/48 passing |
| **Live Tests** | ⏳ Pending | Ready to execute |

**Overall Risk Level:** 🟡 **MEDIUM** - Safe to proceed with live testing after adding individual warning logging

---

## **Approval for Live Testing**

**Prerequisites:**
- [x] ✅ All unit tests passing
- [x] ✅ All integration tests passing
- [x] ✅ Risk mitigation documented
- [ ] ⏳ Individual warning logging added
- [ ] ⏳ Manual test cases executed

**Recommended:**
✅ **PROCEED WITH LIVE TESTING** after adding warning logging enhancement

**Next Review:** After F2 (registry-only prompts) to validate zero-warnings target
