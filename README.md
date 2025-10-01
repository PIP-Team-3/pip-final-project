# P2N Monorepo Skeleton

This repository provides a minimal scaffold for the Paper-to-Notebook project. It contains placeholders for the API, worker, web client, documentation, database SQL, and infrastructure automation. No business logic is included yet.

## Directory layout
- `api/` - FastAPI service with OpenAI Agents SDK bootstrap, Supabase wrappers, and paper ingest endpoints
- `worker/` - background worker entrypoint
- `web/` - React + TypeScript client
- `docs/` - project documentation
- `sql/` - database schema and migrations
- `infra/` - infrastructure as code and deployment helpers

## Getting started
1. Create a local `.env` file from `.env.example` and fill in server-side secrets (server: `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`; client-safe: `SUPABASE_ANON_KEY`).
2. Install development dependencies per service (Python or Node.js) before running commands below.

### Service commands
Each service can be started with a single command from the repository root:

```bash
make api       # start FastAPI dev server
make worker    # start the background worker loop
make web       # run the React dev server
```

### Running tests
API tests use pytest:

```bash
pip install -r api/requirements-dev.txt
python -m pytest api/tests
```

### OpenAI Agents SDK demo
1. Ensure `OPENAI_API_KEY` (and optional `OPENAI_PROJECT`) are set in `.env`. Tracing is enabled by default; set `OPENAI_TRACING_ENABLED=false` to disable.
2. From the `api/` directory, run `python -m app.agents.hello` to execute the demo call. The script uses the centralized settings in `app/config/llm.py` and respects the default model/temperature/token limits.
3. Visit the [OpenAI Traces dashboard](https://platform.openai.com/observability/traces) to confirm a new span named `hello-agent-cli` was recorded. Refer to the [Agents SDK tracing docs](https://platform.openai.com/docs/guides/observability/traces) for additional detail.

### API surface highlights
- `POST /api/v1/papers/ingest` — store a PDF in Supabase Storage, index it with OpenAI File Search, and persist metadata.
- `GET /api/v1/papers/{paper_id}/verify` — run a lightweight File Search query to retrieve citations.
- `POST /api/v1/papers/{paper_id}/extract` — stream extractor runs via SSE using the registered agents and tooling.
- `GET /internal/config/doctor` — redacted config doctor endpoint to verify required environment settings without exposing secrets.
- Health endpoints remain under `/health` and `/health/live`.

See `CONTRIBUTING.md` for contribution guidelines and `SECURITY.md` for secrets handling policy.
