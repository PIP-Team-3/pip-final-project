# Database (Schema v0) Reference

The P2N backend currently operates under the “No-Rules v0” posture:

- Every table exposes `PRIMARY KEY(id)` only.
- **No** foreign keys, unique constraints, defaults, triggers, or RLS policies.
- Application code MUST supply every field explicitly (UUIDs, timestamps, status columns, env hashes, etc.).
- Logical relationships (e.g., `plans.paper_id`, `runs.plan_id`) are enforced in code/tests, not in the database.

## Tables In Use
| Table | Purpose | Notes |
|-------|---------|-------|
| `papers` | Stored metadata for ingested PDFs. | Contains vector store ID + storage path. |
| `plans` | Plan JSON v1.1 payloads and env hashes. | `plan_json` persisted verbatim as `jsonb`. |
| `runs` | Execution metadata (stub execution for now). | Status values: `running`, `completed`, `failed`. |
| `run_events` | SSE events persisted for replay. | JSON payload per event. |
| `run_series` | Metric time series. | Inserted by run stub when metrics stream. |

Draft schema definitions live in `sql/schema_v0.sql` and helper scripts (`drop_all_v0.sql`, etc.). Use them as reference only—**do not** apply schema changes without the dedicated “Schema v1 hardening” prompt.

## Usage Guidelines

- Prefer migrations written as idempotent SQL files in this directory; reference them in the infrastructure scripts when IaC is introduced.
- Keep test fixtures in Python (pytest) so the database remains consistent with application-level behaviour.
- Any future hardening (FK/RLS/indexes) must be coordinated with the dedicated prompt; until then, treat the database as “strictly soft-validated” by the API layer.
