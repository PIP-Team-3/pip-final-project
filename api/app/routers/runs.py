from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ..config.llm import traced_run, traced_subspan
from ..config.settings import get_settings
from ..data.models import RunCreate, RunEventCreate
from ..data.supabase import SupabaseDatabase
from ..dependencies import get_supabase_db, get_supabase_storage
from ..materialize.notebook import build_notebook_bytes, build_requirements
from ..runs import run_stream_manager
from ..schemas.plan_v1_1 import PlanDocumentV11

logger = logging.getLogger(__name__)

RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STAGE_START = "run_start"
RUN_STAGE_COMPLETE = "run_complete"
RUN_STAGE_ERROR = "run_error"
RUN_ERROR_TIMEOUT = "E_RUN_TIMEOUT"
RUN_ERROR_PLAN_MISSING = "E_PLAN_NOT_FOUND"

RUN_ARTIFACT_METRICS = "metrics.json"
RUN_ARTIFACT_EVENTS = "events.jsonl"
RUN_ARTIFACT_LOG = "logs.txt"

router = APIRouter(prefix="/api/v1/plans", tags=["runs"])
stream_router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


async def _simulate_notebook(plan: dict[str, Any], run_id: str, emit) -> Dict[str, Any]:
    emit("stage_update", {"stage": RUN_STAGE_START})
    await asyncio.sleep(0)
    metric_value = 0.75
    events: list[str] = []
    logs: list[str] = ["Starting run", "Executing simulated notebook"]
    emit("log_line", {"message": "Loading dataset"})
    events.append(json.dumps({"event": "stage_update", "stage": "dataset_load"}))
    await asyncio.sleep(0)
    emit("stage_update", {"stage": "train"})
    events.append(json.dumps({"event": "stage_update", "stage": "train"}))
    await asyncio.sleep(0)
    emit("metric_update", {"metric": "accuracy", "value": metric_value})
    events.append(json.dumps({"event": "metric_update", "metric": "accuracy", "value": metric_value}))
    emit("stage_update", {"stage": RUN_STAGE_COMPLETE})
    events.append(json.dumps({"event": "stage_update", "stage": RUN_STAGE_COMPLETE}))
    metrics = {"metrics": {"accuracy": metric_value}}
    return {
        "metrics": json.dumps(metrics, indent=2),
        "events": "\n".join(events) + "\n",
        "logs": "\n".join(logs) + "\n",
    }



async def _run_plan(
    plan_record,
    run_id: str,
    settings,
    db: SupabaseDatabase,
    storage,
    timeout_seconds: int = 60,
) -> None:
    manager = run_stream_manager
    manager.register(run_id)

    def _emit(event: str, payload: Dict[str, Any]) -> None:
        manager.publish(run_id, event, payload)
        db.insert_run_event(
            RunEventCreate(
                id=str(uuid4()),
                run_id=run_id,
                ts=datetime.now(timezone.utc),
                type=event,
                payload=payload,
            )
        )
        if event == "metric_update":
            metric = payload.get("metric")
            value = payload.get("value")
            if metric is not None and isinstance(value, (int, float)):
                db.insert_run_series(run_id, metric, step=1, value=float(value))

    try:
        plan_document = PlanDocumentV11.model_validate(plan_record.plan_json)
        started_at = datetime.now(timezone.utc)
        db.insert_run(
            RunCreate(
                id=run_id,
                plan_id=plan_record.id,
                status=RUN_STATUS_RUNNING,
                env_hash=plan_record.env_hash,
                started_at=started_at,
                finished_at=None,
                created_at=started_at,
            )
        )
        notebook_content = build_notebook_bytes(plan_document, plan_record.id)
        requirements_text, env_hash = build_requirements(plan_document)
        db.update_run(run_id, status=RUN_STATUS_RUNNING, env_hash=env_hash)

        async with asyncio.timeout(timeout_seconds):
            result = await _simulate_notebook(plan_document.model_dump(mode="json"), run_id, _emit)
            metrics_path = f"runs/{run_id}/{RUN_ARTIFACT_METRICS}"
            events_path = f"runs/{run_id}/{RUN_ARTIFACT_EVENTS}"
            logs_path = f"runs/{run_id}/{RUN_ARTIFACT_LOG}"
            storage.store_asset(f"runs/{run_id}/notebook.ipynb", notebook_content, "application/x-ipynb+json")
            storage.store_text(f"runs/{run_id}/requirements.txt", requirements_text, "text/plain")
            storage.store_text(metrics_path, result["metrics"], "application/json")
            storage.store_text(events_path, result["events"], "application/jsonl")
            storage.store_text(logs_path, result["logs"], "text/plain")
            finished_at = datetime.now(timezone.utc)
            db.update_run(run_id, status=RUN_STATUS_COMPLETED, finished_at=finished_at)
    except asyncio.TimeoutError:
        _emit("error", {"code": RUN_ERROR_TIMEOUT, "message": "Run exceeded allotted time"})
        db.update_run(run_id, status=RUN_STATUS_FAILED, finished_at=datetime.now(timezone.utc))
    except Exception as exc:  # pragma: no cover - best effort
        logger.exception("run.failed run_id=%s error=%s", run_id, exc)
        _emit("error", {"code": "E_RUN_FAILED", "message": str(exc)})
        db.update_run(run_id, status=RUN_STATUS_FAILED, finished_at=datetime.now(timezone.utc))
    finally:
        manager.close(run_id)


@router.post("/{plan_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    plan_id: str,
    background_tasks: BackgroundTasks,
    db: SupabaseDatabase = Depends(get_supabase_db),
    storage=Depends(get_supabase_storage),
):
    plan_record = db.get_plan(plan_id)
    if not plan_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": RUN_ERROR_PLAN_MISSING,
                "message": "Plan not found",
            },
        )

    run_id = str(uuid4())
    background_tasks.add_task(
        _run_plan,
        plan_record,
        run_id,
        get_settings(),
        db,
        storage,
    )
    return {"run_id": run_id}


@stream_router.get("/{run_id}/events")
async def stream_run_events(run_id: str):
    queue = run_stream_manager.register(run_id)
    return StreamingResponse(run_stream_manager.stream(run_id), media_type="text/event-stream")
