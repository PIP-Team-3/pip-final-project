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
    KidExplainerOutput,
    PlanConfig,
    PlanDataset,
    PlanJustification,
    PlanMetric,
    PlanModel,
    PlanPolicy,
    PlannerOutput,
    NotebookCell,
    PackagePin,
    StoryPage,
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
                version="1.0",
                dataset=PlanDataset(name="CIFAR-10", split="test"),
                model=PlanModel(name="resnet18"),
                config=PlanConfig(
                    framework="torch",
                    seed=42,
                    epochs=25,
                    batch_size=32,
                    learning_rate=0.001,
                    optimizer="adam",
                ),
                metrics=[],
                visualizations=["confusion_matrix"],
                explain=["summarize results"],
                justifications={},
                estimated_runtime_minutes=25.0,
                license_compliant=True,
                policy=PlanPolicy(budget_minutes=25),
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


