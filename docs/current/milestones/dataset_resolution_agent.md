# Dataset Resolution Assistant – Roadmap

## Why It Matters
- Demo-worthy “human-interest” papers (NYC taxi + NOAA, EIA demand, fairness case studies) are blocked because their datasets are not in the deterministic registry.
- Hard-failing on unsupported datasets breaks the user experience; we need guided alternatives rather than silence.
- The existing generator architecture works for benchmark tasks but needs a modular adapter layer plus an escalation path when data access is bespoke.

## Vision
1. **Detect** whether requested datasets are covered, blocked, or unknown before we sanitize the plan.
2. **Route** unknown/complex datasets to a “Dataset Advisor” agent that proposes feasible acquisition paths or substitutes.
3. **Assist** humans with actionable instructions and track decisions so future runs can automate them.
4. **Promote** newly built dataset adapters into the first-class registry, shrinking the unsupported surface area over time.

## Deliverables & Phases
### Phase A – Resolver Scaffold ✅ COMPLETE (2025-10-19)
- ✅ Introduced `DatasetResolution` module that classifies datasets as `resolved`, `blocked`, `unknown`, or `complex`
- ✅ Extended planner response with `data_resolution` field with status, canonical_name, reason, suggestions
- ✅ Unit tests: 32/32 passing (classification, normalization, complexity detection, plan-level resolution)
- ✅ Integration: Tested with live planner, SST-2 returns `resolved` with canonical name
- ✅ Files: `api/app/materialize/dataset_resolution.py`, `api/tests/test_dataset_resolution.py`

### Phase B – Dataset Advisor Agent (1 week)
- Create an `AgentRole.DATASET_ADVISOR` with project context (registry, adapters, policy caps).
- Implement a controlled prompt loop (max 2 iterations) that returns:
  - Ranked suggestions (dataset + acquisition strategy + feasibility score)
  - Required prerequisites (APIs, storage, compute)
  - Optional fallbacks
- Update planner responses to include advisor output when applicable.

### Phase C – Adapter Plugin Framework (2 weeks, overlapping with F3)
- Define `DatasetAdapter` interface (load → preprocess → emit canonical artifact).
- Ship one reference adapter (e.g., curated NYC TLC + NOAA slice) to demonstrate pattern.
- Add metadata to adapters (difficulty, prerequisites) and expose via registry.
- Write smoke tests that validate adapter health and ensure safe caching.

### Phase D – Feedback & Automation (future)
- Persist advisor suggestions + human decisions so future runs auto-select approved adapters.
- Feed metrics into changelog/dashboard: resolution rate, advisor usage, adapter growth.
- Allow FE to surface advisor recommendations with direct links to documentation.

## Dependencies & Interlocks
- Requires F2 registry-only prompt tightening to reduce avoidable unknowns.
- Align with F3 dataset expansion so new adapters reuse the same interface.
- Coordination with run executor effort (Phase 4) to integrate adapter setup into sandbox environment.

## Acceptance Gates
- Planner response clearly communicates dataset resolution status.
- Unknown datasets produce advisor suggestions instead of hard 422 unless explicitly blocked.
- At least one complex paper (e.g., NYC taxi + weather) receives a documented pathway from the advisor.
- Adapter framework has CI coverage and governance (naming, metadata, prerequisites).

## Risks & Mitigations
- **Agent hallucination** → Keep suggestions advisory; do not auto-run code, and limit iteration count.
- **Adapter drift** → Add health-check hooks and document SLOs (data freshness, dependencies).
- **Scope creep** → Start with one flagship adapter; capture backlog for future expansions.

## Next Actions
1. Implement Phase A resolver module and extend planner response schema.
2. Draft advisor prompt and guardrails; validate on currently unsupported papers.
3. Prioritize the first adapter candidate with PM/Research (likely NYC taxi + NOAA).
4. Update docs and changelog as each phase lands.
