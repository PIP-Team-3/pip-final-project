"""
Dataset code generators.

Phase 1: SyntheticDatasetGenerator (extracts current notebook.py logic)
Phase 2: SklearnDatasetGenerator, TorchvisionDatasetGenerator, HuggingFaceDatasetGenerator
"""

from __future__ import annotations

import textwrap
from typing import List

from .base import CodeGenerator
from .dataset_registry import DatasetMetadata
from ...schemas.plan_v1_1 import PlanDocumentV11


class SyntheticDatasetGenerator(CodeGenerator):
    """
    Generates synthetic classification data using sklearn.datasets.make_classification.

    Phase 1: This extracts the EXACT current logic from notebook.py (lines 111-140).
    No behavior change - ensures regression-free refactor.

    Future: This will be used as fallback when real datasets unavailable.
    """

    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """Import statements for synthetic data generation."""
        return [
            "from sklearn.datasets import make_classification",
            "from sklearn.model_selection import train_test_split",
        ]

    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate synthetic classification dataset.

        Creates 512 samples with 32 features, then splits 80/20 train/test.
        Logs dataset_load event and dataset_samples metric.
        """
        return textwrap.dedent(
            f"""
        log_event(
            "stage_update",
            {{
                "stage": "dataset_load",
                "dataset": "{plan.dataset.name}",
                "split": "{plan.dataset.split}",
            }},
        )

        X, y = make_classification(
            n_samples=512,
            n_features=32,
            n_informative=16,
            n_redundant=4,
            random_state=SEED,
        )
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=SEED
        )
        log_event(
            "metric_update",
            {{"metric": "dataset_samples", "value": int(X.shape[0])}},
        )
        """
        ).strip()

    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """Pip requirements for synthetic data generation."""
        return ["scikit-learn==1.5.1"]


class SklearnDatasetGenerator(CodeGenerator):
    """
    Generates code to load sklearn built-in datasets.

    These datasets are bundled with sklearn (no download required):
    - digits: 8x8 images of handwritten digits
    - iris: Classic iris flower classification
    - wine: Wine recognition dataset
    - breast_cancer: Wisconsin breast cancer dataset

    The data is already on disk when sklearn is installed, making this
    the fastest dataset loading option.
    """

    def __init__(self, metadata: DatasetMetadata):
        """
        Initialize with dataset metadata.

        Args:
            metadata: Dataset metadata from registry
        """
        self.metadata = metadata

    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """Import statements for sklearn dataset loading."""
        return [
            f"from sklearn.datasets import {self.metadata.load_function}",
            "from sklearn.model_selection import train_test_split",
        ]

    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate code to load sklearn dataset.

        Features:
        - No downloads (bundled with sklearn)
        - Deterministic train/test split with SEED
        - Logs dataset_load and dataset_samples events
        """
        dataset_name = plan.dataset.name
        load_func = self.metadata.load_function

        return textwrap.dedent(
            f"""
        # Dataset: {dataset_name} (sklearn built-in - no download)
        log_event("stage_update", {{"stage": "dataset_load", "dataset": "{dataset_name}"}})

        # Load dataset (bundled with sklearn)
        X, y = {load_func}(return_X_y=True)

        # Split train/test with deterministic seed
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=SEED
        )

        log_event("metric_update", {{"metric": "dataset_samples", "value": int(X.shape[0])}})
        """
        ).strip()

    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """Pip requirements for sklearn dataset loading."""
        return ["scikit-learn==1.5.1"]


class TorchvisionDatasetGenerator(CodeGenerator):
    """
    Generates code to load torchvision datasets with caching.

    Supports vision datasets like:
    - MNIST: Handwritten digits (60k train, 10k test)
    - FashionMNIST: Fashion items (60k train, 10k test)
    - CIFAR10: 32x32 color images (50k train, 10k test)

    Features:
    - Downloads on first use, then caches locally
    - Respects OFFLINE_MODE environment variable
    - Subsamples for CPU budget (MAX_TRAIN_SAMPLES)
    - Converts to numpy for sklearn model compatibility (Phase 2)
    """

    def __init__(self, metadata: DatasetMetadata):
        """
        Initialize with dataset metadata.

        Args:
            metadata: Dataset metadata from registry
        """
        self.metadata = metadata

    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """Import statements for torchvision dataset loading."""
        return [
            "from torchvision import datasets, transforms",
            "import numpy as np",
            "import os",
        ]

    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate code to load torchvision dataset with caching.

        Cache behavior:
        - Uses DATASET_CACHE_DIR (default: ./data)
        - download=True checks cache first, only downloads if missing
        - OFFLINE_MODE=true skips download (fails if not cached)

        Resource management:
        - Subsamples to MAX_TRAIN_SAMPLES for CPU budget
        - Flattens images to 1D for sklearn compatibility
        """
        dataset_name = plan.dataset.name
        dataset_class = self.metadata.load_function

        return textwrap.dedent(
            f"""
        # Dataset: {dataset_name} (Torchvision - cached download)
        CACHE_DIR = os.getenv("DATASET_CACHE_DIR", "./data")
        OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"

        log_event("stage_update", {{"stage": "dataset_load", "dataset": "{dataset_name}"}})

        # Basic transforms (normalize to [0, 1])
        transform = transforms.Compose([
            transforms.ToTensor(),
        ])

        # Download=True checks cache first! Only downloads if missing.
        train_dataset = datasets.{dataset_class}(
            root=CACHE_DIR,
            train=True,
            download=not OFFLINE_MODE,  # Skip download if offline
            transform=transform
        )

        test_dataset = datasets.{dataset_class}(
            root=CACHE_DIR,
            train=False,
            download=not OFFLINE_MODE,
            transform=transform
        )

        # Convert to numpy and flatten for sklearn compatibility (Phase 2)
        X_train = train_dataset.data.numpy().reshape(len(train_dataset), -1)
        y_train = np.array(train_dataset.targets)

        X_test = test_dataset.data.numpy().reshape(len(test_dataset), -1)
        y_test = np.array(test_dataset.targets)

        # Subsample for CPU budget (20 min limit)
        MAX_SAMPLES = int(os.getenv("MAX_TRAIN_SAMPLES", "5000"))
        if len(X_train) > MAX_SAMPLES:
            indices = np.random.RandomState(SEED).choice(len(X_train), MAX_SAMPLES, replace=False)
            X_train, y_train = X_train[indices], y_train[indices]

        log_event("metric_update", {{"metric": "dataset_samples", "value": len(X_train)}})
        """
        ).strip()

    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """Pip requirements for torchvision dataset loading."""
        return [
            "torch==2.1.0",
            "torchvision==0.16.0",
            "numpy==1.26.0",
        ]


class HuggingFaceDatasetGenerator(CodeGenerator):
    """
    Generates code to load HuggingFace datasets with streaming support.

    Supports text datasets like:
    - SST-2: Stanford Sentiment Treebank (67MB)
    - IMDB: Movie reviews (130MB)
    - AG News: News articles (20MB)
    - TREC: Question classification (5MB)

    Features:
    - Lazy loading with caching
    - Streaming mode for huge datasets
    - OFFLINE_MODE support
    - Converts to sklearn-compatible format (Phase 2: bag-of-words)
    """

    def __init__(self, metadata: DatasetMetadata):
        """
        Initialize with dataset metadata.

        Args:
            metadata: Dataset metadata from registry
        """
        self.metadata = metadata

    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """Import statements for HuggingFace dataset loading."""
        return [
            "from datasets import load_dataset",
            "from sklearn.feature_extraction.text import CountVectorizer",
            "from sklearn.model_selection import train_test_split",
            "import os",
        ]

    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate code to load HuggingFace dataset with caching.

        Cache behavior:
        - Uses DATASET_CACHE_DIR (default: ./data/cache)
        - download_mode="reuse_dataset_if_exists" reuses cache
        - OFFLINE_MODE=true fails if not cached

        Preprocessing (Phase 2):
        - Converts text to bag-of-words (CountVectorizer)
        - This allows sklearn models (LogisticRegression) to work
        - Phase 3 will add real NLP models (TextCNN, BERT)
        """
        dataset_name = plan.dataset.name
        hf_path = self.metadata.hf_path
        hf_path_str = ", ".join(f'"{p}"' for p in hf_path)
        split = plan.dataset.split or "train"

        return textwrap.dedent(
            f"""
        # Dataset: {dataset_name} (HuggingFace - cached download)
        CACHE_DIR = os.getenv("DATASET_CACHE_DIR", "./data/cache")
        OFFLINE_MODE = os.getenv("OFFLINE_MODE", "false").lower() == "true"

        log_event("stage_update", {{"stage": "dataset_load", "dataset": "{dataset_name}"}})

        # Load with caching (downloads only if not cached)
        dataset = load_dataset(
            {hf_path_str},
            cache_dir=CACHE_DIR,
            download_mode="reuse_dataset_if_exists",  # Reuse cache if available
        )

        # Extract split
        split_name = "{split}" if "{split}" in dataset else "train"
        train_data = dataset[split_name]

        # Convert to sklearn-compatible format
        # Phase 2: Simple bag-of-words (Phase 3 will add real NLP models)

        # Detect text field (common field names)
        text_field = None
        for field in ["sentence", "text", "content", "review"]:
            if field in train_data.features:
                text_field = field
                break

        if text_field is None:
            raise ValueError(f"Could not find text field in dataset. Available fields: {{list(train_data.features.keys())}}")

        # Extract texts and labels
        texts = [row[text_field] for row in train_data]

        # Detect label field
        label_field = "label" if "label" in train_data.features else list(train_data.features.keys())[1]
        labels = [row[label_field] for row in train_data]

        # Vectorize text (bag-of-words for sklearn compatibility)
        MAX_FEATURES = int(os.getenv("MAX_BOW_FEATURES", "1000"))
        vectorizer = CountVectorizer(max_features=MAX_FEATURES, random_state=SEED)
        X = vectorizer.fit_transform(texts).toarray()
        y = np.array(labels)

        # Subsample for CPU budget
        MAX_SAMPLES = int(os.getenv("MAX_TRAIN_SAMPLES", "5000"))
        if len(X) > MAX_SAMPLES:
            indices = np.random.RandomState(SEED).choice(len(X), MAX_SAMPLES, replace=False)
            X, y = X[indices], y[indices]

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=SEED
        )

        log_event("metric_update", {{"metric": "dataset_samples", "value": len(X)}})
        """
        ).strip()

    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """Pip requirements for HuggingFace dataset loading."""
        return [
            "datasets>=2.14.0",
            "scikit-learn==1.5.1",
            "numpy==1.26.0",
        ]
