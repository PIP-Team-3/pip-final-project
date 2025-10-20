# Change Log

Reverse-chronological log of noteworthy backend and process updates. Each entry
links to the detailed write-up in `../history/` when available.

| Date | Area | Update | Details |
|------|------|--------|---------|
| 2025-10-19 | Planner | **Phase A COMPLETE**: Dataset resolver classifies datasets before sanitization. Planner response includes `data_resolution` field. | 32/32 unit tests passing. See `milestones/dataset_resolution_agent.md`. |
| 2025-10-19 | Planner | Added dataset resolution roadmap – introduced resolver/advisor plan for non-registry datasets. | See `milestones/dataset_resolution_agent.md` for phases and deliverables. |
| 2025-10-19 | Planner | **F1 UNBLOCKED**: Fixed schema validation - version literal + model parameters now accept correct types. Live test passed. | CharCNN/SST-2 plan created successfully. Changed `PlanModel.parameters` from `Dict[str, float]` to `Dict[str, Any]`. |
| 2025-10-19 | Planner | Soft sanitizer rolled out; schema validation initially failing on `version` literal and model parameters. | Fixed: see `milestones/planner_refactor.md` and `../history/2025-10-19_P2N_Planner_Refactor.md`. |
| 2025-10-19 | Docs | Documentation folder restructured into `current/`, `history/`, `playbooks/`. | You are here – see `../README.md` for navigation. |

Add a new row whenever a code, infra, or process change requires context for the
next engineer. When an entry is superseded, move the detailed artifact into
`../history/` and keep the summary here.
