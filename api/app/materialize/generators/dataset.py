"""
Dataset code generators.

Phase 1: SyntheticDatasetGenerator (extracts current notebook.py logic)
Phase 2+: SklearnDatasetGenerator, TorchvisionDatasetGenerator, HuggingFaceDatasetGenerator
"""

from __future__ import annotations

import textwrap
from typing import List

from .base import CodeGenerator
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
