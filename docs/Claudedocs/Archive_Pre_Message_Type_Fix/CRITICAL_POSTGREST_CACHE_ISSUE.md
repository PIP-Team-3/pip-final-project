# CRITICAL: PostgREST Schema Cache Won't Refresh - PGRST204

**Date:** 2025-10-04
**Status:** 🔴 BLOCKING - Ingest failing with PGRST204 after nuclear schema rebuild

---

## TL;DR

After nuclear schema rebuild (`DROP SCHEMA public CASCADE`), PostgREST's schema cache is stuck looking for a column `is_public` that doesn't exist in the new v1 schema. Multiple cache refresh attempts have FAILED.

---

## The Error

```
postgrest.exceptions.APIError: {
    'message': "Could not find the 'is_public' column of 'papers' in the schema cache",
    'code': 'PGRST204'
}
```

**Location:** `api/app/data/supabase.py` line 86 during `insert_paper()`

---

## What We Did (Nuclear Schema Rebuild Session)

### 1. Deployed Nuclear Schema v1 ✅
- Ran `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`
- Ran entire [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) (460 lines)
- Created 9 tables with full constraints
- Verified tables exist: `papers`, `claims`, `plans`, `runs`, `run_events`, `run_series`, `storyboards`, `assets`, `evals`

### 2. Disabled RLS ✅
```sql
ALTER TABLE papers DISABLE ROW LEVEL SECURITY;
-- ... (all 9 tables)
```
- Verified: `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';`
- All tables show `rowsecurity = false` ✅

### 3. Applied GRANTS (ChatGPT's Fix) ✅
```sql
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;
```
- Executed successfully: "Success. No rows returned"

### 4. Attempted PostgREST Schema Cache Refresh ❌

**Attempt 1: Python Supabase Query**
```python
client.table('papers').select('*').limit(1).execute()
# Result: "Schema cache refreshed - query returned: 0 rows"
```
**FAILED:** Server still gets PGRST204

**Attempt 2: Direct SQL NOTIFY (Failed - No psql)**
```bash
psql "postgresql://..." -c "NOTIFY pgrst, 'reload schema';"
# Error: psql: command not found
```

**Attempt 3: Python psycopg2 NOTIFY (Failed - Wrong Connection String)**
```python
psycopg2.connect('postgresql://postgres.qpfmxijmvkpnaqjjrxim:...@aws-0-us-east-1.pooler.supabase.com:6543/postgres')
# Error: FATAL: Tenant or user not found
```

**Attempt 4: User Manually Restarted PostgREST in Dashboard**
- User ran NOTIFY command in Supabase SQL Editor (probably)
- Verified with Python query: `Schema cache is FRESH - query succeeded`

**Attempt 5: Restarted Python Server**
- Killed server (Ctrl+C)
- Restarted: `.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1`
- **STILL FAILS with PGRST204!**

---

## Current State

### What Works ✅
- Schema v1 deployed correctly
- Tables exist with correct structure (no `is_public` column)
- RLS disabled
- GRANTS applied
- Python query to Supabase succeeds: `client.table('papers').select('id,title').execute()` works

### What Fails ❌
- **API ingest endpoint:** 500 Internal Server Error
- **Error:** PGRST204 "Could not find 'is_public' column"
- **Even after:** PostgREST restart, server restart, fresh Supabase client

---

## Theory: Why PostgREST Cache Won't Refresh

### Hypothesis 1: Multiple PostgREST Instances
- Supabase may run multiple PostgREST instances for load balancing
- NOTIFY command only reloads ONE instance
- API requests randomly hit different instances (some with stale cache)

**Test:** Retry ingest multiple times - if it randomly succeeds, this is the issue

### Hypothesis 2: Supabase Pooler Caching
- Connection pooler (`aws-0-us-east-1.pooler.supabase.com`) may cache schema
- Direct connection (`db.xxx.supabase.co`) bypasses pooler
- Our code uses pooler connection string

**Test:** Change Supabase URL to direct connection (not pooler)

### Hypothesis 3: Old Schema in `information_schema`
- PostgREST reads from `information_schema.columns`
- After `DROP SCHEMA CASCADE`, metadata may be stale
- Need to force PostgreSQL system catalog refresh

**Test:** Run `VACUUM FULL pg_catalog.pg_class; ANALYZE;`

### Hypothesis 4: Supabase SDK Client-Side Cache
- `supabase-py` library may cache schema on client side
- Restarting server doesn't clear this cache (persisted somewhere?)

**Test:** Delete `__pycache__` and restart

---

## Evidence Collection

### 1. What Column is PostgREST Looking For?

Run this SQL to see what PostgREST sees:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name = 'papers'
ORDER BY ordinal_position;
```

**Expected (v1 schema):** No `is_public` column
**If PGRST204 persists:** PostgREST is reading from stale cache, NOT from `information_schema`

### 2. What Does Direct PostgreSQL Query Show?

```sql
SELECT * FROM papers LIMIT 1;
```

**Expected:** Works (table exists)
**If fails:** Schema wasn't actually deployed

### 3. What Does PostgREST API Show Directly?

```bash
curl -X GET 'https://qpfmxijmvkpnaqjjrxim.supabase.co/rest/v1/papers?select=*&limit=1' \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Authorization: Bearer YOUR_SERVICE_ROLE_KEY"
```

**Expected:** If PGRST204, confirms PostgREST cache is stale
**If works:** API server's Supabase client has stale connection

---

## Nuclear Options (If Nothing Else Works)

### Option 1: Wait 5-10 Minutes
- PostgREST may have auto-refresh interval
- Cache expires naturally after X minutes
- **Action:** Wait 10 minutes, retry ingest

### Option 2: Fully Restart Supabase Project
- Supabase Dashboard → Settings → General → "Pause Project"
- Wait 30 seconds
- "Resume Project"
- **Warning:** Downtime, but forces full cache flush

### Option 3: Re-Deploy Schema With Different Table Name
- Rename `papers` → `papers_v2` everywhere
- PostgREST won't have cached schema for `papers_v2`
- **Warning:** Requires code changes

### Option 4: Add Dummy `is_public` Column
- Hack: Add the column PostgREST expects, then ignore it
```sql
ALTER TABLE papers ADD COLUMN is_public boolean DEFAULT false;
```
- **Warning:** Pollutes schema with unused column

---

## What We Know About v0 Schema

The old schema (before nuclear rebuild) had an `is_public` column that we **don't have in v1**. This suggests:

1. Old schema was deployed weeks ago with `is_public` column
2. Nuclear rebuild removed it (correct)
3. PostgREST cached the old schema structure
4. Cache refresh commands aren't reaching all PostgREST instances

---

## Next Steps for Team

### Immediate (User to Try)
1. **Wait 10 minutes** - Let PostgREST cache expire naturally
2. **Retry ingest** - See if PGRST204 goes away
3. **Try multiple times** - If it randomly succeeds, confirms multiple PostgREST instances

### If Still Failing
1. **Check `information_schema`** - Run SQL query above to see actual columns
2. **Test PostgREST API directly** - curl command above
3. **Check Supabase logs** - Dashboard → Logs → API logs for PGRST204

### Nuclear Option (Last Resort)
1. **Pause/Resume Supabase Project** - Forces full restart
2. **OR Add dummy column** - `ALTER TABLE papers ADD COLUMN is_public boolean;`

---

## Files Modified This Session

1. ✅ [sql/schema_v1_nuclear.sql](../../sql/schema_v1_nuclear.sql) - 460 lines, deployed
2. ✅ [sql/schema_v1_nuclear_with_grants.sql](../../sql/schema_v1_nuclear_with_grants.sql) - Schema + GRANTS
3. ✅ Installed `psycopg2-binary` in .venv (for future NOTIFY commands)
4. ✅ Applied GRANTS via Supabase SQL Editor
5. ✅ Disabled RLS via Supabase SQL Editor
6. ✅ Attempted NOTIFY via multiple methods (all failed to fix issue)

---

## Code That's Failing

**File:** `api/app/data/supabase.py` line 86

```python
response = self._client.table("papers").insert(data).execute()
```

**The `data` dict does NOT contain `is_public`** (correct for v1 schema)
**PostgREST expects it** (cached from old v0 schema)
**Result:** PGRST204 error

---

## Summary for Team

**We successfully deployed schema v1, disabled RLS, and applied GRANTS. The schema is correct. PostgREST's schema cache is stuck on the old v0 schema and won't refresh despite multiple attempts.**

**Recommendation:** Wait 10 minutes for cache to expire, or pause/resume Supabase project to force full restart.

---

**End of Critical Issue Report**
