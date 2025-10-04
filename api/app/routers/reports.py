from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..dependencies import get_supabase_db, get_supabase_storage
from ..services.reports import compute_reproduction_gap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/papers", tags=["reports"])

ERROR_REPORT_NO_RUNS = "E_REPORT_NO_RUNS"
ERROR_REPORT_NO_CLAIM = "E_REPORT_NO_CLAIM"
ERROR_REPORT_METRIC_NOT_FOUND = "E_REPORT_METRIC_NOT_FOUND"


class CitationInfo(BaseModel):
    source: str
    confidence: float


class ReportArtifacts(BaseModel):
    metrics_url: str
    events_url: Optional[str] = None
    logs_url: str


class ReportResponse(BaseModel):
    paper_id: str
    run_id: str
    claimed: float
    observed: float
    gap_percent: float
    metric_name: str
    citations: List[CitationInfo]
    artifacts: ReportArtifacts


@router.get("/{paper_id}/report", response_model=ReportResponse)
async def get_reproduction_report(
    paper_id: str,
    db=Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
):
    """
    Compute the reproduction gap for a paper by comparing the claimed metric
    from the plan with the observed metric from the latest successful run.

    Returns signed URLs to run artifacts with short TTL.
    """
    # Find latest successful run for this paper
    runs = db.get_runs_by_paper(paper_id)
    if not runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_REPORT_NO_RUNS,
                "message": "No runs found for this paper",
                "remediation": "Create a plan and execute a run first",
            },
        )

    # Filter for successful runs and get the latest
    successful_runs = [r for r in runs if r.status == "succeeded"]
    if not successful_runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_REPORT_NO_RUNS,
                "message": "No successful runs found for this paper",
                "remediation": "Wait for a run to complete successfully",
            },
        )

    latest_run = max(successful_runs, key=lambda r: r.completed_at or r.created_at)

    # Get the plan to extract claimed metric
    plan = db.get_plan(latest_run.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ERROR_REPORT_NO_CLAIM,
                "message": "Plan not found for run",
                "remediation": "Ensure plan exists in database",
            },
        )

    # Compute the reproduction gap
    try:
        report_data = await compute_reproduction_gap(
            run_id=latest_run.id,
            plan_json=plan.plan_json,
            storage=storage,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ERROR_REPORT_METRIC_NOT_FOUND,
                "message": str(exc),
                "remediation": "Ensure metrics.json was produced by the run",
            },
        ) from exc

    logger.info(
        "report.computed paper_id=%s run_id=%s gap_percent=%.2f",
        paper_id,
        latest_run.id,
        report_data["gap_percent"],
    )

    return ReportResponse(
        paper_id=paper_id,
        run_id=latest_run.id,
        **report_data,
    )
