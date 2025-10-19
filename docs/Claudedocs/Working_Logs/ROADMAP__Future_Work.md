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

### **4. Real Notebook Generation (C-NOTEBOOK-01)** 🔥 **CRITICAL PRIORITY**
**Status:** Currently generates 100% fake notebooks - **BLOCKING ALL MEANINGFUL TESTING**
**Why Critical:** Cannot reproduce real papers, all current runs produce meaningless results

#### **The Problem**

**Current Implementation ([notebook.py](../../../api/app/materialize/notebook.py)):**
- ❌ **Always generates synthetic data** via `make_classification()` regardless of plan.dataset.name
- ❌ **Always uses LogisticRegression** regardless of plan.model.name
- ❌ **Ignores plan.config.framework** completely (never uses PyTorch even if specified)
- ❌ **No connection to paper claims** - gap analysis will be meaningless
- ✅ Seeds are deterministic (good foundation)
- ✅ Writes required artifacts (metrics.json, events.jsonl)

**Impact:**
```python
# Plan says: dataset="SST-2", model="TextCNN", framework="torch"
# Notebook generates: make_classification() + LogisticRegression()
# Result: Completely useless for reproduction!
```

**This blocks:**
- ⏸️ End-to-end testing with real papers
- ⏸️ Sandbox executor (no point sandboxing fake code)
- ⏸️ Gap analysis (comparing fake results to real claims)
- ⏸️ Demos (can't show real paper reproduction)

---

#### **Modular Architecture Design**

**Component Structure:**
```
api/app/materialize/
├── notebook.py (orchestrator)
└── generators/ (NEW - modular components)
    ├── __init__.py
    ├── base.py (CodeGenerator ABC)
    ├── factory.py (smart selection logic)
    ├── dataset.py (dataset generators)
    │   ├── SyntheticDatasetGenerator
    │   ├── SklearnDatasetGenerator (digits, iris, wine)
    │   ├── TorchvisionDatasetGenerator (MNIST, CIFAR10)
    │   └── HuggingFaceDatasetGenerator (SST-2, IMDB)
    ├── model.py (model generators)
    │   ├── SklearnModelGenerator (LogReg, RandomForest, SVM)
    │   ├── TorchCNNGenerator (TextCNN-style)
    │   └── TorchResNetGenerator (ResNet-18/50/152)
    └── training.py (training loop generators)
```

**Design Principles:**
1. **Modular** - Each generator does ONE thing
2. **Extensible** - Add new datasets/models without touching existing code
3. **Testable** - Test each generator independently
4. **Docker-ready** - All generators produce pure Python code (no state)
5. **Fallback chains** - If advanced fails, fall back to simpler: HuggingFace → torchvision → sklearn → synthetic

---

#### **Implementation Plan: 4 Phases (4 Weeks)**

### **Phase 1: Refactor to Modular (Week 1)**
**Goal:** Make code modular WITHOUT changing behavior yet

**Tasks:**
- [ ] Create `generators/` package structure
- [ ] Define `CodeGenerator` ABC with methods: `generate_imports()`, `generate_code()`, `generate_requirements()`
- [ ] Extract current logic into `SyntheticDatasetGenerator` (unchanged)
- [ ] Extract current logic into `SklearnLogisticGenerator` (unchanged)
- [ ] Create `GeneratorFactory` with selection logic (returns synthetic/logistic for now)
- [ ] Update `notebook.py` to use factory pattern
- [ ] **Test:** All existing tests pass, output identical to before

**Files to Create:**
```
api/app/materialize/generators/__init__.py
api/app/materialize/generators/base.py
api/app/materialize/generators/dataset.py
api/app/materialize/generators/model.py
api/app/materialize/generators/factory.py
```

**Example Generator:**
```python
# generators/dataset.py
class SyntheticDatasetGenerator(CodeGenerator):
    def generate_imports(self, plan):
        return [
            "from sklearn.datasets import make_classification",
            "from sklearn.model_selection import train_test_split",
        ]

    def generate_code(self, plan):
        return textwrap.dedent(f"""
        X, y = make_classification(
            n_samples=512, n_features=32, random_state=SEED
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=SEED
        )
        """).strip()

    def generate_requirements(self, plan):
        return ["scikit-learn==1.5.1"]
```

**Success Criteria:**
- ✅ Code is modular (separate files)
- ✅ All tests pass
- ✅ Generated notebooks identical to before

---

### **Phase 2: Smart Dataset Selection (Week 2)**
**Goal:** Generate code that loads the RIGHT dataset based on plan

**Dataset Registry:**
```python
SKLEARN_DATASETS = {
    "digits": "load_digits",
    "iris": "load_iris",
    "wine": "load_wine",
    "breast_cancer": "load_breast_cancer"
}

TORCHVISION_DATASETS = {
    "mnist": "MNIST",
    "cifar10": "CIFAR10",
    "cifar100": "CIFAR100",
    "fashionmnist": "FashionMNIST"
}

HUGGINGFACE_DATASETS = {
    "sst2": ("glue", "sst2"),
    "sst-2": ("glue", "sst2"),
    "mrpc": ("glue", "mrpc"),
    "imdb": ("imdb",),
    "squad": ("squad",)
}
```

**Tasks:**
- [ ] Implement `SklearnDatasetGenerator` (3+ datasets)
- [ ] Implement `TorchvisionDatasetGenerator` (MNIST, CIFAR10)
- [ ] Implement `HuggingFaceDatasetGenerator` (SST-2, IMDB)
- [ ] Update factory with smart selection logic
- [ ] Add fallback chain: HF → torchvision → sklearn → synthetic
- [ ] **Test:** Generate notebooks for each dataset type
- [ ] **Integration:** TextCNN paper → extract → plan → materialize → verify SST-2 dataset code

**Example - Torchvision Generator:**
```python
class TorchvisionDatasetGenerator(CodeGenerator):
    def generate_code(self, plan):
        return textwrap.dedent(f"""
        from torchvision import datasets, transforms

        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.5,), (0.5,))
        ])

        train_dataset = datasets.MNIST(
            root='./data', train=True, download=True, transform=transform
        )

        # Flatten for sklearn compatibility
        X_train = train_dataset.data.numpy().reshape(len(train_dataset), -1)
        y_train = np.array(train_dataset.targets)
        """).strip()
```

**Success Criteria:**
- ✅ Can generate code for 3+ sklearn datasets
- ✅ Can generate code for 2+ torchvision datasets
- ✅ Can generate code for 2+ HuggingFace datasets
- ✅ TextCNN plan materializes with real SST-2 loading code
- ✅ Falls back to synthetic for unknown datasets

---

### **Phase 3: Smart Model Selection (Week 3)**
**Goal:** Generate code that builds the RIGHT model based on plan

**Model Registry:**
```python
SKLEARN_MODELS = {
    "logistic": "LogisticRegression",
    "random_forest": "RandomForestClassifier",
    "svm": "SVC",
    "knn": "KNeighborsClassifier"
}

TORCH_CNN_VARIANTS = {
    "textcnn": "TextCNN",
    "cnn": "SimpleCNN"
}

TORCH_ARCHITECTURES = {
    "resnet18": ("torchvision.models", "resnet18"),
    "resnet50": ("torchvision.models", "resnet50")
}
```

**Tasks:**
- [ ] Implement `SklearnModelGenerator` (LogReg, RandomForest, SVM)
- [ ] Implement `TorchCNNGenerator` (simple CNN for text classification)
- [ ] Implement `TorchResNetGenerator` (ResNet variants)
- [ ] Update factory with model selection logic
- [ ] Map plan.config hyperparams to model params (epochs → max_iter, lr, etc.)
- [ ] **Test:** Generate notebooks for each model type
- [ ] **Integration:** ResNet paper → extract → plan → materialize → verify ResNet model code

**Example - PyTorch CNN Generator:**
```python
class TorchCNNGenerator(CodeGenerator):
    def generate_code(self, plan):
        epochs = plan.config.epochs or 10
        lr = plan.config.learning_rate or 0.001

        return textwrap.dedent(f"""
        import torch.nn as nn
        import torch.optim as optim

        class SimpleCNN(nn.Module):
            def __init__(self, input_dim, num_classes):
                super().__init__()
                self.conv1 = nn.Conv1d(1, 64, kernel_size=3)
                self.relu = nn.ReLU()
                self.pool = nn.MaxPool1d(kernel_size=2)
                self.fc = nn.Linear(64 * (input_dim // 2), num_classes)

            def forward(self, x):
                x = x.unsqueeze(1)
                x = self.conv1(x)
                x = self.relu(x)
                x = self.pool(x)
                x = x.view(x.size(0), -1)
                return self.fc(x)

        model = SimpleCNN(X_train.shape[1], len(set(y_train)))
        optimizer = optim.Adam(model.parameters(), lr={lr})
        # ... training loop ...
        """).strip()
```

**Success Criteria:**
- ✅ Can generate code for 3+ sklearn models
- ✅ Can generate code for PyTorch CNN
- ✅ Can generate code for ResNet variants
- ✅ ResNet plan materializes with real ResNet architecture
- ✅ Hyperparameters from plan.config mapped correctly

---

### **Phase 4: Docker-Ready Preparation (Week 4)**
**Goal:** Ensure all generators produce Docker-compatible code

**Docker-Ready Patterns:**

1. **Relative Paths Only:**
```python
# GOOD
data_path = Path("./data")
model_path = Path("./models/checkpoint.pt")

# BAD (breaks in Docker)
data_path = Path("/home/user/data")
```

2. **Environment Variable Support:**
```python
# In setup cell:
OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "false") == "true"
MAX_MEMORY_GB = float(os.environ.get("MAX_MEMORY_GB", "2.0"))

if OFFLINE_MODE:
    datasets.MNIST(root='./data', download=False)  # Use cache only
else:
    datasets.MNIST(root='./data', download=True)
```

3. **Resource Awareness:**
```python
import psutil
available_mem = psutil.virtual_memory().available / (1024**3)
if available_mem < MAX_MEMORY_GB * 0.8:
    raise MemoryError(f"Insufficient memory: {available_mem:.1f}GB")
```

**Tasks:**
- [ ] Add environment variable support to all generators
- [ ] Add resource checks to setup cell generation
- [ ] Add offline mode support for datasets
- [ ] Ensure all paths are relative
- [ ] Create `Dockerfile` for notebook executor (prep for C-RUN-01)
- [ ] **Test:** Run generated notebooks in Docker container
- [ ] **Test:** Run with OFFLINE_MODE=true (cached datasets only)

**Files to Modify:**
- All generator classes (add env var support)
- `notebook.py` (enhance setup cell with env checks)

**Success Criteria:**
- ✅ All generated notebooks run in Docker
- ✅ No hardcoded absolute paths
- ✅ Environment variables control behavior
- ✅ Resource limits enforced
- ✅ Offline mode works (no downloads if cached)

---

#### **Testing Strategy**

**Unit Tests:**
```python
# test_dataset_generators.py
def test_sklearn_digits_dataset():
    plan = create_test_plan(dataset_name="digits")
    gen = GeneratorFactory.get_dataset_generator(plan)

    assert isinstance(gen, SklearnDatasetGenerator)
    code = gen.generate_code(plan)
    assert "load_digits()" in code
    assert "SEED" in code  # Determinism

def test_mnist_dataset():
    plan = create_test_plan(dataset_name="mnist")
    gen = GeneratorFactory.get_dataset_generator(plan)

    assert isinstance(gen, TorchvisionDatasetGenerator)
    code = gen.generate_code(plan)
    assert "datasets.MNIST" in code
```

**Integration Tests:**
```python
# test_real_papers.py
def test_textcnn_paper_end_to_end():
    # 1. Extract claims from TextCNN paper
    claims = extract_paper("1408.5882.pdf")

    # 2. Generate plan
    plan = generate_plan(claims)
    assert plan.dataset.name.lower() in ["sst2", "sst-2"]
    assert "cnn" in plan.model.name.lower()

    # 3. Materialize notebook
    notebook_bytes = materialize_plan(plan)

    # 4. Verify generated code
    notebook = nbformat.reads(notebook_bytes)
    code = "\n".join([cell.source for cell in notebook.cells])
    assert "glue" in code or "sst2" in code  # HuggingFace dataset
    assert "Conv" in code  # CNN architecture

    # 5. Execute notebook
    result = execute_notebook(notebook_bytes)
    assert result.metrics_text  # Produced metrics.json
```

---

#### **Week-by-Week Roadmap**

**Week 1: Foundation**
- Mon-Tue: Create package structure, define ABCs
- Wed-Thu: Extract current logic into generators
- Fri: Update notebook.py, run tests
- **Deliverable:** Modular codebase, all tests pass

**Week 2: Datasets**
- Mon: Implement sklearn generator
- Tue: Implement torchvision generator
- Wed: Implement HuggingFace generator
- Thu: Update factory, add fallback logic
- Fri: Integration test with TextCNN paper
- **Deliverable:** Real dataset loading works

**Week 3: Models**
- Mon: Implement enhanced sklearn models
- Tue: Implement PyTorch CNN
- Wed: Implement ResNet generator
- Thu: Update factory, map hyperparameters
- Fri: Integration test with ResNet paper
- **Deliverable:** Real model architectures work

**Week 4: Docker Prep**
- Mon-Tue: Add env var support to all generators
- Wed: Add resource checks, offline mode
- Thu: Create Dockerfile, test in container
- Fri: Documentation, final integration tests
- **Deliverable:** Docker-ready notebooks

---

#### **Success Metrics**

**Phase 1 Complete When:**
- ✅ Code is modular (generators in separate files)
- ✅ All existing tests pass
- ✅ Generated notebooks identical to before (no regression)

**Phase 2 Complete When:**
- ✅ TextCNN paper → plan → materialize → shows `load_dataset("glue", "sst2")` in code
- ✅ Can generate 3+ sklearn, 2+ torchvision, 2+ HF datasets
- ✅ Unknown datasets fall back to synthetic gracefully

**Phase 3 Complete When:**
- ✅ ResNet paper → plan → materialize → shows `resnet50()` in code
- ✅ Can generate 3+ sklearn models, PyTorch CNN, ResNet
- ✅ plan.config.epochs/lr mapped to model params

**Phase 4 Complete When:**
- ✅ All notebooks run in Docker container
- ✅ `OFFLINE_MODE=true` works (no downloads)
- ✅ Resource checks prevent OOM errors
- ✅ Dockerfile ready for C-RUN-01

---

#### **Immediate First Steps (This Week)**

```bash
# 1. Create folder structure
mkdir -p api/app/materialize/generators
touch api/app/materialize/generators/{__init__,base,dataset,model,factory}.py

# 2. Define base CodeGenerator ABC (generators/base.py)
# 3. Extract current logic into SyntheticDatasetGenerator
# 4. Create GeneratorFactory (returns synthetic for now)
# 5. Update notebook.py to use factory
# 6. Run tests: pytest api/tests/test_plans_materialize.py
```

**Estimated Time:** 2-3 days for Phase 1 refactor

---

#### **Why This is #1 Priority**

**Current State:**
- ✅ Extraction works (Session 4 fix)
- ✅ Database ready (Schema v1)
- ✅ Plan generation works
- ❌ **Notebooks are 100% fake** ← BLOCKING ISSUE

**What This Unblocks:**
- ✅ End-to-end testing with real papers
- ✅ Meaningful sandbox executor (C-RUN-01)
- ✅ Accurate gap analysis (C-REPORT-01)
- ✅ Demo-ready system (show real reproduction)

**Priority Order:**
1. Complete extraction integration (claims to DB) - 2 days
2. End-to-end pipeline testing - 3 days
3. Improve extraction quality - 1 week
4. **🔥 Real Notebook Generation (THIS)** - 4 weeks ← CRITICAL PATH
5. Real Sandbox Executor - 2 weeks (depends on #4)
6. Gap Analysis - 1 week (depends on #5)

---

## 🚀 Near-Term Features (Next 2-4 Weeks)

### **5. Real Sandbox Executor (C-RUN-01)**
**Prerequisites:** ✅ C-NOTEBOOK-01 complete (need real notebooks first)
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

### **6. Gap Analysis & Reporting (C-REPORT-01)**
**Prerequisites:** ✅ C-RUN-01 complete (need real run results first)
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

### **7. Kid-Mode Storybook Integration (C-KID-01)**
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

### **8. Multi-Tenancy & Security**
**Status:** RLS disabled for MVP, schema supports `created_by` fields

**Tasks:**
- [ ] Enable RLS policies on all tables
- [ ] Implement user authentication (Supabase Auth)
- [ ] Add `created_by` enforcement in application layer
- [ ] Test isolation between users
- [ ] Add admin role for cross-user access

---

### **9. Web UI (Basic MVP)**
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

### **10. Planner Enhancements**
**Status:** Working but can be smarter

**Improvements:**
- [ ] Auto-detect dataset availability (HuggingFace, TensorFlow Datasets)
- [ ] Model architecture search (suggest similar models if original unavailable)
- [ ] Dependency resolution (auto-generate requirements.txt from plan)
- [ ] Cost estimation (compute time, dataset size)
- [ ] Feasibility scoring (0-1 likelihood of success)

---

### **11. Observability & Monitoring**
**Status:** Basic tracing exists, needs expansion

**Tasks:**
- [ ] Add Sentry for error tracking
- [ ] Create dashboard for run success rates
- [ ] Monitor File Search usage (cost tracking)
- [ ] Alert on failed extractions/runs
- [ ] Add performance metrics (extraction time, run duration)

---

## 🔮 Long-Term Vision (3-6 Months)

### **12. Multi-Paper Reproduction**
Compare reproduction quality across papers:
- Leaderboard of most reproducible papers
- Identify common failure patterns
- Build dataset of reproduction results

### **13. Citation Network Analysis**
- Extract paper citations from PDFs
- Build dependency graph (Paper A cites Paper B)
- Reproduce entire citation chains
- Quantify reproducibility debt

### **14. Automated Paper Discovery**
- Scrape arXiv for new papers
- Auto-ingest papers with code availability
- Pre-extract claims for quick browsing
- Alert on papers in specific domains

### **15. Collaborative Features**
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
