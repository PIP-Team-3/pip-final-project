"""
Factory for selecting appropriate code generators based on plan.

Phase 1: Always returns SyntheticDatasetGenerator and SklearnLogisticGenerator
         (no behavior change from current notebook.py)

Phase 2: Smart dataset selection based on registry lookup with fallback
Phase 3: Smart model selection (coming soon)
Phase 4: Docker-ready features (coming soon)
"""

from __future__ import annotations

import logging

from .base import CodeGenerator
from .dataset import (
    HuggingFaceDatasetGenerator,
    SklearnDatasetGenerator,
    SyntheticDatasetGenerator,
    TorchvisionDatasetGenerator,
)
from .dataset_registry import DatasetSource, lookup_dataset
from .model import SklearnLogisticGenerator
from ...schemas.plan_v1_1 import PlanDocumentV11

logger = logging.getLogger(__name__)


class GeneratorFactory:
    """
    Factory for selecting appropriate code generators.

    Phase 1 Strategy:
    - Always return synthetic dataset generator (no behavior change)
    - Always return logistic regression model generator (no behavior change)

    This ensures Phase 1 refactor produces IDENTICAL output to current notebook.py.

    Future Phases:
    - Phase 2: Add smart dataset selection (sklearn, torchvision, HuggingFace)
    - Phase 3: Add smart model selection (sklearn models, PyTorch CNN, ResNet)
    - Phase 4: Docker-ready features (env vars, resource checks)
    """

    @staticmethod
    def get_dataset_generator(plan: PlanDocumentV11) -> CodeGenerator:
        """
        Select appropriate dataset generator based on plan.

        Phase 2: Smart selection via registry lookup with graceful fallback.

        Selection strategy:
        1. Lookup plan.dataset.name in registry (handles aliases)
        2. If found: Return appropriate generator based on source
        3. If not found: Return SyntheticDatasetGenerator (graceful fallback)

        Args:
            plan: The plan document containing dataset info

        Returns:
            CodeGenerator instance for dataset loading

        Examples:
            >>> plan.dataset.name = "SST-2"  # Planner output
            >>> gen = GeneratorFactory.get_dataset_generator(plan)
            >>> isinstance(gen, HuggingFaceDatasetGenerator)
            True
            >>> plan.dataset.name = "unknown_dataset"
            >>> gen = GeneratorFactory.get_dataset_generator(plan)
            >>> isinstance(gen, SyntheticDatasetGenerator)
            True
        """
        dataset_name = plan.dataset.name

        # Lookup in registry (handles normalization + aliases)
        metadata = lookup_dataset(dataset_name)

        if metadata is None:
            # Not in registry → fallback to synthetic
            logger.info(
                "Dataset '%s' not in registry, using synthetic fallback",
                dataset_name,
            )
            return SyntheticDatasetGenerator()

        # Log size warning for large datasets
        if metadata.typical_size_mb > 200:
            logger.warning(
                "Dataset '%s' will download ~%dMB on first run. "
                "Consider setting MAX_TRAIN_SAMPLES to reduce size.",
                dataset_name,
                metadata.typical_size_mb,
            )

        # Select generator based on source
        if metadata.source == DatasetSource.SKLEARN:
            logger.info(
                "Dataset '%s' found in registry: sklearn (bundled, no download)",
                dataset_name,
            )
            return SklearnDatasetGenerator(metadata)

        elif metadata.source == DatasetSource.TORCHVISION:
            logger.info(
                "Dataset '%s' found in registry: torchvision (~%dMB download on first use)",
                dataset_name,
                metadata.typical_size_mb,
            )
            return TorchvisionDatasetGenerator(metadata)

        elif metadata.source == DatasetSource.HUGGINGFACE:
            logger.info(
                "Dataset '%s' found in registry: HuggingFace (~%dMB download on first use)",
                dataset_name,
                metadata.typical_size_mb,
            )
            return HuggingFaceDatasetGenerator(metadata)

        else:
            # Unknown source → fallback to synthetic
            logger.warning(
                "Dataset '%s' has unknown source '%s', using synthetic fallback",
                dataset_name,
                metadata.source,
            )
            return SyntheticDatasetGenerator()

    @staticmethod
    def get_model_generator(plan: PlanDocumentV11) -> CodeGenerator:
        """
        Select appropriate model generator based on plan.

        Phase 1: Always returns SklearnLogisticGenerator (no behavior change).

        Args:
            plan: The plan document containing model info

        Returns:
            CodeGenerator instance for model building/training
        """
        # Phase 1: Always logistic regression (exact current behavior)
        # Future: Check plan.model.name and plan.config.framework:
        #   - SklearnModelGenerator for logistic/random_forest/svm
        #   - TorchCNNGenerator for textcnn/simple_cnn
        #   - TorchResNetGenerator for resnet18/resnet50
        #   - SklearnLogisticGenerator as fallback
        return SklearnLogisticGenerator()
