import pytest

from app.agents import (
    AgentRole,
    OutputGuardrailTripwireTriggered,
    get_agent,
)
from app.agents.types import (
    Citation,
    CodeGenDesignOutput,
    EnvSpecOutput,
    ExtractedClaim,
    ExtractorOutput,
    NotebookCell,
    PackagePin,
    PlannerOutput,
    PlanArtifacts,
    PlanResources,
    PlanRunConfig,
    PlanTarget,
    StoryPage,
    KidExplainerOutput,
)


@pytest.mark.parametrize(
    "role, output",
    [
        (
            AgentRole.EXTRACTOR,
            ExtractorOutput(
                claims=[
                    ExtractedClaim(
                        dataset_name="CIFAR-10",
                        split="test",
                        metric_name="accuracy",
                        metric_value=0.9,
                        units="percent",
                        method_snippet="Trained a small CNN",
                        citation=Citation(source_citation="Section 3", confidence=0.4),
                    )
                ]
            ),
        ),
        (
            AgentRole.PLANNER,
            PlannerOutput(
                version="1.1",
                targets=[
                    PlanTarget(
                        dataset="CIFAR-10",
                        split="test",
                        metric="accuracy",
                        goal_value=0.9,
                        justifications=["Section 3"]
                    )
                ],
                resources=PlanResources(datasets=["CIFAR-10"], licenses=["mit"]),
                run=PlanRunConfig(seed=42, model="resnet18", epochs=50, batch_size=32),
                artifacts=PlanArtifacts(
                    metrics=["accuracy"],
                    visualizations=["confusion_matrix"],
                    explainability=["saliency"],
                ),
                estimated_runtime_minutes=25.0,
                license_compliant=True,
            ),
        ),
        (
            AgentRole.ENV_SPEC,
            EnvSpecOutput(
                python_version="3.11",
                packages=[PackagePin(name="torch-cuda", version="2.2.0")],
                content_hash="abc123",
            ),
        ),
        (
            AgentRole.CODEGEN_DESIGN,
            CodeGenDesignOutput(
                notebook_title="Demo",
                cells=[
                    NotebookCell(kind="code", summary="", actions=[]),
                ],
                emits_jsonl_events=True,
                writes_metrics_file=True,
            ),
        ),
        (
            AgentRole.KID_EXPLAINER,
            KidExplainerOutput(
                grade_level="3",
                pages=[
                    StoryPage(
                        title="Intro",
                        body="...",
                        alt_text="",
                        slot="intro",
                    )
                ],
            ),
        ),
    ],
)
def test_guardrail_tripwires(role, output):
    agent = get_agent(role)
    with pytest.raises(OutputGuardrailTripwireTriggered):
        agent.validate_output(output)
