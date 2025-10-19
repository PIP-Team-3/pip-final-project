"""
Dataset Registry: Metadata-only dataset catalog.

This module provides a registry of datasets that can be used for notebook generation.
IMPORTANT: This file contains METADATA ONLY - no actual dataset downloads occur here!

The registry maps normalized dataset names to metadata that describes:
- Where to find the dataset (sklearn/torchvision/huggingface)
- How to load it (function name, HF path)
- Size and streaming capabilities
- Aliases for flexible name matching

Usage:
    >>> meta = lookup_dataset("sst2")
    >>> meta.source  # DatasetSource.HUGGINGFACE
    >>> meta.hf_path  # ("glue", "sst2")
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple, Set


class DatasetSource(Enum):
    """Source library for dataset loading."""

    SKLEARN = "sklearn"  # Bundled with sklearn (tiny, always available)
    TORCHVISION = "torchvision"  # Downloads to cache_dir on first use
    HUGGINGFACE = "huggingface"  # Streaming or cached download
    SYNTHETIC = "synthetic"  # Generated on-the-fly (no download)


class DatasetMetadata:
    """
    Metadata about a dataset - describes HOW to generate code to load it.

    Attributes:
        source: Which library provides this dataset
        load_function: Function/class name (e.g., "load_digits", "MNIST", "load_dataset")
        typical_size_mb: Approximate download size in megabytes (for user warnings)
        supports_streaming: Whether dataset supports streaming mode (HuggingFace only)
        hf_path: Tuple of arguments for load_dataset() (HuggingFace only)
        aliases: Set of alternative names that map to this dataset
        license: Dataset license (for compliance checking)
    """

    def __init__(
        self,
        source: DatasetSource,
        load_function: str,
        typical_size_mb: int,
        supports_streaming: bool = False,
        hf_path: Optional[Tuple[str, ...]] = None,
        aliases: Tuple[str, ...] = (),
        license: str = "unknown",
    ):
        self.source = source
        self.load_function = load_function
        self.typical_size_mb = typical_size_mb
        self.supports_streaming = supports_streaming
        self.hf_path = hf_path
        self.aliases: Set[str] = {normalize_dataset_name(a) for a in aliases}
        self.license = license


def normalize_dataset_name(name: str) -> str:
    """
    Normalize dataset name for consistent matching.

    Handles variations like:
    - Case differences: "SST-2" vs "sst2"
    - Hyphens/underscores: "sst-2" vs "sst_2" vs "sst2"
    - Whitespace: " SST-2 " vs "sst2"

    Args:
        name: Raw dataset name from plan or user input

    Returns:
        Normalized lowercase string with no hyphens/underscores/whitespace

    Examples:
        >>> normalize_dataset_name("SST-2")
        'sst2'
        >>> normalize_dataset_name("Fashion-MNIST")
        'fashionmnist'
        >>> normalize_dataset_name("ag_news")
        'agnews'
    """
    return name.lower().strip().replace("-", "").replace("_", "").replace(" ", "")


# Registry: Map normalized names → metadata
# Phase 2 Initial Seed: 5 datasets covering text, vision, and classic ML
DATASET_REGISTRY: Dict[str, DatasetMetadata] = {
    # ============================================================
    # SKLEARN DATASETS (Bundled - No Download Required)
    # ============================================================
    "digits": DatasetMetadata(
        source=DatasetSource.SKLEARN,
        load_function="load_digits",
        typical_size_mb=1,
        license="BSD-3-Clause",
        aliases=("sklearn_digits", "digit"),
    ),
    "iris": DatasetMetadata(
        source=DatasetSource.SKLEARN,
        load_function="load_iris",
        typical_size_mb=1,
        license="BSD-3-Clause",
        aliases=("sklearn_iris",),
    ),
    # ============================================================
    # TORCHVISION DATASETS (Download on First Use)
    # ============================================================
    "mnist": DatasetMetadata(
        source=DatasetSource.TORCHVISION,
        load_function="MNIST",
        typical_size_mb=15,
        license="CC-BY-SA-3.0",
        aliases=("mnist_vision", "torch_mnist"),
    ),
    # ============================================================
    # HUGGINGFACE DATASETS (Streaming or Cached Download)
    # ============================================================
    "sst2": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=67,
        supports_streaming=True,
        hf_path=("glue", "sst2"),
        license="other",  # GLUE has custom license
        aliases=("sst-2", "glue/sst2", "sst_2", "gluesst2", "stanford_sentiment"),
    ),
    "imdb": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=130,
        supports_streaming=True,
        hf_path=("imdb",),
        license="apache-2.0",
        aliases=("imdb_reviews", "imdb_sentiment"),
    ),
    "agnews": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=35,
        supports_streaming=True,
        hf_path=("ag_news",),
        license="apache-2.0",
        aliases=("ag_news", "ag", "ag-news"),
    ),
    "yahooanswerstopics": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=450,
        supports_streaming=True,
        hf_path=("yahoo_answers_topics",),
        license="unknown",
        aliases=("yahoo_answers_topics", "yahoo_answers", "yah_a", "yahoo-answers"),
    ),
    "yelppolarity": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=200,
        supports_streaming=True,
        hf_path=("yelp_polarity",),
        license="unknown",
        aliases=("yelp_polarity", "yelp_p", "yelp-polarity", "yelp"),
    ),
    "trec": DatasetMetadata(
        source=DatasetSource.HUGGINGFACE,
        load_function="load_dataset",
        typical_size_mb=1,
        supports_streaming=False,
        hf_path=("trec",),
        license="unknown",
        aliases=("trec-6",),
    ),
    # ============================================================
    # TORCHVISION DATASETS (Additional Vision Datasets)
    # ============================================================
    "cifar10": DatasetMetadata(
        source=DatasetSource.TORCHVISION,
        load_function="CIFAR10",
        typical_size_mb=170,
        license="MIT",
        aliases=("cifar_10", "cifar-10"),
    ),
    "cifar100": DatasetMetadata(
        source=DatasetSource.TORCHVISION,
        load_function="CIFAR100",
        typical_size_mb=169,
        license="MIT",
        aliases=("cifar_100", "cifar-100"),
    ),
}


def lookup_dataset(name: str) -> Optional[DatasetMetadata]:
    """
    Find dataset metadata by name with flexible matching.

    Lookup strategy:
    1. Normalize the input name
    2. Try exact match in registry keys
    3. Try alias match across all datasets
    4. Return None if not found (caller should fallback to synthetic)

    Args:
        name: Dataset name from plan.dataset.name (e.g., "SST-2", "mnist", "digits")

    Returns:
        DatasetMetadata if found, None otherwise

    Examples:
        >>> meta = lookup_dataset("SST-2")
        >>> meta.source == DatasetSource.HUGGINGFACE
        True
        >>> meta = lookup_dataset("glue/sst2")  # Alias match
        >>> meta.hf_path
        ('glue', 'sst2')
        >>> lookup_dataset("unknown_dataset")  # Returns None
        None
    """
    normalized = normalize_dataset_name(name)

    # Try exact match in registry keys
    if normalized in DATASET_REGISTRY:
        return DATASET_REGISTRY[normalized]

    # Try alias match across all datasets
    for dataset_name, metadata in DATASET_REGISTRY.items():
        if normalized in metadata.aliases:
            return metadata

    # Not found - caller should fallback to synthetic
    return None


def get_all_dataset_names() -> list[str]:
    """
    Get all registered dataset names (for debugging/docs).

    Returns:
        List of all primary dataset names in the registry
    """
    return sorted(DATASET_REGISTRY.keys())


def get_datasets_by_source(source: DatasetSource) -> list[str]:
    """
    Get all datasets from a specific source.

    Args:
        source: DatasetSource to filter by

    Returns:
        List of dataset names from that source

    Examples:
        >>> get_datasets_by_source(DatasetSource.SKLEARN)
        ['digits', 'iris']
    """
    return sorted(
        name for name, meta in DATASET_REGISTRY.items() if meta.source == source
    )


# Blocked datasets (large, restricted license, or otherwise problematic)
# These will be omitted from plans with a warning instead of causing hard failures
BLOCKED_DATASETS = {
    "imagenet",
    "imagenet1k",
    "imagenet2012",
    "imagenet21k",
    "openimages",
    "yfcc100m",
}


def is_dataset_blocked(name: str) -> bool:
    """
    Check if a dataset is blocked (large, restricted, etc.).

    Args:
        name: Dataset name to check

    Returns:
        True if dataset is in the blocked list

    Examples:
        >>> is_dataset_blocked("ImageNet")
        True
        >>> is_dataset_blocked("sst2")
        False
    """
    normalized = normalize_dataset_name(name)
    return normalized in BLOCKED_DATASETS
