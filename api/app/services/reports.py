"""
Reproduction gap computation service.

Compares claimed metric from plan with observed metric from run artifacts.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

EPSILON = 1e-9


async def compute_reproduction_gap(
    run_id: str,
    plan_json: Dict[str, Any],
    storage,
) -> Dict[str, Any]:
    """
    Compute reproduction gap by comparing claimed vs observed metrics.

    Args:
        run_id: The run identifier
        plan_json: The plan JSON containing claimed metrics and citations
        storage: Storage client for fetching run artifacts

    Returns:
        Dictionary with claimed, observed, gap_percent, metric_name, citations, artifacts

    Raises:
        ValueError: If metrics.json not found or primary metric missing
    """
    # Download and parse metrics.json from storage
    metrics_key = f"runs/{run_id}/metrics.json"
    if not storage.object_exists(metrics_key):
        raise ValueError(f"metrics.json not found for run {run_id}")

    metrics_bytes = storage.download(metrics_key)
    metrics_data = json.loads(metrics_bytes.decode("utf-8"))

    # Determine primary metric from plan
    plan_metrics = plan_json.get("metrics", [])
    if not plan_metrics:
        raise ValueError("No metrics defined in plan")

    primary_metric = plan_metrics[0]
    metric_name = primary_metric.get("name")
    claimed_value = primary_metric.get("goal")

    if not metric_name or claimed_value is None:
        raise ValueError(f"Invalid primary metric in plan: {primary_metric}")

    # Extract observed value from metrics.json
    if metric_name not in metrics_data:
        raise ValueError(f"Metric '{metric_name}' not found in metrics.json")

    observed_value = metrics_data[metric_name]

    # Compute gap_percent: (observed - claimed) / max(|claimed|, ε) * 100
    denominator = max(abs(claimed_value), EPSILON)
    gap_percent = ((observed_value - claimed_value) / denominator) * 100.0

    logger.info(
        "gap.computed run_id=%s metric=%s claimed=%.4f observed=%.4f gap=%.2f%%",
        run_id,
        metric_name,
        claimed_value,
        observed_value,
        gap_percent,
    )

    # Extract citations from plan justifications
    citations: List[Dict[str, Any]] = []
    justifications = plan_json.get("justifications", {})
    for key in ["dataset", "model", "config"]:
        if key in justifications:
            just = justifications[key]
            citations.append({
                "source": just.get("citation", ""),
                "confidence": 1.0,  # Schema v0: hardcoded; future: from planner
            })

    # Generate signed URLs for artifacts
    metrics_artifact = storage.create_signed_url(metrics_key, expires_in=3600)
    events_key = f"runs/{run_id}/events.jsonl"
    events_artifact = None
    if storage.object_exists(events_key):
        events_artifact = storage.create_signed_url(events_key, expires_in=3600)

    logs_key = f"runs/{run_id}/logs.txt"
    logs_artifact = storage.create_signed_url(logs_key, expires_in=3600)

    return {
        "claimed": claimed_value,
        "observed": observed_value,
        "gap_percent": gap_percent,
        "metric_name": metric_name,
        "citations": citations,
        "artifacts": {
            "metrics_url": metrics_artifact.signed_url,
            "events_url": events_artifact.signed_url if events_artifact else None,
            "logs_url": logs_artifact.signed_url,
        },
    }
