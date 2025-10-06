"""
Pydantic models for agent structured outputs (Responses API compatibility).

These models mirror the dataclass structure in types.py but provide
Pydantic validation for OpenAI function tools.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, confloat


class CitationModel(BaseModel):
    """Citation with confidence score - matches types.Citation dataclass."""
    source_citation: str = Field(..., description="Section/table citation (e.g., 'Table 1, p.3' or 'Section 3.2, p.5')")
    confidence: confloat(ge=0.0, le=1.0) = Field(..., description="Confidence score 0.0-1.0")

    class Config:
        extra = "forbid"


class ExtractedClaimModel(BaseModel):
    """Single quantitative performance claim - matches types.ExtractedClaim dataclass."""
    dataset_name: Optional[str] = Field(None, description="Dataset name")
    split: Optional[str] = Field(None, description="Train/val/test split")
    metric_name: Optional[str] = Field(None, description="Metric name (accuracy, F1, etc.)")
    metric_value: Optional[float] = Field(None, description="Numeric metric value")
    units: Optional[str] = Field(None, description="Units (%, seconds, etc.)")
    method_snippet: Optional[str] = Field(None, max_length=1000, description="Brief method description")
    citation: CitationModel = Field(..., description="Source citation with confidence")

    class Config:
        extra = "forbid"


class ExtractorOutputModel(BaseModel):
    """Complete extractor output - matches types.ExtractorOutput dataclass."""
    claims: List[ExtractedClaimModel] = Field(default_factory=list, description="Extracted claims list")

    class Config:
        extra = "forbid"
