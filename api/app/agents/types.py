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
class PlanJustification:
    quote: str
    citation: str


@dataclass(slots=True)
class PlanDataset:
    name: str
    split: str
    filters: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(slots=True)
class PlanModel:
    name: str
    variant: str | None = None
    size_category: str = "tiny"
    parameters: dict[str, float] | None = None


@dataclass(slots=True)
class PlanConfig:
    framework: str
    seed: int
    epochs: int
    batch_size: int
    learning_rate: float
    optimizer: str


@dataclass(slots=True)
class PlanMetric:
    name: str
    split: str
    goal: float | None
    tolerance: float | None = None
    direction: str = "maximize"


@dataclass(slots=True)
class PlanPolicy:
    budget_minutes: int
    max_retries: int = 1


@dataclass(slots=True)
class PlannerOutput:
    version: str
    dataset: PlanDataset
    model: PlanModel
    config: PlanConfig
    metrics: list[PlanMetric] = field(default_factory=list)
    visualizations: list[str] = field(default_factory=list)
    explain: list[str] = field(default_factory=list)
    justifications: dict[str, PlanJustification] = field(default_factory=dict)
    estimated_runtime_minutes: float = 0.0
    license_compliant: bool = True
    policy: PlanPolicy | None = None


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
