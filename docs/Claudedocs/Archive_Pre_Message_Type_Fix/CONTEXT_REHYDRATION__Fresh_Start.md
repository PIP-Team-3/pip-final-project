# Context Rehydration Prompt - Fresh Supabase DB Deployment

**Date:** 2025-10-04
**Purpose:** Context for next Claude instance after creating fresh Supabase database
**Status:** Ready for fresh deployment

---

## What Happened (Previous Session Summary)

### The Problem
- Deployed nuclear schema v1 to existing Supabase project
- PostgREST schema cache got stuck looking for old `is_public` column
- Multiple cache refresh attempts failed
- Ingest endpoint blocked with PGRST204 error

### The Solution
**Create a FRESH Supabase project and deploy schema v1 from scratch.**

---

## Current State When You (Next Claude) Start

### Code Status ✅
- **Planner code is FIXED** - `api/app/routers/plans.py` lines 173-179
  - No `response_format` parameter
  - No `text_format` parameter
  - `vector_store_ids` correctly nested in tools array
  - Manual JSON parsing implemented
- **All code committed to GitHub** - Commit `4809a11`

### Schema Status ✅
- **Schema v1 Nuclear is READY** - `sql/schema_v1_nuclear_with_grants.sql`
  - 9 tables with full constraints
  - Foreign keys with CASCADE
  - CHECK constraints on status columns
  - UNIQUE constraints on pdf_sha256 and vector_store_id
  - RLS disabled for MVP
  - GRANTS included for service_role
  - Team-reviewed and approved

### What You Need to Do
1. User will provide NEW Supabase connection details
2. Deploy schema to FRESH database
3. Test ingest endpoint
4. Test planner endpoint
5. Celebrate when it works

---

## Step-by-Step Fresh Deployment

### Step 1: Get New Supabase Credentials

User will create new Supabase project and provide:
- `SUPABASE_URL` (e.g., `https://xxx.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` (JWT token)
- `SUPABASE_ANON_KEY` (optional, not needed for server)

### Step 2: Update .env File

```bash
# Update .env with new credentials
SUPABASE_URL=https://[NEW_PROJECT_ID].supabase.co
SUPABASE_SERVICE_ROLE_KEY=[NEW_SERVICE_ROLE_KEY]
```

**IMPORTANT:** Do NOT commit .env file (already in .gitignore)

### Step 3: Deploy Schema v1 to Fresh Database

**Option A: Run Complete File (Recommended)**
```sql
-- In Supabase SQL Editor, paste entire file:
-- sql/schema_v1_nuclear_with_grants.sql

-- This includes:
-- 1. pgcrypto extension
-- 2. GRANTS for service_role
-- 3. All 9 tables with constraints
-- 4. All 29 indexes
-- 5. Triggers for updated_at and duration_sec
-- 6. Helper views (latest_runs, paper_summary)
-- 7. RLS disabled on all tables
-- 8. All comments/documentation
```

**Option B: Step-by-Step (If File Doesn't Exist)**
1. Run `sql/schema_v1_nuclear.sql` (creates schema + RLS disable)
2. Then run GRANTS:
```sql
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;
```

### Step 4: Verify Schema Deployment

```sql
-- Check tables exist (should return 9 rows)
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Expected output:
-- assets, claims, evals, papers, plans, run_events, run_series, runs, storyboards

-- Check RLS is disabled (all should show rowsecurity = false)
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';

-- Check GRANTS applied
SELECT grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema='public' AND table_name='papers'
ORDER BY grantee, privilege_type;

-- Should see service_role with INSERT, SELECT, UPDATE, DELETE
```

### Step 5: Start Clean Server

```powershell
# Load .env with NEW credentials
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }

# Start server
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1
```

### Step 6: Test Ingest (Should Work Now!)

```powershell
$ing = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest `
  -F "title=Deep Residual Learning (CVPR 2016)" `
  -F "file=@C:\Users\jakem\Projects In Programming\He_Deep_Residual_Learning_CVPR_2016_paper.pdf;type=application/pdf" | ConvertFrom-Json

$paper_id = $ing.paper_id
$vsid = $ing.vector_store_id
"paper_id: $paper_id"
"vector_store_id: $vsid"
```

**Expected:** Valid UUIDs, no errors

### Step 7: Test Planner (Should Work Now!)

```powershell
$actor = [guid]::NewGuid().Guid
$planObj = @{
  created_by     = $actor
  budget_minutes = 5
  claims         = @(@{
      dataset="ImageNet"; split="val"; metric="top-1 accuracy"; value=75.3; units="percent";
      citation="He et al., 2016 (ResNet), CVPR, Table 1"; confidence=0.90
  })
}

$plan = Invoke-RestMethod -Method POST `
  -Uri ("http://127.0.0.1:8000/api/v1/papers/{0}/plan" -f $paper_id) `
  -Headers @{ "X-Actor-Id" = $actor } `
  -ContentType "application/json" `
  -Body ($planObj | ConvertTo-Json -Depth 10)

$plan_id = $plan.plan_id
"plan_id: $plan_id"
```

**Expected:** 200 OK with valid plan_id (NOT 502!)

---

## Key Technical Details (For Your Reference)

### OpenAI SDK Compatibility (1.109.1)

**DO NOT use these parameters** (they don't exist in SDK 1.109.1):
- ❌ `response_format`
- ❌ `text_format` (with Pydantic models)
- ❌ `tool_resources`
- ❌ Top-level `vector_store_ids`
- ❌ Message-level `attachments`

**Correct call shape for planner (lines 173-179):**
```python
stream_manager = client.responses.stream(
    model=agent_defaults.model,
    input=[system_content, user_payload],
    tools=tools,  # vector_store_ids is INSIDE tools array
    temperature=agent_defaults.temperature,
    max_output_tokens=agent_defaults.max_output_tokens,
)
```

**Tools array structure (lines 106-128):**
```python
tools = [{
    "type": "file_search",
    "max_num_results": 8,
    "vector_store_ids": [paper.vector_store_id]  # ✅ Nested inside tool
}]
```

### Database Schema v1 Features

**9 Tables:**
1. `papers` - Ingested PDFs with vector stores
2. `claims` - Extracted claims from Extractor agent
3. `plans` - Plan v1.1 JSON from Planner agent
4. `runs` - Notebook execution runs
5. `run_events` - SSE event stream (append-only)
6. `run_series` - Time series metrics (nullable `step` for terminal metrics)
7. `storyboards` - Kid-Mode explanations
8. `assets` - Storage artifact tracking
9. `evals` - Reproduction gap analysis

**Key Constraints:**
- `papers.vector_store_id` UNIQUE - prevents duplicate vector stores
- `papers.pdf_sha256` UNIQUE - prevents duplicate PDF ingests
- `runs.env_hash` NOT NULL - enforces materialization before run
- `run_series.step` NULLABLE - allows terminal metrics without fake steps
- Partial unique indexes on `assets` - prevents duplicate notebooks/logs/metrics

**Triggers:**
- Auto-update `updated_at` on papers, plans, storyboards
- Auto-calculate `duration_sec` on runs

---

## Previous Session Issues (Now Resolved)

### Issue 1: Zombie Background Servers ✅ RESOLVED
- 7 immortal bash processes running old buggy code
- **Solution:** User closed VSCode, killed all processes, started fresh
- **Won't happen again:** Fresh VSCode session

### Issue 2: Missing GRANTS ✅ RESOLVED
- After `DROP SCHEMA CASCADE`, service_role lost permissions
- **Solution:** GRANTS now included in `schema_v1_nuclear_with_grants.sql`
- **Won't happen again:** Fresh DB will have GRANTS from start

### Issue 3: PostgREST Schema Cache ✅ RESOLVED
- Old schema cached, looking for `is_public` column
- **Solution:** Fresh Supabase project has clean cache
- **Won't happen again:** Fresh DB has no old schema to cache

---

## Files to Reference

### Schema Files
- **[sql/schema_v1_nuclear_with_grants.sql](../../sql/schema_v1_nuclear_with_grants.sql)** - Complete deployment (GRANTS + schema)
- **[sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql)** - Schema only (460 lines)
- **[sql/migration_v0_to_v1.sql](../../sql/migration_v0_to_v1.sql)** - Incremental migration (NOT NEEDED for fresh DB)

### Code Files (Already Fixed)
- **[api/app/routers/plans.py](../../api/app/routers/plans.py)** - Planner endpoint (SDK 1.109.1 compatible)
- **[api/app/routers/papers.py](../../api/app/routers/papers.py)** - Ingest endpoint
- **[api/app/data/supabase.py](../../api/app/data/supabase.py)** - Database client

### Documentation
- **[docs/claudedocs/CRITICAL_POSTGREST_CACHE_ISSUE.md](CRITICAL_POSTGREST_CACHE_ISSUE.md)** - Previous session failures
- **[docs/claudedocs/SCHEMA_V1_NUCLEAR__Tracking_Doc.md](SCHEMA_V1_NUCLEAR__Tracking_Doc.md)** - Deployment tracking
- **[docs/claudedocs/SESSION_SUMMARY__Planner_Fix_Complete.md](SESSION_SUMMARY__Planner_Fix_Complete.md)** - Original planner fix
- **[docs/ROADMAP_P2N.md](../ROADMAP_P2N.md)** - Project roadmap

---

## Environment Variables Needed

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...  # User will provide (already in .env)

# Supabase (NEW - User will provide)
SUPABASE_URL=https://[NEW_PROJECT_ID].supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...  # NEW service role JWT

# Optional (already in .env)
P2N_DEV_USER_ID=119cba38-b850-4c31-84e6-87fcbe0bcc8e
```

---

## Testing Checklist

After fresh deployment, verify:

- [ ] Schema deployed: 9 tables exist
- [ ] RLS disabled: All tables show `rowsecurity = false`
- [ ] GRANTS applied: service_role has INSERT/SELECT/UPDATE/DELETE
- [ ] Server starts: No Supabase auth warnings (cosmetic, ignore if present)
- [ ] Ingest works: Returns `{paper_id, vector_store_id}` (200 OK)
- [ ] Planner works: Returns `{plan_id, plan_json}` (200 OK, NOT 502!)
- [ ] No PGRST204 errors
- [ ] No "permission denied" errors
- [ ] No zombie servers (only ONE python.exe process)

---

## If Something Goes Wrong

### Error: "permission denied for table papers"
**Fix:** Run GRANTS again (Step 3, Option B above)

### Error: PGRST204 "Could not find column"
**Fix:** This should NOT happen on fresh DB. If it does, restart PostgREST:
```sql
NOTIFY pgrst, 'reload schema';
```

### Error: "vector_store_id violates unique constraint"
**Cause:** Re-ingesting same paper twice
**Fix:** Expected behavior - constraint working correctly

### Error: "TypeError: got unexpected keyword 'response_format'"
**Cause:** Running old buggy code
**Fix:**
1. Check git status: `git status`
2. Pull latest: `git pull origin main`
3. Verify planner code has NO `response_format` at line 173

---

## Success Criteria

You'll know everything is working when:

1. **Ingest succeeds:**
   ```json
   {
     "paper_id": "uuid-here",
     "vector_store_id": "vs_...",
     "storage_path": "papers/dev/2025/10/05/uuid.pdf"
   }
   ```

2. **Planner succeeds:**
   ```json
   {
     "plan_id": "uuid-here",
     "plan_version": "1.1",
     "plan": { ... }
   }
   ```

3. **Database has data:**
   ```sql
   SELECT COUNT(*) FROM papers;  -- Returns 1
   SELECT COUNT(*) FROM plans;   -- Returns 1
   ```

4. **No errors in server logs** (except cosmetic Supabase auth warnings)

---

## Final Notes

- **Fresh DB = Clean Slate** - No cached schema, no zombie processes, no GRANTS issues
- **Schema v1 is production-ready** - Team-reviewed with 5+ hardening tweaks
- **Planner code is correct** - Fixed in previous session, committed to main
- **All docs updated** - Comprehensive tracking of all changes

**This should "just work" on fresh database.**

---

## Quick Reference Commands

```powershell
# Load .env
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }

# Start server
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1

# Test ingest
$ing = curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/papers/ingest -F "title=Test Paper" -F "file=@path/to/pdf.pdf;type=application/pdf" | ConvertFrom-Json

# Test planner
curl.exe -sS "http://127.0.0.1:8000/api/v1/papers/$($ing.paper_id)/plan"
```

---

**End of Context Rehydration Prompt**

**Next Claude:** Read this doc, follow steps 1-7, test, celebrate. 🎉
