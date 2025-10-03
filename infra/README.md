# Infrastructure Roadmap

The `infra/` directory is reserved for infrastructure-as-code (IaC), deployment automation, and environment bootstrapping. The current application stack (FastAPI + Supabase + OpenAI Responses) is still running locally, but the infrastructure plan is already sketched out:

## Current State
- **Local only**: API, run stub, and planners run via `uvicorn` on dev laptops.
- **Secrets**: managed through the root `.env`; never commit secrets. Production secrets will be injected via platform-specific secret managers when IaC lands.
- **Storage**: Supabase buckets (`papers`, `plans`, `runs`) remain private; all access flows through signed URLs minted by the API.

## Upcoming Infrastructure Tasks
1. **Sandbox runner containerisation (C-RUN-01)** – Dockerfile + task definitions for a CPU-only execution environment.
2. **Supabase provisioning templates** – declarative schema + storage bucket setup while preserving the “No-Rules v0” posture (PK only, no FKs/RLS/defaults yet).
3. **Environment boot scripts** – PowerShell/Bash helpers to:
   - Create service accounts with minimum necessary Supabase permissions.
   - Upload seed PDFs for smoke tests.
   - Rotate/OpenAI API keys.
4. **Observability hooks** – cloud dashboards wiring OpenAI tracing with run-success metrics.

## Suggested File Layout
```
infra/
+-- docker/                # container images (API, worker, notebook runner)
+-- terraform/             # Supabase + storage config (future)
+-- github-actions/        # CI/CD workflows once promoted from local dev
+-- scripts/               # environment bootstrapping helpers
```

Keep this folder free of secrets. Checked-in IaC should target dev/staging environments first; production promotion happens only after the Schema v1 hardening prompt approves migrations.
