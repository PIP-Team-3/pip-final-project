from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator


class PlanJustification(BaseModel):
    """Represents a single grounded justification with citation."""

    quote: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)


class PlanDataset(BaseModel):
    name: str = Field(..., min_length=1)
    split: str = Field(..., min_length=1)
    filters: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class PlanModel(BaseModel):
    name: str = Field(..., min_length=1)
    variant: Optional[str] = None
    parameters: Dict[str, Any] | None = Field(
        None,
        description="Model hyperparameters (can be int, float, str, list, etc.)"
    )
    size_category: Literal["tiny", "small", "medium"] = Field(
        default="tiny",
        description="Qualitative size bucket for the chosen model.",
    )


class PlanConfig(BaseModel):
    framework: str = Field(..., min_length=1)
    seed: int = Field(..., ge=0)
    epochs: int = Field(..., ge=1, le=20)
    batch_size: int = Field(..., ge=1)
    learning_rate: float = Field(..., gt=0.0)
    optimizer: str = Field(..., min_length=1)


class PlanMetric(BaseModel):
    name: str = Field(..., min_length=1)
    split: str = Field(..., min_length=1)
    goal: Optional[float] = None
    tolerance: Optional[float] = Field(None, ge=0.0)
    direction: Literal["maximize", "minimize"] = "maximize"


class PlanPolicy(BaseModel):
    budget_minutes: int = Field(..., ge=1, le=20)
    max_retries: int = Field(default=1, ge=0, le=3)


class PlanDocumentV11(BaseModel):
    """Strict validator for Planner outputs (version 1.1)."""

    version: Literal["1.1"]
    dataset: PlanDataset
    model: PlanModel
    config: PlanConfig
    metrics: List[PlanMetric]
    visualizations: List[str] = Field(..., min_length=1)
    explain: List[str] = Field(..., min_length=1)
    justifications: Dict[str, PlanJustification]
    estimated_runtime_minutes: float = Field(..., gt=0.0, le=20.0)
    license_compliant: bool
    policy: PlanPolicy

    @model_validator(mode="after")
    def _post_validate(self) -> "PlanDocumentV11":
        if not self.metrics:
            raise ValueError("At least one metric target is required")
        if not all(item.strip() for item in self.visualizations):
            raise ValueError("Visualization entries must be non-empty strings")
        if not all(item.strip() for item in self.explain):
            raise ValueError("Explain entries must be non-empty strings")
        required_keys = {"dataset", "model", "config"}
        if not required_keys.issubset(self.justifications.keys()):
            missing = ", ".join(sorted(required_keys - set(self.justifications.keys())))
            raise ValueError(f"Missing justifications for: {missing}")
        return self


__all__ = [
    "PlanDocumentV11",
    "PlanConfig",
    "PlanDataset",
    "PlanJustification",
    "PlanMetric",
    "PlanModel",
    "PlanPolicy",
]
