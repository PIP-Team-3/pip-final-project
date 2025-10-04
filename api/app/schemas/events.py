from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class StageUpdatePayload(BaseModel):
    stage: str
    run_id: Optional[str] = None


class ProgressPayload(BaseModel):
    percent: int = Field(ge=0, le=100)
    message: Optional[str] = None


class LogLinePayload(BaseModel):
    message: str


class MetricUpdatePayload(BaseModel):
    metric: str
    value: float
    split: Optional[str] = None
    ts: Optional[str] = None


class SamplePredPayload(BaseModel):
    text: Optional[str] = None
    label: Optional[str] = None
    stage: Optional[str] = None
    ts: Optional[str] = None


class ErrorPayload(BaseModel):
    message: str
    code: Optional[str] = None


EVENT_VALIDATORS: Dict[str, Any] = {
    "stage_update": StageUpdatePayload,
    "progress": ProgressPayload,
    "log_line": LogLinePayload,
    "metric_update": MetricUpdatePayload,
    "sample_pred": SamplePredPayload,
    "error": ErrorPayload,
}


def validate_event(event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    model = EVENT_VALIDATORS.get(event)
    if not model:
        return payload
    return model(**payload).model_dump()
