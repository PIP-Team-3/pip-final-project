from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..config.llm import traced_run, traced_subspan
from ..data.models import RunCreate, RunEventCreate
from ..data.supabase import SupabaseDatabase
from ..dependencies import get_supabase_db, get_supabase_storage
from ..run.runner_local import GPURequestedError, NotebookExecutionError, NotebookRunResult, execute_notebook
from ..runs import run_stream_manager
from ..schemas.events import validate_event
from ..schemas.plan_v1_1 import PlanDocumentV11

logger = logging.getLogger(__name__)

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "succeeded"
RUN_STATUS_FAILED = "failed"

RUN_STAGE_START = "run_start"
RUN_STAGE_COMPLETE = "run_complete"
RUN_STAGE_ERROR = "run_error"

RUN_ERROR_TIMEOUT = "E_RUN_TIMEOUT"
RUN_ERROR_PLAN_MISSING = "E_PLAN_NOT_FOUND"
RUN_ERROR_FAILED = "E_RUN_FAILED"
RUN_ERROR_GPU_REQUESTED = "E_GPU_REQUESTED"

RUN_ARTIFACT_METRICS = "metrics.json"
RUN_ARTIFACT_EVENTS = "events.jsonl"
RUN_ARTIFACT_LOG = "logs.txt"

DEFAULT_TIMEOUT_MINUTES = 25

router = APIRouter(prefix="/api/v1/plans", tags=["runs"])
stream_router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


async def _persist_artifacts(storage, run_id: str, result: NotebookRunResult) -> None:
    storage.store_text(
        f"runs/{run_id}/{RUN_ARTIFACT_METRICS}",
        result.metrics_text,
        "application/json",
    )
    if result.events_text:
        storage.store_text(
            f"runs/{run_id}/{RUN_ARTIFACT_EVENTS}",
            result.events_text,
            "application/jsonl",
        )
    storage.store_text(
        f"runs/{run_id}/{RUN_ARTIFACT_LOG}",
        result.logs_text or "",
        "text/plain",
    )


async def _run_plan(
    plan_record,
    run_id: str,
    db: SupabaseDatabase,
    storage,
) -> None:
    manager = run_stream_manager
    manager.register(run_id)
    captured_logs: list[str] = []

    def _emit(event: str, payload: Dict[str, Any]) -> None:
        validated = validate_event(event, payload)
        if event == "log_line":
            message = validated.get("message")
            if isinstance(message, str):
                captured_logs.append(message)
        manager.publish(run_id, event, validated)
        try:
            db.insert_run_event(
                RunEventCreate(
                    id=str(uuid4()),
                    run_id=run_id,
                    ts=datetime.now(timezone.utc),
                    type=event,
                    payload=validated,
                )
            )
        except Exception as exc:  # pragma: no cover - observability only
            logger.warning("run.events.persist_failed run_id=%s error=%s", run_id, exc)

    try:
        plan_document = PlanDocumentV11.model_validate(plan_record.plan_json)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("run.plan.validation_failed plan_id=%s error=%s", getattr(plan_record, "id", None), exc)
        _emit(
            "error",
            {
                "message": "Plan document invalid",
                "code": RUN_ERROR_FAILED,
            },
        )
        manager.close(run_id)
        return

    timeout_minutes = plan_document.policy.budget_minutes if plan_document.policy else DEFAULT_TIMEOUT_MINUTES
    timeout_minutes = min(timeout_minutes or DEFAULT_TIMEOUT_MINUTES, DEFAULT_TIMEOUT_MINUTES)

    # Extract seed from plan config for deterministic execution
    seed = 42  # default
    if plan_document.config and hasattr(plan_document.config, "seed"):
        seed = plan_document.config.seed or 42

    notebook_key = f"plans/{plan_record.id}/notebook.ipynb"

    with traced_run("p2n.run.exec") as span:
        started_at = datetime.now(timezone.utc)
        try:
            db.update_run(
                run_id,
                status=RUN_STATUS_RUNNING,
                started_at=started_at,
            )
        except Exception as exc:  # pragma: no cover - persistence errors
            logger.error("run.update_failed run_id=%s error=%s", run_id, exc)

        _emit("stage_update", {"stage": RUN_STAGE_START, "run_id": run_id})
        _emit("progress", {"percent": 0})

        try:
            with traced_subspan(span, "p2n.run.nbclient.start"):
                notebook_bytes = storage.download(notebook_key)

            with traced_subspan(span, "p2n.run.nbclient.finish"):
                result = await execute_notebook(
                    notebook_bytes=notebook_bytes,
                    emit=_emit,
                    timeout_minutes=timeout_minutes,
                    seed=seed,
                )

            with traced_subspan(span, "p2n.run.artifacts.persist"):
                await _persist_artifacts(storage, run_id, result)

            completed_at = datetime.now(timezone.utc)
            db.update_run(
                run_id,
                status=RUN_STATUS_COMPLETED,
                completed_at=completed_at,
            )
            _emit("stage_update", {"stage": RUN_STAGE_COMPLETE, "run_id": run_id})
            _emit("progress", {"percent": 100})
        except asyncio.TimeoutError:
            logger.warning("run.timeout run_id=%s", run_id)
            _emit("stage_update", {"stage": RUN_STAGE_ERROR, "run_id": run_id})
            _emit(
                "error",
                {"message": "Run exceeded allotted time", "code": RUN_ERROR_TIMEOUT},
            )
            db.update_run(
                run_id,
                status=RUN_STATUS_FAILED,
                completed_at=datetime.now(timezone.utc),
            )
            storage.store_text(
                f"runs/{run_id}/{RUN_ARTIFACT_LOG}",
                "\n".join(captured_logs) + ("\n" if captured_logs else ""),
                "text/plain",
            )
        except GPURequestedError as exc:
            logger.warning("run.gpu_requested run_id=%s error=%s", run_id, exc)
            _emit("stage_update", {"stage": RUN_STAGE_ERROR, "run_id": run_id})
            _emit("error", {"message": str(exc), "code": RUN_ERROR_GPU_REQUESTED})
            db.update_run(
                run_id,
                status=RUN_STATUS_FAILED,
                completed_at=datetime.now(timezone.utc),
            )
            storage.store_text(
                f"runs/{run_id}/{RUN_ARTIFACT_LOG}",
                "\n".join(captured_logs) + ("\n" if captured_logs else ""),
                "text/plain",
            )
        except NotebookExecutionError as exc:
            logger.info("run.nbclient_failed run_id=%s error=%s", run_id, exc)
            _emit("stage_update", {"stage": RUN_STAGE_ERROR, "run_id": run_id})
            _emit("error", {"message": str(exc), "code": RUN_ERROR_FAILED})
            db.update_run(
                run_id,
                status=RUN_STATUS_FAILED,
                completed_at=datetime.now(timezone.utc),
            )
            storage.store_text(
                f"runs/{run_id}/{RUN_ARTIFACT_LOG}",
                "\n".join(captured_logs) + ("\n" if captured_logs else ""),
                "text/plain",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("run.unexpected_failure run_id=%s error=%s", run_id, exc)
            _emit("stage_update", {"stage": RUN_STAGE_ERROR, "run_id": run_id})
            _emit(
                "error",
                {"message": "Unexpected run failure", "code": RUN_ERROR_FAILED},
            )
            db.update_run(
                run_id,
                status=RUN_STATUS_FAILED,
                completed_at=datetime.now(timezone.utc),
            )
            storage.store_text(
                f"runs/{run_id}/{RUN_ARTIFACT_LOG}",
                "\n".join(captured_logs) + ("\n" if captured_logs else ""),
                "text/plain",
            )
        finally:
            manager.close(run_id)


@router.post("/{plan_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    plan_id: str,
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
    now = datetime.now(timezone.utc)
    db.insert_run(
        RunCreate(
            id=run_id,
            plan_id=plan_record.id,
            paper_id=plan_record.paper_id,
            status=RUN_STATUS_PENDING,
            env_hash=getattr(plan_record, "env_hash", None),
            created_at=now,
            started_at=None,
            completed_at=None,
        )
    )

    run_stream_manager.register(run_id)
    asyncio.create_task(_run_plan(plan_record, run_id, db, storage))
    return {"run_id": run_id}


@stream_router.get("/{run_id}/events")
async def stream_run_events(run_id: str):
    run_stream_manager.register(run_id)
    return StreamingResponse(run_stream_manager.stream(run_id), media_type="text/event-stream")
