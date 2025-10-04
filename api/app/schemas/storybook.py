"""
Storybook schema for Kid-Mode explanations.

Grade-3 reading level, alt-text required, 5-7 pages.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class GlossaryEntry(BaseModel):
    """A glossary term with kid-friendly definition."""

    term: str = Field(..., min_length=1)
    definition: str = Field(..., min_length=1)


class StoryPage(BaseModel):
    """Single page in the storyboard."""

    page_number: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=10, max_length=2000)
    alt_text: str = Field(..., min_length=10, max_length=500, description="Alt-text for visual description")
    visual_hint: Optional[str] = Field(None, max_length=200, description="Suggested visual (not generated)")

    @field_validator("alt_text")
    @classmethod
    def alt_text_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("alt_text is required and must be non-empty")
        return v


class Scoreboard(BaseModel):
    """Two-bar scoreboard comparing claim vs observed metric."""

    metric_name: str
    claimed_value: float
    observed_value: Optional[float] = None  # None until run completes
    gap_percent: Optional[float] = None


class Storyboard(BaseModel):
    """Full storyboard with pages, glossary, and optional scoreboard."""

    storyboard_id: str
    paper_id: str
    run_id: Optional[str] = None
    pages: List[StoryPage] = Field(..., min_length=5, max_length=7)
    glossary: List[GlossaryEntry] = Field(default_factory=list)
    scoreboard: Optional[Scoreboard] = None
    created_at: str
    updated_at: Optional[str] = None

    @field_validator("pages")
    @classmethod
    def validate_pages_count(cls, v: List[StoryPage]) -> List[StoryPage]:
        if len(v) < 5:
            raise ValueError("Storyboard must have at least 5 pages")
        if len(v) > 7:
            raise ValueError("Storyboard must have at most 7 pages")
        return v

    @field_validator("pages")
    @classmethod
    def validate_alt_text_present(cls, v: List[StoryPage]) -> List[StoryPage]:
        for page in v:
            if not page.alt_text or not page.alt_text.strip():
                raise ValueError(f"Page {page.page_number} missing required alt_text")
        return v


class StoryboardCreateRequest(BaseModel):
    """Request to create a new storyboard."""

    paper_id: str = Field(..., min_length=1)


class StoryboardCreateResponse(BaseModel):
    """Response after creating a storyboard."""

    storyboard_id: str
    paper_id: str
    pages_count: int
    signed_url: str
    expires_at: str


class StoryboardRefreshResponse(BaseModel):
    """Response after refreshing final page with run results."""

    storyboard_id: str
    run_id: str
    scoreboard: Scoreboard
    signed_url: str
