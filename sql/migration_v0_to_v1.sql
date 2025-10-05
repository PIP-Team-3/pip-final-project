-- Migration: v0 → v1 Schema Hardening
-- Author: Claude Code
-- Date: 2025-10-04
-- Purpose: Add FKs, indexes, constraints, and missing columns without breaking existing code

-- =============================================================================
-- STEP 1: Add missing columns to existing tables
-- =============================================================================

-- Add missing columns to runs table
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS env_hash text,
  ADD COLUMN IF NOT EXISTS error_message text,
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS completed_at timestamptz;

-- Rename finished_at to align with app expectations (or keep both temporarily)
-- Option A: Keep both for backwards compat
-- Option B: Rename (commented out for safety)
-- ALTER TABLE runs RENAME COLUMN finished_at TO completed_at;

-- Add missing columns to storyboards
ALTER TABLE storyboards
  ADD COLUMN IF NOT EXISTS run_id uuid,
  ADD COLUMN IF NOT EXISTS storage_path text;

-- Rename plans.compute_budget_minutes to budget_minutes (or add alias)
-- Option: Keep both for backwards compat
ALTER TABLE plans
  ADD COLUMN IF NOT EXISTS budget_minutes int;

-- Backfill budget_minutes from compute_budget_minutes if needed
UPDATE plans
SET budget_minutes = compute_budget_minutes
WHERE budget_minutes IS NULL AND compute_budget_minutes IS NOT NULL;

-- =============================================================================
-- STEP 2: Add defaults to timestamp columns
-- =============================================================================

-- papers
ALTER TABLE papers
  ALTER COLUMN created_at SET DEFAULT NOW(),
  ALTER COLUMN updated_at SET DEFAULT NOW();

-- plans
ALTER TABLE plans
  ALTER COLUMN created_at SET DEFAULT NOW(),
  ALTER COLUMN updated_at SET DEFAULT NOW();

-- runs
ALTER TABLE runs
  ALTER COLUMN started_at SET DEFAULT NOW();

-- claims
ALTER TABLE claims
  ALTER COLUMN created_at SET DEFAULT NOW();

-- storyboards
ALTER TABLE storyboards
  ALTER COLUMN created_at SET DEFAULT NOW(),
  ALTER COLUMN updated_at SET DEFAULT NOW();

-- assets
ALTER TABLE assets
  ALTER COLUMN created_at SET DEFAULT NOW();

-- datasets
ALTER TABLE datasets
  ALTER COLUMN created_at SET DEFAULT NOW();

-- paper_sections
ALTER TABLE paper_sections
  ALTER COLUMN created_at SET DEFAULT NOW();

-- run_events
ALTER TABLE run_events
  ALTER COLUMN ts SET DEFAULT NOW();

-- run_metrics
ALTER TABLE run_metrics
  ALTER COLUMN created_at SET DEFAULT NOW();

-- =============================================================================
-- STEP 3: Add status defaults and constraints
-- =============================================================================

-- papers.status default
ALTER TABLE papers
  ALTER COLUMN status SET DEFAULT 'draft';

-- plans.status default
ALTER TABLE plans
  ALTER COLUMN status SET DEFAULT 'draft';

-- runs.status default
ALTER TABLE runs
  ALTER COLUMN status SET DEFAULT 'queued';

-- Add CHECK constraints for valid status values
ALTER TABLE papers
  ADD CONSTRAINT papers_status_check
  CHECK (status IN ('draft', 'processing', 'ready', 'failed'));

ALTER TABLE plans
  ADD CONSTRAINT plans_status_check
  CHECK (status IN ('draft', 'ready', 'failed'));

ALTER TABLE runs
  ADD CONSTRAINT runs_status_check
  CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'timeout', 'cancelled'));

-- =============================================================================
-- STEP 4: Add UNIQUE constraints to prevent duplicates
-- =============================================================================

-- Prevent duplicate PDF ingests (same SHA256)
CREATE UNIQUE INDEX IF NOT EXISTS papers_pdf_sha256_unique_idx
  ON papers(pdf_sha256)
  WHERE pdf_sha256 IS NOT NULL;

-- Prevent duplicate vector stores
CREATE UNIQUE INDEX IF NOT EXISTS papers_vector_store_unique_idx
  ON papers(vector_store_id)
  WHERE vector_store_id IS NOT NULL;

-- =============================================================================
-- STEP 5: Add Foreign Keys (as NOT VALID first for safety)
-- =============================================================================

-- plans → papers
ALTER TABLE plans
  ADD CONSTRAINT plans_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- runs → plans
ALTER TABLE runs
  ADD CONSTRAINT runs_plan_id_fk
  FOREIGN KEY (plan_id) REFERENCES plans(id)
  ON DELETE CASCADE
  NOT VALID;

-- runs → papers
ALTER TABLE runs
  ADD CONSTRAINT runs_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- claims → papers
ALTER TABLE claims
  ADD CONSTRAINT claims_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- paper_sections → papers
ALTER TABLE paper_sections
  ADD CONSTRAINT paper_sections_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- storyboards → papers
ALTER TABLE storyboards
  ADD CONSTRAINT storyboards_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- storyboards → runs (nullable)
ALTER TABLE storyboards
  ADD CONSTRAINT storyboards_run_id_fk
  FOREIGN KEY (run_id) REFERENCES runs(id)
  ON DELETE SET NULL
  NOT VALID;

-- run_events → runs
ALTER TABLE run_events
  ADD CONSTRAINT run_events_run_id_fk
  FOREIGN KEY (run_id) REFERENCES runs(id)
  ON DELETE CASCADE
  NOT VALID;

-- run_series → runs
ALTER TABLE run_series
  ADD CONSTRAINT run_series_run_id_fk
  FOREIGN KEY (run_id) REFERENCES runs(id)
  ON DELETE CASCADE
  NOT VALID;

-- run_metrics → runs
ALTER TABLE run_metrics
  ADD CONSTRAINT run_metrics_run_id_fk
  FOREIGN KEY (run_id) REFERENCES runs(id)
  ON DELETE CASCADE
  NOT VALID;

-- assets → papers (nullable)
ALTER TABLE assets
  ADD CONSTRAINT assets_paper_id_fk
  FOREIGN KEY (paper_id) REFERENCES papers(id)
  ON DELETE CASCADE
  NOT VALID;

-- assets → runs (nullable)
ALTER TABLE assets
  ADD CONSTRAINT assets_run_id_fk
  FOREIGN KEY (run_id) REFERENCES runs(id)
  ON DELETE CASCADE
  NOT VALID;

-- =============================================================================
-- STEP 6: Add Performance Indexes
-- =============================================================================

-- papers lookups
CREATE INDEX IF NOT EXISTS papers_created_at_idx ON papers(created_at DESC);
CREATE INDEX IF NOT EXISTS papers_created_by_idx ON papers(created_by) WHERE created_by IS NOT NULL;

-- plans lookups
CREATE INDEX IF NOT EXISTS plans_paper_id_idx ON plans(paper_id);
CREATE INDEX IF NOT EXISTS plans_created_at_idx ON plans(created_at DESC);

-- runs hot paths (most common queries)
CREATE INDEX IF NOT EXISTS runs_paper_id_status_idx ON runs(paper_id, status);
CREATE INDEX IF NOT EXISTS runs_plan_id_idx ON runs(plan_id);
CREATE INDEX IF NOT EXISTS runs_status_idx ON runs(status);
CREATE INDEX IF NOT EXISTS runs_paper_completed_idx ON runs(paper_id, completed_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS runs_created_at_idx ON runs(created_at DESC);

-- run_events for replay/streaming
CREATE INDEX IF NOT EXISTS run_events_run_id_ts_idx ON run_events(run_id, ts);

-- run_series for metrics charts
CREATE INDEX IF NOT EXISTS run_series_run_metric_step_idx ON run_series(run_id, metric, step);

-- claims for reports
CREATE INDEX IF NOT EXISTS claims_paper_id_idx ON claims(paper_id);

-- storyboards
CREATE INDEX IF NOT EXISTS storyboards_paper_id_idx ON storyboards(paper_id);
CREATE INDEX IF NOT EXISTS storyboards_run_id_idx ON storyboards(run_id) WHERE run_id IS NOT NULL;

-- =============================================================================
-- STEP 7: Validate foreign keys (AFTER cleaning any orphaned data)
-- =============================================================================

-- IMPORTANT: Only run these AFTER you've cleaned up any orphaned records!
-- Uncomment these once you've verified no FK violations exist:

-- ALTER TABLE plans VALIDATE CONSTRAINT plans_paper_id_fk;
-- ALTER TABLE runs VALIDATE CONSTRAINT runs_plan_id_fk;
-- ALTER TABLE runs VALIDATE CONSTRAINT runs_paper_id_fk;
-- ALTER TABLE claims VALIDATE CONSTRAINT claims_paper_id_fk;
-- ALTER TABLE paper_sections VALIDATE CONSTRAINT paper_sections_paper_id_fk;
-- ALTER TABLE storyboards VALIDATE CONSTRAINT storyboards_paper_id_fk;
-- ALTER TABLE storyboards VALIDATE CONSTRAINT storyboards_run_id_fk;
-- ALTER TABLE run_events VALIDATE CONSTRAINT run_events_run_id_fk;
-- ALTER TABLE run_series VALIDATE CONSTRAINT run_series_run_id_fk;
-- ALTER TABLE run_metrics VALIDATE CONSTRAINT run_metrics_run_id_fk;
-- ALTER TABLE assets VALIDATE CONSTRAINT assets_paper_id_fk;
-- ALTER TABLE assets VALIDATE CONSTRAINT assets_run_id_fk;

-- =============================================================================
-- STEP 8: Find orphaned records (run these queries to check before validating FKs)
-- =============================================================================

/*
-- Find plans with invalid paper_id
SELECT p.id, p.paper_id
FROM plans p
LEFT JOIN papers pap ON p.paper_id = pap.id
WHERE pap.id IS NULL;

-- Find runs with invalid plan_id
SELECT r.id, r.plan_id
FROM runs r
LEFT JOIN plans p ON r.plan_id = p.id
WHERE p.id IS NULL;

-- Find runs with invalid paper_id
SELECT r.id, r.paper_id
FROM runs r
LEFT JOIN papers p ON r.paper_id = p.id
WHERE p.id IS NULL;

-- Delete orphaned records if safe:
-- DELETE FROM plans WHERE paper_id NOT IN (SELECT id FROM papers);
-- DELETE FROM runs WHERE plan_id NOT IN (SELECT id FROM plans);
-- DELETE FROM runs WHERE paper_id NOT IN (SELECT id FROM papers);
*/

-- =============================================================================
-- NOTES:
-- =============================================================================
-- 1. FKs are added as NOT VALID - they don't enforce on existing rows yet
-- 2. Run the orphaned record queries above to find bad data
-- 3. Clean up orphaned records manually
-- 4. Uncomment VALIDATE statements in Step 7 to enforce FKs going forward
-- 5. This migration is BACKWARDS COMPATIBLE - existing code will continue to work
-- 6. New inserts will be validated against FKs once validated
