-- =============================================================================
-- P2N (Paper-to-Notebook) Schema v1 - Production Ready + GRANTS
-- =============================================================================
-- Author: Claude Code + Team Review + ChatGPT GRANTS fix
-- Date: 2025-10-04
-- Purpose: Complete deployment script with schema + permissions
--
-- IMPORTANT: Run this ENTIRE file after DROP SCHEMA public CASCADE
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- SCHEMA & GRANTS (Fix for permission denied after nuclear rebuild)
-- =============================================================================

-- Ensure service_role has full access to public schema
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- Future-proof: auto-grant on newly created objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;

-- =============================================================================
-- CORE ENTITIES
-- =============================================================================

-- (Rest of schema identical to schema_v1_nuclear.sql - importing below)
-- =============================================================================
-- P2N (Paper-to-Notebook) Schema v1 - Production Ready (Nuclear Rebuild)
-- =============================================================================
-- Author: Claude Code + Team Review
-- Date: 2025-10-04
-- Purpose: Clean slate schema with full integrity, performance, and safety
--
-- Design Principles:
-- 1. Foreign keys with CASCADE for referential integrity
-- 2. CHECK constraints for valid states
-- 3. UNIQUE constraints to prevent duplicates
-- 4. NOT NULL where app always provides values
-- 5. DEFAULT NOW() on all timestamps
-- 6. Indexes on all foreign keys and hot query paths
-- 7. JSONB for complex structures (validated by app)
-- 8. Text for IDs from external systems (OpenAI vector stores, etc.)
-- 9. Partial unique indexes to prevent duplicate assets per parent/kind
-- 10. pgcrypto extension for gen_random_uuid()
-- =============================================================================

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- RLS CONFIGURATION (Disabled for MVP - Service Role has full access)
-- =============================================================================
-- NOTE: In production with multi-tenant, enable RLS and add policies per table
-- See docs/claudedocs/DB_UPGRADE_PLAN__v1_FKs_RLS.md for future RLS design

-- =============================================================================
-- CORE ENTITIES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Papers: Ingested research papers with OpenAI vector stores
-- -----------------------------------------------------------------------------
CREATE TABLE papers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Metadata
    title text NOT NULL,
    source_url text,
    doi text,
    arxiv_id text,

    -- Storage & Search
    pdf_storage_path text NOT NULL              -- Supabase Storage path
        CHECK (pdf_storage_path LIKE 'papers/%'),
    vector_store_id text NOT NULL,               -- OpenAI vector store ID (vs_...)
    pdf_sha256 text NOT NULL,                    -- For duplicate detection

    -- Status tracking
    status text NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'processing', 'failed')),

    -- Audit
    created_by uuid,                              -- Optional: future multi-tenant
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT papers_pdf_sha256_unique UNIQUE (pdf_sha256),
    CONSTRAINT papers_vector_store_unique UNIQUE (vector_store_id)
);

CREATE INDEX papers_created_at_idx ON papers(created_at DESC);
CREATE INDEX papers_status_idx ON papers(status) WHERE status != 'ready';

-- -----------------------------------------------------------------------------
-- Claims: Extracted claims from papers (from Extractor agent)
-- -----------------------------------------------------------------------------
CREATE TABLE claims (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,

    -- Claim data
    dataset_name text,
    split text,
    metric_name text NOT NULL,
    metric_value numeric NOT NULL,
    units text,
    method_snippet text,

    -- Evidence
    source_citation text NOT NULL,               -- "Table 1, page 4"
    confidence numeric NOT NULL                  -- 0.0 - 1.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Audit
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX claims_paper_id_idx ON claims(paper_id);
CREATE INDEX claims_confidence_idx ON claims(confidence DESC);

-- -----------------------------------------------------------------------------
-- Plans: Generated execution plans (Plan v1.1 JSON from Planner agent)
-- -----------------------------------------------------------------------------
CREATE TABLE plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,

    -- Plan content (validated Plan v1.1 JSON)
    version text NOT NULL DEFAULT '1.1',
    plan_json jsonb NOT NULL,

    -- Materialization
    env_hash text,                               -- SHA256 of sorted requirements.txt (NULL until materialized)
    budget_minutes int NOT NULL DEFAULT 20
        CHECK (budget_minutes > 0 AND budget_minutes <= 120),

    -- Status
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'ready', 'failed')),

    -- Audit
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX plans_paper_id_idx ON plans(paper_id);
CREATE INDEX plans_env_hash_idx ON plans(env_hash) WHERE env_hash IS NOT NULL;
CREATE INDEX plans_created_at_idx ON plans(created_at DESC);

-- -----------------------------------------------------------------------------
-- Runs: Notebook execution runs (deterministic, CPU-only)
-- -----------------------------------------------------------------------------
CREATE TABLE runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References (both for easy querying)
    plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,

    -- Execution metadata
    env_hash text NOT NULL,                      -- Copied from plan at runtime (enforces materialization)
    seed int NOT NULL DEFAULT 42,

    -- Status tracking
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'timeout', 'cancelled')),

    -- Timing
    created_at timestamptz NOT NULL DEFAULT NOW(),
    started_at timestamptz,
    completed_at timestamptz,
    duration_sec int,

    -- Error tracking
    error_code text,                             -- E_GPU_REQUESTED, E_RUN_TIMEOUT, E_PLAN_NOT_MATERIALIZED, etc.
    error_message text,

    -- Constraints
    CONSTRAINT runs_timing_check
        CHECK (started_at IS NULL OR started_at >= created_at),
    CONSTRAINT runs_completion_check
        CHECK (completed_at IS NULL OR completed_at >= started_at),
    CONSTRAINT runs_duration_check
        CHECK (duration_sec IS NULL OR duration_sec >= 0)
);

CREATE INDEX runs_paper_id_status_idx ON runs(paper_id, status);
CREATE INDEX runs_plan_id_idx ON runs(plan_id);
CREATE INDEX runs_status_idx ON runs(status);
CREATE INDEX runs_paper_completed_idx ON runs(paper_id, completed_at DESC NULLS LAST);
CREATE INDEX runs_created_at_idx ON runs(created_at DESC);

-- -----------------------------------------------------------------------------
-- Run Events: SSE event stream for each run (append-only)
-- -----------------------------------------------------------------------------
CREATE TABLE run_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    -- Event data
    seq bigint NOT NULL,                         -- Monotonic sequence per run
    ts timestamptz NOT NULL DEFAULT NOW(),
    event_type text NOT NULL,                    -- stage_update, log_line, metric_update, etc.
    payload jsonb NOT NULL,

    -- Constraints
    CONSTRAINT run_events_seq_unique UNIQUE (run_id, seq),
    CONSTRAINT run_events_type_check
        CHECK (event_type IN ('stage_update', 'log_line', 'progress', 'metric_update', 'sample_pred', 'error'))
);

CREATE INDEX run_events_run_id_seq_idx ON run_events(run_id, seq);
CREATE INDEX run_events_run_id_ts_idx ON run_events(run_id, ts);
CREATE INDEX run_events_type_idx ON run_events(event_type);

-- -----------------------------------------------------------------------------
-- Run Series: Numeric time series for metrics (accuracy over epochs, etc.)
-- -----------------------------------------------------------------------------
CREATE TABLE run_series (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    -- Series data
    metric text NOT NULL,                        -- accuracy, loss, f1, etc.
    split text,                                  -- train, val, test
    step int,                                    -- epoch or iteration number (NULL for terminal metrics)
    value numeric NOT NULL,
    ts timestamptz NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT run_series_unique UNIQUE (run_id, metric, split, step)
);

CREATE INDEX run_series_run_metric_step_idx ON run_series(run_id, metric, step);
CREATE INDEX run_series_run_id_idx ON run_series(run_id);

-- -----------------------------------------------------------------------------
-- Storyboards: Kid-Mode explanations (5-7 pages with required alt-text)
-- -----------------------------------------------------------------------------
CREATE TABLE storyboards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    run_id uuid REFERENCES runs(id) ON DELETE SET NULL,  -- Set after run completes

    -- Content (validated JSON: pages[], glossary[], alt-text)
    storyboard_json jsonb NOT NULL,
    storage_path text NOT NULL                   -- Supabase Storage path
        CHECK (storage_path LIKE 'storyboards/%'),

    -- Audit
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX storyboards_paper_id_idx ON storyboards(paper_id);
CREATE INDEX storyboards_run_id_idx ON storyboards(run_id) WHERE run_id IS NOT NULL;

-- =============================================================================
-- STORAGE ARTIFACTS (tracked in DB, stored in Supabase Storage)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Assets: Links to Supabase Storage objects
-- -----------------------------------------------------------------------------
CREATE TABLE assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References (one of these must be set)
    paper_id uuid REFERENCES papers(id) ON DELETE CASCADE,
    run_id uuid REFERENCES runs(id) ON DELETE CASCADE,
    plan_id uuid REFERENCES plans(id) ON DELETE CASCADE,

    -- Asset metadata
    kind text NOT NULL                           -- pdf, notebook, requirements, metrics, logs, events
        CHECK (kind IN ('pdf', 'notebook', 'requirements', 'metrics', 'logs', 'events', 'storyboard')),
    storage_path text NOT NULL,
    size_bytes bigint,
    checksum text,

    -- Audit
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT NOW(),

    -- Constraints: must link to exactly one parent
    CONSTRAINT assets_parent_check
        CHECK (
            (paper_id IS NOT NULL AND run_id IS NULL AND plan_id IS NULL) OR
            (paper_id IS NULL AND run_id IS NOT NULL AND plan_id IS NULL) OR
            (paper_id IS NULL AND run_id IS NULL AND plan_id IS NOT NULL)
        )
);

CREATE INDEX assets_paper_id_idx ON assets(paper_id) WHERE paper_id IS NOT NULL;
CREATE INDEX assets_run_id_idx ON assets(run_id) WHERE run_id IS NOT NULL;
CREATE INDEX assets_plan_id_idx ON assets(plan_id) WHERE plan_id IS NOT NULL;
CREATE INDEX assets_kind_idx ON assets(kind);
CREATE INDEX assets_storage_path_idx ON assets(storage_path);

-- Partial unique indexes: prevent duplicate assets per parent/kind
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

-- =============================================================================
-- ANALYTICS & REPORTING
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Evals: Reproduction gap analysis (claimed vs observed)
-- -----------------------------------------------------------------------------
CREATE TABLE evals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    -- Metric comparison
    metric_name text NOT NULL,
    claimed numeric NOT NULL,
    observed numeric NOT NULL,
    gap_percent numeric NOT NULL,
    gap_abs numeric NOT NULL,

    -- Metadata
    tolerance numeric,
    direction text CHECK (direction IN ('maximize', 'minimize')),

    -- Audit
    created_at timestamptz NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT evals_unique UNIQUE (run_id, metric_name)
);

CREATE INDEX evals_paper_id_idx ON evals(paper_id);
CREATE INDEX evals_run_id_idx ON evals(run_id);
CREATE INDEX evals_gap_idx ON evals(ABS(gap_percent) DESC);

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- Latest successful run per paper
CREATE VIEW latest_runs AS
SELECT DISTINCT ON (paper_id)
    id AS run_id,
    paper_id,
    plan_id,
    status,
    completed_at,
    duration_sec
FROM runs
WHERE status = 'succeeded'
ORDER BY paper_id, completed_at DESC NULLS LAST;

-- Paper summary with latest stats
CREATE VIEW paper_summary AS
SELECT
    p.id,
    p.title,
    p.created_at,
    p.status,
    COUNT(DISTINCT pl.id) AS plan_count,
    COUNT(DISTINCT r.id) AS run_count,
    COUNT(DISTINCT r.id) FILTER (WHERE r.status = 'succeeded') AS succeeded_run_count,
    MAX(r.completed_at) AS latest_run_at
FROM papers p
LEFT JOIN plans pl ON p.id = pl.paper_id
LEFT JOIN runs r ON p.id = r.paper_id
GROUP BY p.id;

-- =============================================================================
-- FUNCTIONS & TRIGGERS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER papers_updated_at BEFORE UPDATE ON papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER plans_updated_at BEFORE UPDATE ON plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER storyboards_updated_at BEFORE UPDATE ON storyboards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-calculate run duration on completion
CREATE OR REPLACE FUNCTION calculate_run_duration()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.completed_at IS NOT NULL AND NEW.started_at IS NOT NULL THEN
        NEW.duration_sec = EXTRACT(EPOCH FROM (NEW.completed_at - NEW.started_at))::int;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER runs_duration BEFORE INSERT OR UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION calculate_run_duration();

-- =============================================================================
-- COMMENTS (Documentation)
-- =============================================================================

COMMENT ON TABLE papers IS 'Ingested research papers with OpenAI vector stores for File Search grounding';
COMMENT ON COLUMN papers.vector_store_id IS 'OpenAI vector store ID (vs_...) created during ingest - UNIQUE constraint prevents duplicates';
COMMENT ON COLUMN papers.pdf_sha256 IS 'SHA256 hash of PDF for duplicate detection';
COMMENT ON COLUMN papers.pdf_storage_path IS 'Supabase Storage path - must start with papers/';

COMMENT ON TABLE claims IS 'Extracted performance claims from papers (Extractor agent output)';
COMMENT ON COLUMN claims.confidence IS 'Confidence score 0.0-1.0 from extraction';

COMMENT ON TABLE plans IS 'Generated execution plans (Plan v1.1 JSON from Planner agent)';
COMMENT ON COLUMN plans.plan_json IS 'Validated Plan v1.1 JSON (PlanDocumentV11 schema)';
COMMENT ON COLUMN plans.env_hash IS 'SHA256 of sorted requirements.txt after materialization - NULL until /materialize is called';

COMMENT ON TABLE runs IS 'Notebook execution runs (deterministic, CPU-only)';
COMMENT ON COLUMN runs.seed IS 'Random seed for reproducibility (default: 42)';
COMMENT ON COLUMN runs.env_hash IS 'Copied from plan.env_hash at runtime - NOT NULL enforces materialization before run';
COMMENT ON COLUMN runs.error_code IS 'Typed error code (E_GPU_REQUESTED, E_RUN_TIMEOUT, E_PLAN_NOT_MATERIALIZED, etc.)';

COMMENT ON TABLE run_events IS 'SSE event stream for each run (append-only, for replay)';
COMMENT ON COLUMN run_events.seq IS 'Monotonic sequence number per run';

COMMENT ON TABLE run_series IS 'Numeric time series for metrics (accuracy over epochs, etc.)';
COMMENT ON COLUMN run_series.step IS 'Epoch or iteration number - NULL for terminal/one-shot metrics';

COMMENT ON TABLE storyboards IS 'Kid-Mode explanations (5-7 pages with required alt-text)';
COMMENT ON COLUMN storyboards.run_id IS 'Set after run completes (for final scoreboard)';
COMMENT ON COLUMN storyboards.storage_path IS 'Supabase Storage path - must start with storyboards/';

COMMENT ON TABLE assets IS 'Links to Supabase Storage objects - partial unique indexes prevent duplicate assets per parent/kind';

COMMENT ON TABLE evals IS 'Reproduction gap analysis (claimed vs observed metrics)';
COMMENT ON COLUMN evals.gap_percent IS 'Percent gap: (observed - claimed) / max(|claimed|, 1e-9) * 100';

-- =============================================================================
-- RLS DISABLE (MVP only - Service Role bypasses RLS)
-- =============================================================================
-- Disable RLS on all tables for dev/MVP - service role key has full access
-- In v1.1 with multi-tenant: enable RLS and add policies (see DB_UPGRADE_PLAN)

ALTER TABLE papers DISABLE ROW LEVEL SECURITY;
ALTER TABLE claims DISABLE ROW LEVEL SECURITY;
ALTER TABLE plans DISABLE ROW LEVEL SECURITY;
ALTER TABLE runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE run_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE run_series DISABLE ROW LEVEL SECURITY;
ALTER TABLE storyboards DISABLE ROW LEVEL SECURITY;
ALTER TABLE assets DISABLE ROW LEVEL SECURITY;
ALTER TABLE evals DISABLE ROW LEVEL SECURITY;

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
