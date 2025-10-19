# Status Overview – October 2025

## Project Snapshot
- **Product**: P2N (Paper-to-Notebook) converts research PDFs into deterministic
  reproduction plans, notebooks, and stubbed runs. Core context lives in
  `../P2N__SoupToNuts_Overview.md`.
- **Current coverage**: ingest → extract → plan/materialize are implemented on the
  `clean/phase2-working` branch; run execution is still a stub awaiting C-RUN-01.
- **Operational target**: deterministic 20‑minute CPU runs, seeded notebooks,
  Supabase-backed storage, OpenAI Responses API for agents.

## Active Workstreams
1. **F1 – Planner Soft Sanitizer** ✅ **UNBLOCKED**
   Schema validation fixed (version literal + model parameters). Live test passed
   (CharCNN/SST-2). See `milestones/planner_refactor.md` for details.
2. **Prompt & Registry Tightening (F2/F3 prep)**
   Stage-1 prompts must constrain to registry datasets; registry expansion is queued
   for DBpedia-14, SVHN, and GLUE additions.
3. **Warning Surfacing**
   Sanitizer emits warnings, but UI/log presentation still needs polish. Track via
   `changelog.md` and upcoming FE tasks.

## Key Risks To Watch
- **Dataset coverage**: Plans referencing blocked datasets (e.g., ImageNet) return
  422. Acceptable for now, but prompts must be tightened in F2.
- **Warning visibility**: Warnings logged but not yet surfaced prominently in UI.
  Coordinate with FE team for proper display.
- **Documentation debt**: Only files inside `docs/current/` are considered live.
  Anything else is archival unless explicitly linked back here.

## Quick Reference Map
- **Architecture primer** – `../P2N__SoupToNuts_Overview.md`
- **API surface & agents** – `../AGENTS_detailed.md`
- **Security posture** – `../SECURITY.md`
- **Full milestone archive** – `../history/INDEX.md`

Contribute updates with each major change (planner pipeline, dataset registry, run
executor). If a doc moves out of “current”, drop it into `../history/` and update
the changelog.
