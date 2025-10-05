# Database Upgrade Plan — v1 Hardening (FKs, Indexes, RLS) — *Plan only, do not apply yet*

_Current posture: v0 (app-enforced), no FKs/RLS/checks._

## Goals

- Introduce **foreign keys** and minimal **indexes** for integrity & perf.
- Draft **RLS** policies for future multi-tenant safety (not enabled yet).
- Keep SQL migrations **generated but not applied** (CI parse-only).

## Proposed Relations (simplified)

```
papers(id PK, title, storage_path, vector_store_id, created_by, created_at)
plans(id PK, paper_id FK->papers(id), env_hash, plan_json JSONB, budget_minutes, created_by, created_at)
runs(id PK, plan_id FK->plans(id), paper_id FK->papers(id), env_hash, status, created_at, started_at, completed_at)
run_events(id PK, run_id FK->runs(id), seq BIGINT, type, payload JSONB, created_at)
storyboards(id PK, paper_id FK->papers(id), run_id FK->runs(id), json JSONB, created_at)
```

**Indexes:**  
- `runs(plan_id)`, `runs(paper_id)`, `run_events(run_id, seq)`  
- `plans(paper_id)`

## Migration Sketch (SQL)

```sql
-- 001_init_v1.sql

BEGIN;

ALTER TABLE plans
  ADD COLUMN IF NOT EXISTS paper_id UUID,
  ADD CONSTRAINT plans_paper_id_fk
    FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS paper_id UUID,
  ADD COLUMN IF NOT EXISTS plan_id  UUID,
  ADD CONSTRAINT runs_plan_id_fk
    FOREIGN KEY (plan_id)  REFERENCES plans(id),
  ADD CONSTRAINT runs_paper_id_fk
    FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE run_events
  ADD COLUMN IF NOT EXISTS run_id UUID,
  ADD CONSTRAINT run_events_run_id_fk
    FOREIGN KEY (run_id) REFERENCES runs(id);

ALTER TABLE storyboards
  ADD COLUMN IF NOT EXISTS paper_id UUID,
  ADD COLUMN IF NOT EXISTS run_id  UUID,
  ADD CONSTRAINT storyboards_paper_id_fk
    FOREIGN KEY (paper_id) REFERENCES papers(id),
  ADD CONSTRAINT storyboards_run_id_fk
    FOREIGN KEY (run_id) REFERENCES runs(id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_plans_paper_id   ON plans(paper_id);
CREATE INDEX IF NOT EXISTS idx_runs_plan_id     ON runs(plan_id);
CREATE INDEX IF NOT EXISTS idx_runs_paper_id    ON runs(paper_id);
CREATE INDEX IF NOT EXISTS idx_run_events_byseq ON run_events(run_id, seq);

COMMIT;
```

> Apply **only** after we cut a `v0` tag and update the app to send `paper_id` and `plan_id` consistently (already true in code).

## RLS (future sketch, do not enable yet)

- Base policy: owner via `created_by` (UUID).  
- Reader policy: short‑TTL signed URLs for artifacts only.

## Rollout Plan

1. Generate file under `db/migrations/001_init_v1.sql` (commit to repo).  
2. CI adds a “**parse-only**” job (`psql -f` against throwaway DB).  
3. When we are ready for production hardening, schedule a maintenance window to apply.  
4. Add `RLS` in a separate migration once tenanting needs are pinned.
