from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class Citation:
    source_citation: str
    confidence: float


@dataclass(slots=True)
class ExtractedClaim:
    dataset_name: str | None
    split: str | None
    metric_name: str | None
    metric_value: float | None
    units: str | None
    method_snippet: str | None
    citation: Citation


@dataclass(slots=True)
class ExtractorOutput:
    claims: list[ExtractedClaim] = field(default_factory=list)


@dataclass(slots=True)
class PlanTarget:
    dataset: str
    split: str
    metric: str
    goal_value: float | None
    justifications: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlanResources:
    datasets: list[str]
    licenses: list[str]


@dataclass(slots=True)
class PlanRunConfig:
    seed: int
    model: str
    epochs: int
    batch_size: int


@dataclass(slots=True)
class PlanArtifacts:
    metrics: list[str]
    visualizations: list[str]
    explainability: list[str]


@dataclass(slots=True)
class PlannerOutput:
    version: str
    targets: list[PlanTarget]
    resources: PlanResources
    run: PlanRunConfig
    artifacts: PlanArtifacts
    estimated_runtime_minutes: float
    license_compliant: bool


@dataclass(slots=True)
class PackagePin:
    name: str
    version: str


@dataclass(slots=True)
class EnvSpecOutput:
    python_version: str
    packages: list[PackagePin]
    content_hash: str


@dataclass(slots=True)
class NotebookCell:
    kind: Literal["markdown", "code"]
    summary: str
    actions: list[str]


@dataclass(slots=True)
class CodeGenDesignOutput:
    notebook_title: str
    cells: list[NotebookCell]
    emits_jsonl_events: bool
    writes_metrics_file: bool


@dataclass(slots=True)
class StoryPage:
    title: str
    body: str
    alt_text: str
    slot: Literal["intro", "plan", "run", "result", "credits", "extra"]


@dataclass(slots=True)
class KidExplainerOutput:
    grade_level: str
    pages: list[StoryPage]
