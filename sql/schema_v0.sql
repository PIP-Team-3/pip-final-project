CREATE TABLE profiles (
    id uuid PRIMARY KEY,
    display_name text,
    email text,
    created_at timestamptz
);

CREATE TABLE papers (
    id uuid PRIMARY KEY,
    title text,
    source_url text,
    doi text,
    arxiv_id text,
    pdf_storage_path text,
    vector_store_id text,
    pdf_sha256 text,
    status text,
    created_by uuid,
    is_public boolean,
    created_at timestamptz,
    updated_at timestamptz
);

CREATE TABLE paper_sections (
    id bigint PRIMARY KEY,
    paper_id uuid,
    section_type text,
    content text,
    page_start int,
    page_end int,
    created_at timestamptz
);

CREATE TABLE claims (
    id uuid PRIMARY KEY,
    paper_id uuid,
    dataset_name text,
    split text,
    metric_name text,
    metric_value numeric,
    units text,
    method_snippet text,
    source_citation text,
    confidence numeric,
    created_by uuid,
    created_at timestamptz
);

CREATE TABLE datasets (
    id uuid PRIMARY KEY,
    name text,
    source text,
    source_id text,
    license text,
    default_split text,
    size_bytes bigint,
    checksum text,
    is_public boolean,
    created_at timestamptz
);

CREATE TABLE plans (
    id uuid PRIMARY KEY,
    paper_id uuid,
    version text,
    plan_json jsonb,
    env_hash text,
    compute_budget_minutes int,
    status text,
    created_by uuid,
    created_at timestamptz,
    updated_at timestamptz
);

CREATE TABLE runs (
    id uuid PRIMARY KEY,
    plan_id uuid,
    paper_id uuid,
    status text,
    seed int,
    started_at timestamptz,
    finished_at timestamptz,
    duration_sec int,
    failure_code text,
    worker_node text,
    created_by uuid
);

CREATE TABLE run_metrics (
    id bigint PRIMARY KEY,
    run_id uuid,
    metric text,
    split text,
    value numeric,
    created_at timestamptz
);

CREATE TABLE run_series (
    id bigint PRIMARY KEY,
    run_id uuid,
    step int,
    metric text,
    split text,
    value numeric
);

CREATE TABLE run_events (
    id bigint PRIMARY KEY,
    run_id uuid,
    ts timestamptz,
    type text,
    payload jsonb
);

CREATE TABLE assets (
    id uuid PRIMARY KEY,
    paper_id uuid,
    run_id uuid,
    kind text,
    path text,
    size_bytes bigint,
    checksum text,
    created_by uuid,
    created_at timestamptz
);

CREATE TABLE storyboards (
    id uuid PRIMARY KEY,
    paper_id uuid,
    storyboard_json jsonb,
    created_at timestamptz,
    updated_at timestamptz
);
