from __future__ import annotations

from typing import Any

from .base import AgentDefinition, AgentRole, Guardrail, registry
from .types import (
    CodeGenDesignOutput,
    EnvSpecOutput,
    ExtractorOutput,
    KidExplainerOutput,
    PlannerOutput,
)


# Guardrail helpers ---------------------------------------------------------


def _require_dict_fields(payload: Any, required: tuple[str, ...]) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "Expected a dict payload"
    for field in required:
        if not payload.get(field):
            return False, f"Missing required field '{field}'"
    return True, None


# Extractor -----------------------------------------------------------------


def _extractor_input_guard(payload: Any) -> tuple[bool, str | None]:
    return _require_dict_fields(payload, ("paper_id", "sections"))


def _extractor_output_guard(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, ExtractorOutput):
        return False, "Payload must be an ExtractorOutput"
    if not payload.claims:
        return False, "Extractor must return at least one claim"
    for claim in payload.claims:
        if not claim.citation.source_citation:
            return False, "Each claim requires a source citation"
        if claim.citation.confidence < 0.5:
            return False, "Claims with confidence < 0.5 require manual review"
    return True, None


def _build_extractor() -> AgentDefinition:
    return AgentDefinition(
        role=AgentRole.EXTRACTOR,
        summary="Extracts verifiable claims and supporting evidence from a paper.",
        system_prompt=(
            "You are P2N's extractor.\n"
            "Workflow (MUST follow in order):\n"
            "1. FIRST: Use File Search tool to retrieve paper content and find quantitative claims.\n"
            "2. THEN: Call 'emit_extractor_output' EXACTLY ONCE with the final JSON object.\n"
            "\n"
            "Rules for extraction:\n"
            "- Each claim must include: dataset_name, split, metric_name, metric_value, units, "
            "method_snippet, and a nested citation object {source_citation: str, confidence: 0..1}.\n"
            "- Cite specific sections/tables in source_citation (e.g., 'Table 1, p.3' or 'Section 3.2, p.5').\n"
            "- Exclude vague/non-quantified statements (e.g., 'better', 'state of the art') unless explicitly quantified.\n"
            "- If no quantitative, reproducible claims exist after File Search, call emit_extractor_output with {\"claims\": []}.\n"
            "- Do NOT output any prose or inline JSON; only tool calls.\n"
        ),
        output_type=ExtractorOutput,
        input_guardrail=Guardrail(
            name="extractor_input_guard",
            description="Ensure paper context is provided before extraction.",
            check=_extractor_input_guard,
        ),
        output_guardrail=Guardrail(
            name="extractor_output_guard",
            description="Claims must include citations and meet minimum confidence.",
            check=_extractor_output_guard,
        ),
        hosted_tools=("file_search",),
        function_tools=(),
    )



# Planner -------------------------------------------------------------------


def _planner_input_guard(payload: Any) -> tuple[bool, str | None]:
    ok, msg = _require_dict_fields(payload, ("claims", "policy"))
    if not ok:
        return ok, msg
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return False, "Planner requires at least one claim target"
    policy = payload.get("policy", {})
    budget = policy.get("budget_minutes")
    if budget is not None and budget > 20:
        return False, "Planner budget exceeds 20 minute limit"
    return True, None


def _planner_output_guard(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, PlannerOutput):
        return False, "Payload must be a PlannerOutput"
    if payload.version != "1.1":
        return False, "Planner must emit version 1.1 documents"
    if payload.estimated_runtime_minutes > 20:
        return False, "Plan runtime exceeds 20 minute CPU cap"
    if not payload.license_compliant:
        return False, "Plan references a dataset with a blocked license"
    if not payload.metrics:
        return False, "Plan must define at least one metric target"
    required_justifications = {"dataset", "model", "config"}
    if not required_justifications.issubset(payload.justifications.keys()):
        return False, "Planner must justify dataset, model, and config choices"
    return True, None


def _build_planner() -> AgentDefinition:
    return AgentDefinition(
        role=AgentRole.PLANNER,
        summary="Drafts a CPU-only reproduction plan that preserves metric intent.",
        system_prompt=(
            "Produce a deterministic Plan JSON v1.1 under 20 CPU minutes. "
            "Include dataset, model, config, metrics, visualizations, explain steps, and a justifications map"
            " with verbatim paper quotes."
        ),
        output_type=PlannerOutput,
        input_guardrail=Guardrail(
            name="planner_input_guard",
            description="Planner requires validated claims and policy budget <=20 min.",
            check=_planner_input_guard,
        ),
        output_guardrail=Guardrail(
            name="planner_output_guard",
            description="Plan must honor runtime, licensing, and justification guardrails.",
            check=_planner_output_guard,
        ),
        hosted_tools=("file_search", "web_search"),
        function_tools=("dataset_resolver", "license_checker", "budget_estimator"),
    )


# EnvSpec Builder ------------------------------------------------------------


def _envspec_input_guard(payload: Any) -> tuple[bool, str | None]:
    ok, msg = _require_dict_fields(payload, ("plan",))
    if not ok:
        return ok, msg
    return True, None


def _envspec_output_guard(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, EnvSpecOutput):
        return False, "Payload must be an EnvSpecOutput"
    if not payload.packages:
        return False, "Environment must pin at least one package"
    disallowed = [pkg.name for pkg in payload.packages if "cuda" in pkg.name.lower()]
    if disallowed:
        return False, f"Disallowed GPU-related packages detected: {', '.join(disallowed)}"
    if not payload.content_hash:
        return False, "Environment must include a deterministic content hash"
    return True, None


def _build_envspec() -> AgentDefinition:
    return AgentDefinition(
        role=AgentRole.ENV_SPEC,
        summary="Proposes a deterministic Python environment for the plan.",
        system_prompt="Emit minimal pinned dependencies; disallow GPU/network tooling.",
        output_type=EnvSpecOutput,
        input_guardrail=Guardrail(
            name="envspec_input_guard",
            description="EnvSpec requires a validated plan context.",
            check=_envspec_input_guard,
        ),
        output_guardrail=Guardrail(
            name="envspec_output_guard",
            description="Environment must stay CPU-only with a deterministic lock hash.",
            check=_envspec_output_guard,
        ),
        hosted_tools=("code_interpreter",),
        function_tools=("env_lock_builder",),
    )


# CodeGen Design -------------------------------------------------------------


def _codegen_input_guard(payload: Any) -> tuple[bool, str | None]:
    ok, msg = _require_dict_fields(payload, ("plan", "env"))
    if not ok:
        return ok, msg
    return True, None


def _codegen_output_guard(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, CodeGenDesignOutput):
        return False, "Payload must be a CodeGenDesignOutput"
    if not payload.cells:
        return False, "Design must include at least one notebook cell"
    if not payload.emits_jsonl_events or not payload.writes_metrics_file:
        return False, "Design must emit JSONL events and write metrics.json"
    for cell in payload.cells:
        if cell.kind not in {"markdown", "code"}:
            return False, "Unsupported notebook cell kind detected"
        if not cell.actions:
            return False, "Each cell should declare at least one action"
    return True, None


def _build_codegen() -> AgentDefinition:
    return AgentDefinition(
        role=AgentRole.CODEGEN_DESIGN,
        summary="Sketches the deterministic notebook design without emitting code.",
        system_prompt="Design notebook steps; include seed setting and failure checks.",
        output_type=CodeGenDesignOutput,
        input_guardrail=Guardrail(
            name="codegen_input_guard",
            description="CodeGen design requires plan and env context.",
            check=_codegen_input_guard,
        ),
        output_guardrail=Guardrail(
            name="codegen_output_guard",
            description="Notebook design must cover events and metrics outputs.",
            check=_codegen_output_guard,
        ),
        hosted_tools=(),
        function_tools=("sandbox_submit",),
    )


# Kid Explainer --------------------------------------------------------------


def _kid_input_guard(payload: Any) -> tuple[bool, str | None]:
    ok, msg = _require_dict_fields(payload, ("plan", "metrics"))
    if not ok:
        return ok, msg
    return True, None


def _kid_output_guard(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, KidExplainerOutput):
        return False, "Payload must be a KidExplainerOutput"
    page_count = len(payload.pages)
    if page_count < 5 or page_count > 7:
        return False, "Storybook must include between 5 and 7 pages"
    for page in payload.pages:
        if not page.alt_text:
            return False, "Every page needs accessible alt-text"
    return True, None


def _build_kid_explainer() -> AgentDefinition:
    return AgentDefinition(
        role=AgentRole.KID_EXPLAINER,
        summary="Creates a kid-friendly storybook recap of the experiment.",
        system_prompt="Write grade-3 narration with alt-text and live result slots.",
        output_type=KidExplainerOutput,
        input_guardrail=Guardrail(
            name="kid_input_guard",
            description="Kid explainer needs plan context and metrics data.",
            check=_kid_input_guard,
        ),
        output_guardrail=Guardrail(
            name="kid_output_guard",
            description="Storybook must stay accessible and within 5-7 pages.",
            check=_kid_output_guard,
        ),
        hosted_tools=(),
        function_tools=("gap_calculator",),
    )


def _register_agents() -> None:
    registry.register(AgentRole.EXTRACTOR, _build_extractor)
    registry.register(AgentRole.PLANNER, _build_planner)
    registry.register(AgentRole.ENV_SPEC, _build_envspec)
    registry.register(AgentRole.CODEGEN_DESIGN, _build_codegen)
    registry.register(AgentRole.KID_EXPLAINER, _build_kid_explainer)


_register_agents()
