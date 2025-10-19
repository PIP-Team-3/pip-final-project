# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

**P2N (Paper-to-Notebook)** transforms research paper PDFs into reproducible experiments. The system extracts experimental claims, generates reproduction plans, creates executable notebooks, and runs them in a sandboxed environment.

**Current State:** Phase 2 Complete (Smart Dataset Selection verified Oct 2025)
- ✅ Phase 1: Claims extraction, two-stage planner, modular generators
- ✅ Phase 2: Smart dataset selection (HuggingFace, Torchvision, Sklearn generators)
- ⏳ Phase 3: Smart model selection (planned)

**Tech Stack:** FastAPI + OpenAI Agents SDK (Responses API) + Supabase (PostgreSQL + Storage)

---

## Critical Architecture Patterns

### Two-Stage Planner Architecture
The planner uses a **two-stage design** to get best-of-both-worlds:
- **Stage 1 (o3-mini):** Produces detailed natural language reasoning with verbatim paper quotes
- **Stage 2 (GPT-4o):** Converts natural language → valid Plan JSON v1.1 schema

**Why:** o3-mini excels at reasoning but doesn't enforce JSON schemas. GPT-4o enforces schemas but has weaker reasoning. The two-stage approach combines both strengths.

**Code:** `api/app/routers/plans.py`
- Lines 83-184: `_fix_plan_schema()` (Stage 2 conversion)
- Lines 190-430: `create_plan()` (Stage 1 execution + Stage 2 call)

**Important:** DO NOT try to make o3-mini produce JSON directly. It will fail ~80% of the time.

### Agent System (Thin Agents, Thick Tools)
Agents produce **structured outputs only**, never arbitrary code. The backend validates and executes.

**5 Agents Defined** (in `api/app/agents/definitions.py`):
1. **EXTRACTOR** ✅ - Extract claims from papers (uses File Search)
2. **PLANNER** ✅ - Generate reproduction plans (two-stage: o3-mini + GPT-4o)
3. **ENV_SPEC** ⏳ - Environment spec builder (defined, not yet called)
4. **CODEGEN_DESIGN** ⏳ - Notebook designer (defined, not yet called)
5. **KID_EXPLAINER** ⏳ - Kid-friendly explanations (defined, not yet called)

**Currently Active:** Only EXTRACTOR and PLANNER are in use. Others are infrastructure for future phases.

### Code Generation: Generators NOT Agents
**CRITICAL:** Notebook code is generated via **deterministic generators**, NOT LLM agents.

**Why:**
- Generators produce proven, working code every time
- LLM code generation is non-deterministic and can produce broken code
- Generators are testable with unit tests

**Code:** `api/app/materialize/generators/`
- `factory.py` - Smart selection logic (dataset registry lookup → generator)
- `dataset.py` - HuggingFace, Torchvision, Sklearn, Synthetic generators
- `model.py` - Model generators (currently only SklearnLogistic, Phase 3 adds more)

**Phase 2 Success (Oct 2025):** Smart dataset selection verified working:
- SST-2 → `load_dataset("glue", "sst2")` ✅
- MNIST → `torchvision.datasets.MNIST` ✅
- Unknown datasets → synthetic fallback ✅

---

## Development Commands

### Environment Setup
```bash
# Install dependencies (Python 3.12.5)
pip install -r api/requirements-dev.txt

# Create .env from .env.example
# Must set: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# Load environment (PowerShell)
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }
```

### Running the API Server
```bash
# Method 1: Via manage.py (auto-loads .env)
python manage.py start

# Method 2: Direct uvicorn (manual env loading)
python -m uvicorn app.main:app --app-dir api --log-level info
```

### Testing
```bash
# Run all tests
.venv/Scripts/python.exe -m pytest -q

# Run specific test file
pytest api/tests/test_papers_extract.py -v

# Run single test
pytest api/tests/test_generators.py::test_huggingface_generator -v

# Key test suites:
# - test_generators.py (24 tests) - Phase 2 dataset generators
# - test_plans_materialize.py (3 tests) - Notebook generation
# - test_two_stage_planner.py (4 tests) - Two-stage planner with mocks
# - test_papers_extract.py - Extractor agent with File Search
# - test_papers_ingest.py - Paper upload + vector store creation
```

### Common Tasks (manage.py)
```bash
python manage.py models              # Show current model config
python manage.py set-planner o3-mini # Set planner to o3-mini
python manage.py health              # Check API health
python manage.py list                # List ingested papers
python manage.py extract <paper_id>  # Extract claims
python manage.py plan <paper_id>     # Generate plan
```

---

## Key File Locations

### Core Pipeline
- `api/app/routers/papers.py` - Paper ingestion + claim extraction (EXTRACTOR agent)
- `api/app/routers/plans.py` - Plan generation + materialize (PLANNER agent, two-stage)
- `api/app/routers/runs.py` - Notebook execution (ready for Phase 3+)

### Agent System
- `api/app/agents/definitions.py` - All 5 agent definitions (2 active, 3 future)
- `api/app/agents/base.py` - Agent registry, guardrails framework
- `api/app/agents/runtime.py` - Tool building (hosted + function tools)

### Code Generators (Phase 2)
- `api/app/materialize/generators/factory.py` - Smart generator selection
- `api/app/materialize/generators/dataset.py` - 4 dataset generators
- `api/app/materialize/generators/dataset_registry.py` - Dataset metadata (5+ datasets)
- `api/app/materialize/generators/model.py` - Model generators (Phase 3 expands this)
- `api/app/materialize/notebook.py` - Notebook orchestrator

### Data Layer
- `api/app/data/supabase.py` - Database + Storage abstraction
- `api/app/data/models.py` - Pydantic models for DB records
- `api/app/dependencies.py` - FastAPI dependency injection

### Configuration
- `api/app/config/settings.py` - Environment variables
- `api/app/config/llm.py` - OpenAI client, tracing, agent defaults

---

## Critical Constraints & Gotchas

### OpenAI SDK Version Lock
**CRITICAL:** Must use `openai==1.109.1` and `openai-agents==0.3.3`
- DO NOT upgrade without explicit migration prompt
- Two-stage planner depends on specific SDK behaviors
- Responses API vs Chat Completions API differences matter

### Supabase Storage Buckets
**Two separate buckets with different MIME type restrictions:**
- `papers` bucket: Only accepts `application/pdf` (for paper PDFs)
- `plans` bucket: Accepts `text/plain`, `application/json` (for notebooks, requirements)

**Bug Fixed Oct 2025:** Materialize was trying to upload notebooks to `papers` bucket → 400 MIME error. Now uses dedicated `plans` bucket.

**Code locations:**
- `api/app/config/settings.py` - Bucket names
- `api/app/dependencies.py` - `get_supabase_plans_storage()` dependency
- `api/app/routers/plans.py` - Materialize uses `plans_storage`, not `storage`

### Database Schema ("No-Rules v0")
**Current posture:** Tables have `PRIMARY KEY(id)` ONLY. No foreign keys, no defaults, no RLS.
- Application must supply every value explicitly (including timestamps, UUIDs)
- Schema v1 deployed (`sql/schema_v1_nuclear_with_grants.sql`)
- DO NOT add constraints without explicit schema migration prompt

### Streaming & Event Handling
**o3-mini streaming is unreliable:**
- Stream deltas (`response.output_text.delta`) are reliable
- Completion events (`response.completed`) are NOT reliable (~10-20% missing)
- **Pattern:** Collect deltas in array, use as fallback if `get_final_response()` throws RuntimeError

**Code:** `api/app/routers/plans.py` lines 326-399

### Token Limits by Model
**o3-mini needs higher limits than other models:**
- o3-mini: 8192 tokens (produces detailed reasoning)
- Other models: 4096 tokens (default)

**Code:** `api/app/routers/plans.py` line 313 (conditional token limit)

---

## Testing Strategy

### What to Test
1. **Agent outputs:** Verify structured output matches Pydantic schemas
2. **Guardrails:** Test input/output guardrails trigger correctly
3. **Generators:** Test each dataset/model generator independently
4. **Storage paths:** Verify correct bucket usage (papers vs plans)
5. **Two-stage planner:** Test Stage 1 → Stage 2 conversion

### Mock vs Integration
- **Unit tests:** Mock OpenAI responses (fast, no API cost)
- **Integration tests:** Use real API (slow, costs money, more realistic)
- **Current:** Mostly unit tests with mocks, some integration tests for critical paths

### Running Tests Against Live API
```bash
# Ensure server is running first
python manage.py start

# In another terminal:
curl -X POST http://127.0.0.1:8000/api/v1/papers/ingest \
  -F "title=Test Paper" \
  -F "file=@path/to/paper.pdf"
```

---

## Phase Roadmap Context

### Phase 1 (COMPLETE - Oct 8, 2025)
- ✅ Claims extraction with database persistence
- ✅ Two-stage planner (o3-mini + GPT-4o)
- ✅ Modular generator refactor (ABC interface, factory pattern)

### Phase 2 (COMPLETE - Oct 10, 2025)
- ✅ Smart dataset selection (registry lookup → generator)
- ✅ Lazy loading pattern (notebooks download datasets, not server)
- ✅ Graceful fallback chain (HuggingFace → Torchvision → Sklearn → Synthetic)
- ✅ Storage bucket separation (papers vs plans)
- **Verified:** Notebooks generate `load_dataset("glue", "sst2")` NOT `make_classification()`

### Phase 3 (NEXT - Planned)
- ⏳ Smart model selection (expand `factory.py::get_model_generator()`)
- ⏳ TorchCNNGenerator (TextCNN architecture)
- ⏳ TorchResNetGenerator (ResNet-18/34)
- ⏳ SklearnModelGenerator (RandomForest, SVM)

### Future Phases
- Phase 4: Docker sandbox executor (replace stub in `api/app/run/runner_local.py`)
- Phase 5: Gap analysis & reporting
- Phase 6: Kid-mode explanations (storyboard generation)

---

## Working with Existing Code

### When Adding New Datasets
1. Add entry to `api/app/materialize/generators/dataset_registry.py`
2. Generator auto-selected by `factory.py` based on `source` field
3. Add test to `api/tests/test_dataset_registry.py`

### When Adding New Models (Phase 3)
1. Create generator class in `api/app/materialize/generators/model.py`
2. Update `factory.py::get_model_generator()` with selection logic
3. Add test to `api/tests/test_generators.py`

### When Adding New Agents
1. Define in `api/app/agents/definitions.py`
2. Register in `_register_agents()`
3. Add Pydantic output type to `api/app/agents/types.py`
4. Add guardrails (input + output)
5. Call agent in appropriate router

### When Modifying Two-Stage Planner
- **DO NOT** try to make o3-mini produce JSON directly
- **DO NOT** remove Stage 2 (GPT-4o schema fixing)
- **DO** update Stage 2 prompt if schema changes (lines 116-157 in plans.py)
- **DO** test with real papers, not just mocks

---

## Documentation Hierarchy

**Start Here:**
- `README.md` - Project overview, setup, basic usage
- `AGENTS_detailed.md` - Agent architecture, roles, contracts
- This file (`CLAUDE.md`) - Development guide

**Phase Documentation:**
- `docs/Claudedocs/CURRENT_SESSION_STATUS__2025-10-10.md` - Current state (Phase 2 complete)
- `docs/Claudedocs/P2N_PHASES__Datasets_and_Notebooks__UPDATED.md` - Phase 2-4 roadmap
- `docs/Claudedocs/REHYDRATION__2025-10-08_Phase_1_Complete.md` - Phase 1 completion

**Working Logs:**
- `docs/Claudedocs/Working_Logs/2025-10-10_Phase2_Verification_and_Storage_Fix.md` - Latest session
- `docs/Claudedocs/Working_Logs/2025-10-08_Two_Stage_Planner_Live_Testing.md` - Two-stage planner testing

**Database:**
- `sql/schema_v1_nuclear_with_grants.sql` - Current production schema
- `sql/README.md` - Schema documentation

---

## Quick Reference: End-to-End Flow

```bash
# 1. Ingest paper
curl -X POST http://127.0.0.1:8000/api/v1/papers/ingest \
  -F "title=TextCNN Paper" \
  -F "file=@1408.5882.pdf"
# Returns: paper_id

# 2. Extract claims (SSE stream)
curl -N -X POST http://127.0.0.1:8000/api/v1/papers/{paper_id}/extract

# 3. Generate plan (two-stage: o3-mini + GPT-4o)
curl -X POST http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan
# Returns: plan_id

# 4. Materialize notebook (uses Phase 2 smart dataset selection)
curl -X POST http://127.0.0.1:8000/api/v1/plans/{plan_id}/materialize
# Uploads to 'plans' bucket (NOT 'papers' bucket)

# 5. Get signed URLs
curl http://127.0.0.1:8000/api/v1/plans/{plan_id}/assets
# Returns: notebook_signed_url, env_signed_url (120s TTL)

# 6. Download notebook
curl -o notebook.ipynb "{notebook_signed_url}"

# 7. Verify Phase 2 working
grep "load_dataset" notebook.ipynb  # Should find real dataset loader
grep "make_classification" notebook.ipynb  # Should NOT find (no synthetic fallback)
```

---

## Troubleshooting

### Two-Stage Planner Fails
- **Symptom:** Empty output from Stage 1 (~10% of o3-mini calls)
- **Fix:** Retry the request (inherent o3-mini variability)
- **Don't:** Try to add structured outputs to o3-mini (will make it worse)

### Materialize Returns 500
- **Check:** Are you using `plans_storage` dependency (NOT `storage`)?
- **Check:** Do storage paths include bucket name prefix? (They shouldn't - bucket is in dependency)
- **Check:** Does `plans` bucket exist in Supabase and allow `text/plain`?

### Tests Failing After SDK Upgrade
- **Fix:** Revert to `openai==1.109.1` and `openai-agents==0.3.3`
- **Why:** Two-stage planner depends on specific SDK behaviors

### Notebooks Generate Synthetic Data for Known Datasets
- **Check:** Is dataset in registry (`dataset_registry.py`)?
- **Check:** Does factory lookup work (normalize name, check aliases)?
- **Debug:** Add logging to `factory.py::get_dataset_generator()` to see why fallback triggered

---

## Branch Information

**Main Branch:** `main`
- Contains all code (working + stubs + old files)
- Complete history preserved
- Use as reference/backup

**Clean Branch:** `clean/phase2-working`
- Only essential working code (Phase 1 & 2)
- No stubs (web/, worker/, infra/)
- No old SQL v0 files
- No old prompt files
- **Use this for Phase 3+ development**

Switch branches:
```bash
git checkout main                    # Full repo
git checkout clean/phase2-working    # Clean minimal repo
```

---

## Key Principles

1. **Agents produce JSON, not code** - Code generation uses deterministic generators
2. **Two-stage planner is intentional** - Don't try to collapse to single-stage
3. **Generators over LLMs for code** - Proven templates beat non-deterministic generation
4. **Storage buckets matter** - papers vs plans have different MIME restrictions
5. **Test generators independently** - Unit test each dataset/model generator
6. **Phase 2 is complete** - Smart dataset selection verified working Oct 2025
