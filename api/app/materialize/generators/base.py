"""
Abstract base class for all code generators.

Defines the interface that all dataset, model, and training generators must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ...schemas.plan_v1_1 import PlanDocumentV11


class CodeGenerator(ABC):
    """
    Base class for all code generators in the materialization pipeline.

    Each generator is responsible for producing a specific section of the notebook:
    - Dataset generators: data loading and preprocessing
    - Model generators: model building, training, and evaluation

    All generators must implement three methods:
    - generate_imports(): Return import statements needed for this code
    - generate_code(): Return the actual Python code to execute
    - generate_requirements(): Return pip packages needed for this code
    """

    @abstractmethod
    def generate_imports(self, plan: PlanDocumentV11) -> List[str]:
        """
        Generate import statements for this code section.

        Args:
            plan: The plan document containing dataset, model, and config info

        Returns:
            List of import statement strings (e.g., ["import numpy as np"])
        """
        pass

    @abstractmethod
    def generate_code(self, plan: PlanDocumentV11) -> str:
        """
        Generate the main Python code for this section.

        Args:
            plan: The plan document containing dataset, model, and config info

        Returns:
            Python code as a string (will be inserted into notebook cell)
        """
        pass

    @abstractmethod
    def generate_requirements(self, plan: PlanDocumentV11) -> List[str]:
        """
        Generate pip requirements for this code section.

        Args:
            plan: The plan document containing dataset, model, and config info

        Returns:
            List of pip requirement strings (e.g., ["scikit-learn==1.5.1"])
        """
        pass
