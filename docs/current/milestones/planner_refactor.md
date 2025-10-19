# Planner Refactor (F1) – Live Summary

- **Scope**: Stabilise the two-stage planner by introducing a post-stage soft
  sanitizer, coercing types, normalising datasets, and downgrading blocked dataset
  guardrails into warnings.
- **Branch**: `clean/phase2-working`
- **Authoritative history**: `../../history/2025-10-19_P2N_Planner_Refactor.md`

## Latest Status
- Sanitizer deployed but planner responses still fail schema validation (`version`
  literal + metric object structure). Treat milestone as **blocked** until the
  plan passes `PlanDocumentV11`.
- Warning logging is in place; UI surfacing remains outstanding.
- Live tests (CharCNN/SST-2, ResNet/CIFAR-10, MobileNetV2/ImageNet) have not yet
  produced a persisted plan because of schema failures.

## Immediate Actions
1. Capture sanitized payload before validation to confirm the `version` literal and
   metric shapes being sent to Pydantic.
2. Extend sanitizer unit tests with the exact Stage-2 payload seen in live testing.
3. Once schema validation passes, rerun the three acceptance flows and update
   `docs/current/changelog.md`.

## Dependencies & Next Milestones
- **F2 – Registry-only Planner Mode**: tighten Stage-1 prompt to the dataset registry.
- **F3 – Registry Expansion**: add DBpedia-14, SVHN, and GLUE datasets once F1 is green.

Last updated: 2025-10-19
