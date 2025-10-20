"""
Dataset Resolution Module - Phase A

Classifies datasets as resolved, blocked, unknown, or complex before sanitization.
Part of the Dataset Resolution Assistant roadmap.

See: docs/current/milestones/dataset_resolution_agent.md
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import re
import logging

logger = logging.getLogger(__name__)


class ResolutionStatus(Enum):
    """Dataset resolution status outcomes."""

    RESOLVED = "resolved"   # In registry, ready to use
    BLOCKED = "blocked"     # Intentionally blocked (large/restricted)
    UNKNOWN = "unknown"     # Not in registry, might be acquirable
    COMPLEX = "complex"     # Needs custom adapter/preprocessing


@dataclass
class DatasetResolutionResult:
    """Result of dataset resolution attempt."""

    status: ResolutionStatus
    dataset_name: str
    canonical_name: Optional[str] = None      # Normalized registry name if RESOLVED
    reason: Optional[str] = None              # Why blocked/unknown/complex
    suggestions: Optional[List[str]] = None   # Brief hints (full advisor in Phase B)
    metadata: Optional[Dict[str, Any]] = None # Registry metadata if available


# Complexity detection patterns
# Datasets matching these patterns need custom acquisition/preprocessing
COMPLEX_PATTERNS = [
    r'\+',                          # Multi-dataset indicator (NYC Taxi + NOAA)
    r'taxi.*weather',               # Taxi + weather correlation studies
    r'weather.*taxi',               # Reverse order
    r'fairness.*demographic',       # Fairness + demographic data
    r'demographic.*fairness',       # Reverse order
    r'eia.*load',                   # EIA electricity load data
    r'load.*eia',                   # Reverse order
    r'openimages.*subset',          # Custom subsets of large datasets
]


def normalize_dataset_name(name: str) -> str:
    """
    Normalize dataset name for comparison.

    Args:
        name: Raw dataset name from paper/claim

    Returns:
        Normalized name (lowercase, no punctuation/whitespace)
    """
    if not name:
        return ""

    # Convert to lowercase and remove non-alphanumeric characters
    normalized = re.sub(r'[^a-z0-9]+', '', name.lower())
    return normalized


def is_complex_dataset(dataset_name: str) -> bool:
    """
    Check if dataset name matches complexity patterns.

    Complex datasets require custom adapters or multi-source acquisition.

    Args:
        dataset_name: Raw dataset name

    Returns:
        True if dataset appears complex
    """
    name_lower = dataset_name.lower()

    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, name_lower):
            logger.debug(
                "dataset_resolution.complex_match pattern=%s dataset=%s",
                pattern,
                dataset_name
            )
            return True

    return False


def classify_dataset(
    dataset_name: str,
    registry: Dict[str, Any],
    blocked_list: Set[str]
) -> DatasetResolutionResult:
    """
    Classify dataset resolution status.

    Classification logic:
    1. Normalize name (lowercase, strip punctuation)
    2. Check blocked list → BLOCKED
    3. Check registry (exact + aliases) → RESOLVED
    4. Check complexity heuristics → COMPLEX vs UNKNOWN

    Args:
        dataset_name: Raw dataset name from claim/plan
        registry: Dataset registry (DATASET_REGISTRY)
        blocked_list: Set of blocked dataset names (BLOCKED_DATASETS)

    Returns:
        DatasetResolutionResult with classification outcome
    """
    if not dataset_name:
        return DatasetResolutionResult(
            status=ResolutionStatus.UNKNOWN,
            dataset_name="",
            reason="No dataset name provided"
        )

    logger.debug("dataset_resolution.classify dataset=%s", dataset_name)

    # Step 1: Normalize for comparison
    normalized = normalize_dataset_name(dataset_name)

    # Step 2: Check blocked list
    if normalized in blocked_list:
        logger.info(
            "dataset_resolution.blocked dataset=%s normalized=%s",
            dataset_name,
            normalized
        )
        return DatasetResolutionResult(
            status=ResolutionStatus.BLOCKED,
            dataset_name=dataset_name,
            reason=f"Dataset '{dataset_name}' is blocked (large/restricted license)",
            suggestions=["Use a smaller alternative dataset from registry"]
        )

    # Step 3: Check registry (exact + aliases)
    # Reuse existing resolution logic from dataset_registry
    from app.materialize.generators.dataset_registry import lookup_dataset, normalize_dataset_name as registry_normalize

    dataset_meta = lookup_dataset(dataset_name)

    if dataset_meta:
        # Find the canonical name (registry key) for this dataset
        # The canonical name is the registry key that maps to this metadata object
        canonical_name = None
        normalized_input = registry_normalize(dataset_name)

        # Check if input matches a registry key directly
        if normalized_input in registry:
            canonical_name = normalized_input
        else:
            # Find which registry key has this metadata (via alias match)
            for reg_key, reg_meta in registry.items():
                if reg_meta is dataset_meta:
                    canonical_name = reg_key
                    break

        logger.info(
            "dataset_resolution.resolved dataset=%s canonical=%s",
            dataset_name,
            canonical_name
        )

        return DatasetResolutionResult(
            status=ResolutionStatus.RESOLVED,
            dataset_name=dataset_name,
            canonical_name=canonical_name,
            reason=f"Dataset found in registry as '{canonical_name}'",
            metadata={"source": dataset_meta.source.value, "aliases": list(dataset_meta.aliases)}
        )

    # Step 4: Not in registry - check complexity
    if is_complex_dataset(dataset_name):
        logger.info(
            "dataset_resolution.complex dataset=%s",
            dataset_name
        )
        return DatasetResolutionResult(
            status=ResolutionStatus.COMPLEX,
            dataset_name=dataset_name,
            reason="Dataset requires custom acquisition/preprocessing (multi-source or bespoke data)",
            suggestions=[
                "Consider Phase B advisor for detailed acquisition strategy",
                "May require custom DatasetAdapter implementation"
            ]
        )

    # Step 5: Unknown - simple dataset not in registry
    logger.info(
        "dataset_resolution.unknown dataset=%s",
        dataset_name
    )
    return DatasetResolutionResult(
        status=ResolutionStatus.UNKNOWN,
        dataset_name=dataset_name,
        reason="Dataset not found in registry",
        suggestions=[
            "Add dataset to registry if it's a standard benchmark",
            "Request advisor assistance for acquisition strategy (Phase B)",
            "Consider using a similar dataset from registry as fallback"
        ]
    )


def resolve_dataset_for_plan(
    plan_dict: Dict[str, Any],
    registry: Dict[str, Any],
    blocked_list: Set[str]
) -> Optional[DatasetResolutionResult]:
    """
    Extract dataset from plan dict and classify it.

    Convenience wrapper for planner integration.

    Args:
        plan_dict: Stage 2 planner output (before sanitization)
        registry: Dataset registry
        blocked_list: Set of blocked datasets

    Returns:
        Resolution result, or None if no dataset in plan
    """
    dataset_section = plan_dict.get("dataset", {})
    dataset_name = dataset_section.get("name")

    if not dataset_name:
        logger.warning("dataset_resolution.no_dataset plan_keys=%s", list(plan_dict.keys()))
        return None

    return classify_dataset(dataset_name, registry, blocked_list)
