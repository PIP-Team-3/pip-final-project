"""
Plan Sanitizer: Post-Stage-2 cleanup and normalization.

This module provides a "soft sanitizer" that coerces types, prunes unknown keys,
resolves dataset names to canonical registry IDs, and extracts justifications from
prose output. It ensures plans are runnable even when Stage 2 returns slightly
malformed or incomplete data.

Key functions:
- coerce_value: Recursively convert string numbers/booleans to proper types
- prune_dict: Remove keys not in target schema (simulate additionalProperties: false)
- resolve_dataset_name: Map aliases to canonical names via dataset_registry
- extract_justification: Parse prose into {quote, citation} structure
- sanitize_plan: Main orchestrator that applies all transformations

Usage:
    >>> from .sanitizer import sanitize_plan
    >>> from .generators.dataset_registry import DATASET_REGISTRY
    >>> sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, policy={})
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple, Optional, Set

from ..materialize.generators.dataset_registry import (
    lookup_dataset,
    normalize_dataset_name,
    DatasetMetadata,
)

logger = logging.getLogger(__name__)

# Datasets that should be blocked/omitted (large, restricted, or problematic)
BLOCKED_DATASETS = {
    "imagenet",
    "imagenet1k",
    "imagenet2012",
    "imagenet21k",
    "openimages",
    "yfcc100m",
}


def coerce_value(value: Any) -> Any:
    """
    Recursively coerce types for JSON values.

    Handles:
    - String numbers: "10" → 10, "0.5" → 0.5
    - String booleans: "true"/"false" → True/False
    - String nulls: "null" → None
    - Lists: recursively coerce elements
    - Dicts: recursively coerce values

    Args:
        value: Raw value from JSON (potentially string-typed)

    Returns:
        Coerced value with proper Python types

    Examples:
        >>> coerce_value("10")
        10
        >>> coerce_value("0.5")
        0.5
        >>> coerce_value("true")
        True
        >>> coerce_value([{"count": "5"}])
        [{'count': 5}]
    """
    if isinstance(value, str):
        # Try boolean first (before number, since "true" could be ambiguous)
        lower = value.lower().strip()
        if lower == "true":
            return True
        if lower == "false":
            return False
        if lower == "null" or lower == "none":
            return None

        # Try number coercion
        try:
            # Check for decimal point to distinguish int vs float
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            # Not a number, return as-is
            return value

    elif isinstance(value, list):
        return [coerce_value(item) for item in value]

    elif isinstance(value, dict):
        return {k: coerce_value(v) for k, v in value.items()}

    # Already correct type (int, float, bool, None)
    return value


def prune_dict(data: Dict[str, Any], allowed_keys: Set[str]) -> Dict[str, Any]:
    """
    Remove keys not in allowed set (simulate additionalProperties: false).

    Recursively prunes nested dictionaries. Does not validate structure,
    only removes unknown top-level keys.

    Args:
        data: Dictionary to prune
        allowed_keys: Set of permitted keys at this level

    Returns:
        Pruned dictionary with only allowed keys

    Examples:
        >>> prune_dict({"a": 1, "b": 2, "extra": 3}, {"a", "b"})
        {'a': 1, 'b': 2}
    """
    pruned = {}
    for key, value in data.items():
        if key in allowed_keys:
            pruned[key] = value
        else:
            logger.debug(f"sanitizer.prune_key key={key} (not in schema)")
    return pruned


def is_dataset_allowed(name: str, registry: Dict[str, DatasetMetadata]) -> bool:
    """
    Check if dataset is in registry and not blocked.

    Args:
        name: Dataset name to check
        registry: Dataset registry (from dataset_registry.py)

    Returns:
        True if dataset is allowed, False if blocked or unknown

    Examples:
        >>> is_dataset_allowed("sst2", DATASET_REGISTRY)
        True
        >>> is_dataset_allowed("imagenet", DATASET_REGISTRY)
        False
        >>> is_dataset_allowed("unknown_dataset", DATASET_REGISTRY)
        False
    """
    normalized = normalize_dataset_name(name)

    # Check if blocked
    if normalized in BLOCKED_DATASETS:
        return False

    # Check if in registry
    meta = lookup_dataset(name)
    return meta is not None


def resolve_dataset_name(name: str, registry: Dict[str, DatasetMetadata]) -> Optional[str]:
    """
    Resolve dataset name to canonical registry ID.

    Handles aliases and normalization (e.g., "SST-2" → "sst2", "glue/sst2" → "sst2").

    Args:
        name: Raw dataset name from plan
        registry: Dataset registry

    Returns:
        Canonical dataset name if found, None if not in registry or blocked

    Examples:
        >>> resolve_dataset_name("SST-2", DATASET_REGISTRY)
        'sst2'
        >>> resolve_dataset_name("glue/sst2", DATASET_REGISTRY)
        'sst2'
        >>> resolve_dataset_name("ImageNet", DATASET_REGISTRY)
        None
    """
    normalized = normalize_dataset_name(name)

    # Blocked datasets return None
    if normalized in BLOCKED_DATASETS:
        logger.info(f"sanitizer.dataset.blocked name={name} normalized={normalized}")
        return None

    # Lookup in registry (handles aliases)
    meta = lookup_dataset(name)
    if meta is None:
        logger.warning(f"sanitizer.dataset.unknown name={name} normalized={normalized}")
        return None

    # Find canonical name by reverse-lookup
    # (We need to find the key that maps to this metadata)
    for canonical_name, candidate_meta in registry.items():
        if candidate_meta is meta:
            logger.info(f"sanitizer.dataset.resolved name={name} canonical={canonical_name}")
            return canonical_name

    # Fallback: use normalized name if it matches
    if normalized in registry:
        return normalized

    return None


def extract_justification(prose: str, field: str) -> Dict[str, str]:
    """
    Extract justification {quote, citation} from prose text.

    Tries to find quotes and citations in Stage 1 output. If not found,
    creates a minimal justification from the prose.

    Args:
        prose: Raw text from Stage 1 (may contain quotes/citations)
        field: Field name for logging (e.g., "dataset", "model", "config")

    Returns:
        Dict with "quote" and "citation" keys

    Examples:
        >>> extract_justification('The paper uses SST-2 (Section 3.1)', 'dataset')
        {'quote': 'The paper uses SST-2', 'citation': 'Section 3.1'}
    """
    # Try to extract citation patterns: (Section X), (Table Y), (p. Z), etc.
    citation_match = re.search(
        r'\((?:Section|Table|Figure|Appendix|p\.?)\s+[\w\d.]+\)',
        prose,
        re.IGNORECASE
    )

    if citation_match:
        citation = citation_match.group(0).strip("()")
        # Quote is everything before the citation
        quote = prose[:citation_match.start()].strip()
        if not quote:
            quote = f"Justification for {field} from paper"
    else:
        # No citation found - use first sentence as quote
        sentences = prose.split(".")
        quote = sentences[0].strip() if sentences else prose.strip()
        if not quote:  # Handle empty prose
            quote = f"Justification for {field} from paper"
        citation = f"Inferred from plan ({field})"

    return {
        "quote": quote[:500],  # Limit quote length
        "citation": citation[:100],  # Limit citation length
    }


def sanitize_plan(
    raw_plan: Dict[str, Any],
    registry: Dict[str, DatasetMetadata],
    policy: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Sanitize and normalize plan JSON from Stage 2.

    Applies:
    1. Type coercion (string numbers/booleans → proper types)
    2. Key pruning (remove unknown fields)
    3. Dataset resolution (aliases → canonical names, blocked → omitted)
    4. Justifications fixup (ensure {quote, citation} structure)

    Args:
        raw_plan: Raw plan dict from Stage 2 (may have type/schema issues)
        registry: Dataset registry for name resolution
        policy: Policy dict (budget_minutes, etc.)

    Returns:
        Tuple of (sanitized_plan, warnings)
        - sanitized_plan: Clean plan dict ready for validation
        - warnings: List of warning messages about omissions/changes

    Raises:
        ValueError: If all datasets are blocked/unknown (no runnable plan)

    Examples:
        >>> plan = {"dataset": {"name": "SST-2"}, "metrics": ["accuracy"]}
        >>> sanitized, warnings = sanitize_plan(plan, DATASET_REGISTRY, {})
        >>> sanitized["dataset"]["name"]
        'sst2'
    """
    warnings = []

    logger.info("sanitizer.start fields=%s", list(raw_plan.keys()))

    # Step 1: Type coercion
    coerced = coerce_value(raw_plan)
    if not isinstance(coerced, dict):
        # Should never happen, but safety check
        raise ValueError(f"Plan must be a dict, got {type(coerced)}")

    # Step 2: Prune unknown keys (Plan v1.1 top-level schema)
    # We keep this minimal - just ensure core fields exist
    # (Full validation happens later via Pydantic)
    allowed_top_level = {
        "version",
        "dataset",
        "model",
        "config",
        "metrics",
        "visualizations",
        "explain",
        "justifications",
        "estimated_runtime_minutes",
        "license_compliant",
        "policy",
    }
    pruned = prune_dict(coerced, allowed_top_level)

    # Step 3: Dataset resolution
    if "dataset" in pruned and isinstance(pruned["dataset"], dict):
        dataset_obj = pruned["dataset"]
        raw_name = dataset_obj.get("name")

        if raw_name:
            canonical = resolve_dataset_name(raw_name, registry)
            if canonical is None:
                # Dataset blocked or unknown
                if normalize_dataset_name(raw_name) in BLOCKED_DATASETS:
                    warnings.append(
                        f"Dataset '{raw_name}' is blocked (large/restricted) and was omitted"
                    )
                else:
                    warnings.append(
                        f"Dataset '{raw_name}' not in registry and was omitted"
                    )
                # Remove dataset from plan (will fail later if no fallback)
                pruned.pop("dataset", None)
            else:
                # Update to canonical name
                if canonical != raw_name:
                    warnings.append(
                        f"Dataset name normalized: '{raw_name}' → '{canonical}'"
                    )
                dataset_obj["name"] = canonical

    # Check if we have any datasets left
    if "dataset" not in pruned or not pruned.get("dataset", {}).get("name"):
        # No dataset remaining after sanitization
        raise ValueError(
            "No allowed datasets in plan after sanitization. "
            "Add datasets to registry or adjust planner to use covered datasets."
        )

    # Step 4: Justifications fixup
    # Ensure justifications is a dict with {dataset, model, config} keys
    if "justifications" not in pruned or not isinstance(pruned["justifications"], dict):
        pruned["justifications"] = {}

    justifs = pruned["justifications"]

    # Each justification must have {quote, citation} structure
    for field_name in ["dataset", "model", "config"]:
        if field_name not in justifs:
            # Missing justification - create minimal one
            justifs[field_name] = {
                "quote": f"Justification for {field_name} from planner output",
                "citation": "Inferred from plan"
            }
            warnings.append(f"Missing justification for '{field_name}', added placeholder")
        elif isinstance(justifs[field_name], str):
            # Justification is a string (prose) - extract quote/citation
            prose = justifs[field_name]
            justifs[field_name] = extract_justification(prose, field_name)
            logger.debug(f"sanitizer.justification.extracted field={field_name}")
        elif isinstance(justifs[field_name], dict):
            # Already structured - ensure keys exist
            j = justifs[field_name]
            if "quote" not in j:
                j["quote"] = f"Justification for {field_name}"
            if "citation" not in j:
                j["citation"] = "Inferred from plan"

    # Step 5: Ensure required fields exist with defaults
    # ALWAYS set version to "1.1" (don't just check if missing - Stage 2 might set wrong value)
    pruned["version"] = "1.1"

    # Ensure metrics is List[PlanMetric] format (Pydantic schema requirement)
    if "metrics" not in pruned or not pruned["metrics"]:
        # Default to accuracy metric object
        pruned["metrics"] = [{
            "name": "accuracy",
            "split": pruned.get("dataset", {}).get("split", "test"),
            "goal": None,
            "tolerance": None,
            "direction": "maximize"
        }]
        warnings.append("No metrics specified, defaulted to accuracy")
    elif isinstance(pruned["metrics"], list) and all(isinstance(m, str) for m in pruned["metrics"]):
        # Convert string list to metric objects
        dataset_split = pruned.get("dataset", {}).get("split", "test")
        pruned["metrics"] = [{
            "name": m,
            "split": dataset_split,
            "goal": None,
            "tolerance": None,
            "direction": "maximize"
        } for m in pruned["metrics"]]
        logger.debug("sanitizer.metrics.converted from strings to objects")

    if "visualizations" not in pruned or not pruned["visualizations"]:
        pruned["visualizations"] = ["training_curve"]
        warnings.append("No visualizations specified, defaulted to ['training_curve']")

    # Add explain field if missing (required by Pydantic schema)
    if "explain" not in pruned or not pruned["explain"]:
        pruned["explain"] = ["Load dataset", "Train model", "Evaluate metrics"]
        warnings.append("No explain steps, added defaults")

    if "estimated_runtime_minutes" not in pruned:
        budget = policy.get("budget_minutes", 20)
        pruned["estimated_runtime_minutes"] = budget
        warnings.append(f"No runtime estimate, defaulted to budget ({budget} minutes)")

    if "license_compliant" not in pruned:
        pruned["license_compliant"] = True

    logger.info(
        "sanitizer.complete warnings_count=%d dataset=%s",
        len(warnings),
        pruned.get("dataset", {}).get("name", "unknown")
    )

    return pruned, warnings
