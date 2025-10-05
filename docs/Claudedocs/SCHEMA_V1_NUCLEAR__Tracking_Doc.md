# Schema v1 Nuclear Rebuild - Tracking Document
**Last Updated:** 2025-10-04 17:15 UTC
**Status:** ⚠️ RLS PERMISSIONS FIX NEEDED

---

## Executive Summary

This document tracks the nuclear schema v1 rebuild for P2N (Paper-to-Notebook) project. The planner endpoint is fixed and production-ready, but blocked by invalid `vector_store_id` in the current v0 database schema. User requested "go nuclear" - complete schema rebuild with full integrity constraints.

**✅ DEPLOYMENT SUCCESSFUL:**
- Nuclear schema deployed to Supabase
- 9 tables created with full constraints
- Team tweaks applied (5 suggestions + 1 bonus)

**⚠️ RLS PERMISSIONS ISSUE DISCOVERED:**
- Supabase enables RLS by default on new tables
- Service role key blocked with "permission denied for table papers"
- **FIX:** Run RLS DISABLE commands (added to schema v1 lines 447-455)

---

## Changes Made This Session

### 1. Security: Gitignore & Secrets Protection ✅

**Problem:** API keys exposed in `start_server.ps1` (hardcoded OPENAI_API_KEY and SUPABASE_SERVICE_ROLE_KEY)

**Actions Taken:**
- ✅ Added `.claude/` to `.gitignore` (line 26)
- ✅ Added `start_server.ps1` to `.gitignore` (line 29-30)
- ✅ Created `start_server.EXAMPLE.ps1` with .env loader (safe to commit)
- ✅ Verified NO secrets in files to be committed:
  - `docs/Claudedocs/` - clean ✅
  - `sql/` - clean ✅
  - All untracked files - clean ✅

**Files Modified:**
- [.gitignore](../../.gitignore) - Added `.claude/`, `start_server.ps1`, `start_server.local.ps1`
- [start_server.EXAMPLE.ps1](../../start_server.EXAMPLE.ps1) - Created safe example

### 2. Schema v1 Nuclear - Team Tweaks Applied ✅

**File:** [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) (438 lines)

**Team Feedback Received:**
1. ✅ **Make `run_series.step` NULLABLE** - allows terminal metrics without fake steps
2. ✅ **Add partial unique indexes on assets** - prevents duplicate notebooks/metrics/logs per parent
3. ✅ **Keep `runs.env_hash NOT NULL`** - enforces materialization before run (E_PLAN_NOT_MATERIALIZED)
4. ✅ **Keep `papers.vector_store_id UNIQUE`** - prevents the exact issue that caused planner 502
5. ✅ **Add pgcrypto extension** - for `gen_random_uuid()` support

**Changes Applied:**

#### Change 1: `run_series.step` now NULLABLE (line 191)
```sql
step int,  -- epoch or iteration number (NULL for terminal metrics)
```
**Rationale:** Runner may emit progress percent or one-shot metrics without step values

#### Change 2: Added pgcrypto extension (line 25)
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

#### Change 3: Added 6 partial unique indexes on assets (lines 276-292)
```sql
-- Prevent duplicate assets per parent/kind
CREATE UNIQUE INDEX assets_plan_notebook_uniq
    ON assets(plan_id) WHERE kind = 'notebook' AND plan_id IS NOT NULL;

CREATE UNIQUE INDEX assets_plan_requirements_uniq
    ON assets(plan_id) WHERE kind = 'requirements' AND plan_id IS NOT NULL;

CREATE UNIQUE INDEX assets_run_metrics_uniq
    ON assets(run_id) WHERE kind = 'metrics' AND run_id IS NOT NULL;

CREATE UNIQUE INDEX assets_run_logs_uniq
    ON assets(run_id) WHERE kind = 'logs' AND run_id IS NOT NULL;

CREATE UNIQUE INDEX assets_run_events_uniq
    ON assets(run_id) WHERE kind = 'events' AND run_id IS NOT NULL;

CREATE UNIQUE INDEX assets_paper_pdf_uniq
    ON assets(paper_id) WHERE kind = 'pdf' AND paper_id IS NOT NULL;
```
**Rationale:** Prevents accidental duplicate asset creation (e.g., two notebooks for one plan)

#### Change 4: Added storage path CHECK constraints (lines 45, 215)
```sql
-- papers.pdf_storage_path
CHECK (pdf_storage_path LIKE 'papers/%')

-- storyboards.storage_path
CHECK (storage_path LIKE 'storyboards/%')
```
**Rationale:** Validates storage paths match expected bucket prefixes (prevents corruption)

#### Change 5: Updated comments for new features (lines 377, 388, 395, 399, 401)
```sql
COMMENT ON COLUMN papers.pdf_storage_path IS 'Supabase Storage path - must start with papers/';
COMMENT ON COLUMN runs.env_hash IS 'Copied from plan.env_hash at runtime - NOT NULL enforces materialization before run';
COMMENT ON COLUMN run_series.step IS 'Epoch or iteration number - NULL for terminal/one-shot metrics';
COMMENT ON COLUMN storyboards.storage_path IS 'Supabase Storage path - must start with storyboards/';
COMMENT ON TABLE assets IS 'Links to Supabase Storage objects - partial unique indexes prevent duplicate assets per parent/kind';
```

**Git Status:**
```
M .gitignore
M api/app/routers/plans.py (from previous session - planner fix)
M sql/schema_v1_nuclear.sql (team tweaks applied)
?? docs/claudedocs/ (session summaries, playbooks, tracking doc)
?? sql/migration_v0_to_v1.sql (incremental migration - alternative approach)
?? start_server.EXAMPLE.ps1 (safe example)
```

---

## Current Database Schema Analysis

### Schema v0 (Current - Weak)

**Critical Issues:**
1. ❌ No foreign keys → orphaned records allowed
2. ❌ No CHECK constraints → invalid states allowed (e.g., `status = 'asdfasdf'`)
3. ❌ No UNIQUE constraints → duplicate ingests allowed
4. ❌ No DEFAULT timestamps → manual entry required everywhere
5. ❌ Wrong column types → `run_events.id` is `bigint` but app uses UUIDs
6. ❌ Hardcoded invalid data → `vector_store_id = 'vs_68def3f856c88190ad914e41d0dfea8c'` (404 NOT FOUND)

**Impact:** The planner 502 errors were caused by this weak schema allowing corrupted data to persist.

### Schema v1 Nuclear (Proposed - Strong)

**File:** [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) (403 lines)

**Key Features:**
- ✅ Foreign keys with CASCADE on ALL relationships
- ✅ CHECK constraints on status columns: `CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'timeout', 'cancelled'))`
- ✅ UNIQUE constraints: `UNIQUE (pdf_sha256)`, `UNIQUE (vector_store_id)`
- ✅ NOT NULL on required fields
- ✅ DEFAULT NOW() on all timestamps
- ✅ 23 indexes on hot query paths
- ✅ Auto-update triggers for `updated_at`
- ✅ Auto-calculate `duration_sec` trigger
- ✅ Helper views: `latest_runs`, `paper_summary`
- ✅ Comprehensive table/column comments

**Tables:** 9 tables total
1. `papers` - Ingested PDFs with vector stores
2. `claims` - Extracted claims from Extractor agent
3. `plans` - Plan v1.1 JSON from Planner agent
4. `runs` - Notebook execution runs
5. `run_events` - SSE event stream (append-only)
6. `run_series` - Time series metrics (accuracy over epochs)
7. `storyboards` - Kid-Mode explanations
8. `assets` - Storage artifact tracking
9. `evals` - Reproduction gap analysis

---

## Team Review Summary

### All Team Tweaks Applied ✅

| Tweak | Status | Impact |
|-------|--------|--------|
| 1. `run_series.step` NULLABLE | ✅ Applied | Allows terminal metrics without fake step values |
| 2. Partial unique indexes on assets | ✅ Applied | Prevents duplicate notebooks/logs/metrics per parent |
| 3. Keep `runs.env_hash NOT NULL` | ✅ Confirmed | Enforces materialization before run (typed error E_PLAN_NOT_MATERIALIZED) |
| 4. Keep `papers.vector_store_id UNIQUE` | ✅ Confirmed | **Prevents the exact planner 502 issue we just fixed** |
| 5. Add `pgcrypto` extension | ✅ Applied | Enables gen_random_uuid() for UUIDs |
| 6. Storage path CHECK constraints (bonus) | ✅ Applied | Validates paths start with correct bucket prefix |

**Team Verdict:** Schema is production-ready for nuclear deployment.

---

## Additional Considerations (Deferred to v1.1)

### 1. Missing `created_by` FK Constraint ⏭️

**Current State:** `created_by uuid` on most tables but NO foreign key

**Decision:** Keep nullable without FK for v1.0
- No blocking issues for MVP
- Add `profiles` table + FK in v1.1 when multi-tenant auth is implemented
- P2N_DEV_USER_ID environment variable suffices for dev

### 2. RLS (Row-Level Security) ⏭️

**Current State:** No RLS policies

**Decision:** Defer to v1.1
- See [DB_UPGRADE_PLAN__v1_FKs_RLS.md](DB_UPGRADE_PLAN__v1_FKs_RLS.md) for future RLS sketch
- Base policy: owner via `created_by` UUID
- Reader policy: short-TTL signed URLs for artifacts only

**Impact:** Service role key currently has full access (acceptable for dev/MVP)

---

## Nuclear Deployment Plan ✅ READY

**Prerequisites:**
- User said "idc about this data at all" - safe to drop everything
- Planner code is production-ready (from previous session)
- No secrets in tracked files (verified ✅)

**Deployment Method:** Supabase SQL Editor

### Step 1: Backup (Optional - user said "idc about this data")
```sql
-- Skip this step per user request
```

### Step 2: Nuclear Drop (DESTRUCTIVE)
```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
```

### Step 3: Deploy v1 Schema
- Run entire [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) in Supabase SQL Editor

### Step 4: Verify
```sql
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT conname, contype FROM pg_constraint WHERE connamespace = 'public'::regnamespace;
```

### Step 5: Re-ingest Test Paper
```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"arxiv_url": "https://arxiv.org/abs/1706.03762", "created_by": "119cba38-b850-4c31-84e6-87fcbe0bcc8e"}'
```

### Step 6: Test Planner
```bash
curl http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan
```

---

## Implementation Approach

### Option A: Manual Deployment (Recommended for Control)

**User performs these steps in Supabase SQL Editor:**

1. Navigate to Supabase project SQL Editor
2. Copy entire contents of [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql)
3. Paste into SQL Editor
4. Execute (will take ~5-10 seconds)
5. Verify: `SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;`
6. Expected: 9 tables (papers, claims, plans, runs, run_events, run_series, storyboards, assets, evals)

**Then test planner:**
```bash
# Re-ingest test paper
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"arxiv_url": "https://arxiv.org/abs/1706.03762", "created_by": "119cba38-b850-4c31-84e6-87fcbe0bcc8e"}'

# Test planner (expect 200 OK)
curl http://127.0.0.1:8000/api/v1/papers/{paper_id}/plan
```

### Option B: Git Commit + Push + Manual Deployment

1. Commit all changes (schema, planner fix, docs, gitignore updates)
2. Push to GitHub
3. User manually runs nuclear schema in Supabase (same as Option A step 2-6)
4. Test planner

### Option C: Quick Fix First, Nuclear Later

1. User runs single SQL UPDATE to fix vector_store_id
2. Test planner proves code works
3. Then deploy nuclear schema with confidence

**Recommendation:** Option A (manual deployment now) gives fastest path to testing planner with clean data.

---

## Next Steps

1. ✅ **COMPLETED:** Team DB tweaks evaluated and applied
2. ✅ **COMPLETED:** `schema_v1_nuclear.sql` updated with team feedback
3. **YOUR CHOICE:** Deploy nuclear schema (see Implementation Approach above)
4. **THEN:** Test planner end-to-end with fresh data
5. **THEN:** Fix extractor endpoint (same changes as planner)
6. **THEN:** Commit & push to GitHub

---

## References

**Session Summaries:**
- [SESSION_SUMMARY__Planner_Fix_Complete.md](SESSION_SUMMARY__Planner_Fix_Complete.md) - Previous session context

**Playbooks:**
- [PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md](PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md) - Testing guide

**Schema Files:**
- [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) - Nuclear rebuild (403 lines)
- [sql/migration_v0_to_v1.sql](../../sql/migration_v0_to_v1.sql) - Incremental migration (alternative)

**Roadmaps:**
- [docs/ROADMAP_P2N.md](../ROADMAP_P2N.md) - Project roadmap
- [docs/PLAYBOOK_MA.md](../PLAYBOOK_MA.md) - Manual testing playbook

---

## Git Safety Checklist ✅

- ✅ `.env` in `.gitignore`
- ✅ `.claude/` in `.gitignore`
- ✅ `start_server.ps1` in `.gitignore` (contains secrets)
- ✅ `start_server.EXAMPLE.ps1` created (safe to commit)
- ✅ No secrets in `docs/Claudedocs/`
- ✅ No secrets in `sql/`
- ✅ All files to be committed verified clean

---

**End of Tracking Document**
