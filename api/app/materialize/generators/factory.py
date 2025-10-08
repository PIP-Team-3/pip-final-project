"""
Factory for selecting appropriate code generators based on plan.

Phase 1: Always returns SyntheticDatasetGenerator and SklearnLogisticGenerator
         (no behavior change from current notebook.py)

Phase 2+: Smart selection based on plan.dataset.name and plan.model.name
          with fallback chains for graceful degradation
"""

from __future__ import annotations

from .base import CodeGenerator
from .dataset import SyntheticDatasetGenerator
from .model import SklearnLogisticGenerator
from ...schemas.plan_v1_1 import PlanDocumentV11


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

        Phase 1: Always returns SyntheticDatasetGenerator (no behavior change).

        Args:
            plan: The plan document containing dataset info

        Returns:
            CodeGenerator instance for dataset loading
        """
        # Phase 1: Always synthetic (exact current behavior)
        # Future: Check plan.dataset.name and select:
        #   - SklearnDatasetGenerator for digits/iris/wine
        #   - TorchvisionDatasetGenerator for mnist/cifar10
        #   - HuggingFaceDatasetGenerator for sst2/imdb
        #   - SyntheticDatasetGenerator as fallback
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
