from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Dict, Iterable, List

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

EmitCallable = Callable[[str, Dict[str, object]], None]

logger = logging.getLogger(__name__)

# Artifact size caps (bytes)
MAX_LOGS_SIZE = 2 * 1024 * 1024  # 2 MiB
MAX_EVENTS_SIZE = 5 * 1024 * 1024  # 5 MiB
TRUNCATION_MARKER = "\n__TRUNCATED__\n"


@dataclass
class NotebookRunResult:
    metrics_text: str
    events_text: str
    logs_text: str


class NotebookExecutionError(RuntimeError):
    """Raised when the notebook fails to produce required artifacts."""


class GPURequestedError(RuntimeError):
    """Raised when GPU is requested but CPU-only mode is enforced."""


def _setup_deterministic_seeds(seed: int, emit: EmitCallable) -> None:
    """Set seeds for random, numpy, and torch (if present) for deterministic execution."""
    random.seed(seed)
    emit("stage_update", {"stage": "seed_check", "seed": seed})

    try:
        import numpy as np
        np.random.seed(seed)
        emit("log_line", {"message": f"numpy seed set: {seed}"})
    except ImportError:
        pass

    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        emit("log_line", {"message": f"torch seed set: {seed}"})
    except ImportError:
        pass


def _enforce_cpu_only(emit: EmitCallable) -> None:
    """Verify CPU-only execution; raise GPURequestedError if GPU is detected or requested."""
    # Check environment variables that might request GPU
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if cuda_visible and cuda_visible != "-1":
        logger.error("GPU requested via CUDA_VISIBLE_DEVICES=%s", cuda_visible)
        raise GPURequestedError(f"GPU requested via CUDA_VISIBLE_DEVICES={cuda_visible}, but CPU-only mode is enforced")

    # Force CPU-only for PyTorch
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    # Check if torch is available and has GPU
    try:
        import torch
        if torch.cuda.is_available():
            logger.warning("torch.cuda.is_available() returned True; enforcing CPU-only")
            # This shouldn't happen if CUDA_VISIBLE_DEVICES=-1, but double-check
            emit("log_line", {"message": "Warning: GPU detected but CPU-only mode enforced"})
    except ImportError:
        pass

    emit("log_line", {"message": f"Environment: Python {sys.version.split()[0]}, CPU-only mode"})


def _truncate_if_needed(text: str, max_size: int, label: str, emit: EmitCallable) -> str:
    """Truncate text if it exceeds max_size and emit a warning."""
    if len(text.encode("utf-8")) <= max_size:
        return text

    # Truncate to fit marker
    marker_size = len(TRUNCATION_MARKER.encode("utf-8"))
    truncated = text.encode("utf-8")[: max_size - marker_size].decode("utf-8", errors="ignore")

    warning = f"{label} exceeded {max_size} bytes and was truncated"
    logger.warning(warning)
    emit("log_line", {"message": f"Warning: {warning}"})

    return truncated + TRUNCATION_MARKER


def _stream_lines(outputs: Iterable[dict]) -> List[str]:
    """Extract printable lines from notebook cell outputs."""

    lines: List[str] = []
    for output in outputs:
        if output.get("output_type") == "stream":
            text = output.get("text", "")
            for line in str(text).splitlines():
                if line.strip():
                    lines.append(line)
        elif output.get("output_type") == "error":
            ename = output.get("ename", "Error")
            evalue = output.get("evalue", "")
            lines.append(f"{ename}: {evalue}")
    return lines


def _flush_notebook_events(events_path: Path, emit: EmitCallable, start_index: int) -> int:
    """Stream new JSONL events emitted by the notebook to the SSE bridge."""

    if not events_path.exists():
        return start_index

    try:
        raw_lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return start_index

    for raw_event in raw_lines[start_index:]:
        payload_raw = raw_event.strip()
        if not payload_raw:
            continue
        try:
            payload_obj = json.loads(payload_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload_obj, dict):
            continue
        event_type = payload_obj.pop("type", None)
        if not isinstance(event_type, str):
            continue
        emit(event_type, payload_obj)

    return len(raw_lines)


def _execute_sync(
    notebook_bytes: bytes,
    emit: EmitCallable,
    timeout_seconds: int,
    seed: int = 42,
) -> NotebookRunResult:
    logs: List[str] = []
    events_text = ""
    metrics_text = ""

    # Enforce CPU-only and set deterministic seeds
    _enforce_cpu_only(emit)
    _setup_deterministic_seeds(seed, emit)

    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        notebook_path = tmp_path / "notebook.ipynb"
        notebook_path.write_bytes(notebook_bytes)

        nb = nbformat.reads(notebook_bytes.decode("utf-8"), as_version=4)
        client = NotebookClient(
            nb,
            timeout=timeout_seconds,
            kernel_name="python3",
            allow_errors=False,
            resources={"metadata": {"path": str(tmp_path)}},
        )

        events_path = tmp_path / "events.jsonl"
        processed_events = 0

        with client.setup_kernel():
            total = max(len(nb.cells), 1)
            for index, cell in enumerate(nb.cells, start=1):
                emit("progress", {"percent": int(((index - 1) / total) * 100)})
                try:
                    client.execute_cell(cell, index - 1, execution_count=index)
                except CellExecutionError as exc:
                    cell_logs = _stream_lines(cell.get("outputs", []))
                    logs.extend(cell_logs)
                    for line in cell_logs:
                        emit("log_line", {"message": line})
                    processed_events = _flush_notebook_events(events_path, emit, processed_events)
                    raise NotebookExecutionError(str(exc))

                cell_logs = _stream_lines(cell.get("outputs", []))
                for line in cell_logs:
                    logs.append(line)
                    emit("log_line", {"message": line})

                processed_events = _flush_notebook_events(events_path, emit, processed_events)
                emit("progress", {"percent": int((index / total) * 100)})

        metrics_path = tmp_path / "metrics.json"
        if not metrics_path.exists():
            raise NotebookExecutionError("metrics.json not produced by notebook")
        metrics_text = metrics_path.read_text(encoding="utf-8")

        events_path = tmp_path / "events.jsonl"
        if events_path.exists():
            processed_events = _flush_notebook_events(events_path, emit, processed_events)
            events_text = events_path.read_text(encoding="utf-8")

        log_file = tmp_path / "logs.txt"
        if log_file.exists():
            file_lines = [line for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            logs.extend(file_lines)

    logs_text = "\n".join(logs)
    if logs_text:
        logs_text += "\n"

    # Apply artifact size caps with truncation
    logs_text = _truncate_if_needed(logs_text, MAX_LOGS_SIZE, "logs.txt", emit)
    events_text = _truncate_if_needed(events_text, MAX_EVENTS_SIZE, "events.jsonl", emit)

    return NotebookRunResult(
        metrics_text=metrics_text,
        events_text=events_text,
        logs_text=logs_text,
    )


async def execute_notebook(
    notebook_bytes: bytes,
    emit: EmitCallable,
    timeout_minutes: int,
    seed: int = 42,
) -> NotebookRunResult:
    timeout_minutes = max(1, min(timeout_minutes, 25))
    timeout_seconds = timeout_minutes * 60
    return await asyncio.to_thread(_execute_sync, notebook_bytes, emit, timeout_seconds, seed)
