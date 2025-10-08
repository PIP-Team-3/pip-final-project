"""
Code generators for notebook materialization.

This package provides modular code generators following the factory pattern:
- base.py: Abstract base class (CodeGenerator)
- dataset.py: Dataset loading code generators
- model.py: Model building code generators
- factory.py: Factory for selecting appropriate generators

Phase 1: Extracts current logic into modular components (no behavior change)
Phase 2+: Add smart dataset/model selection based on plan
"""

from .base import CodeGenerator
from .dataset import SyntheticDatasetGenerator
from .factory import GeneratorFactory
from .model import SklearnLogisticGenerator

__all__ = [
    "CodeGenerator",
    "GeneratorFactory",
    "SyntheticDatasetGenerator",
    "SklearnLogisticGenerator",
]
