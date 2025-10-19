"""
Regression test for version literal validation bug.

Reproduces the exact scenario where Stage 2 output causes schema validation to fail
with "Input should be '1.1'" error.
"""

import pytest
from app.materialize.sanitizer import sanitize_plan
from app.materialize.generators.dataset_registry import DATASET_REGISTRY
from app.schemas.plan_v1_1 import PlanDocumentV11


class TestVersionLiteralRegression:
    """Regression tests for version literal validation."""

    def test_version_as_string_passes_validation(self):
        """
        REGRESSION TEST: Ensure sanitized plan with version="1.1" (string)
        passes PlanDocumentV11 validation.

        This was the root cause of F1 blocker - Stage 2 sometimes returned
        version as float 1.1, which failed Pydantic's Literal["1.1"].
        """
        # Simulate Stage 2 output with version as string
        raw_plan = {
            "version": "1.1",  # String literal (what Stage 2 SHOULD return)
            "dataset": {"name": "sst2", "split": "train", "filters": []},
            "model": {"name": "cnn", "size_category": "tiny"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": [{"name": "accuracy", "split": "test"}],
            "visualizations": ["training_curve"],
            "explain": ["This is a test explanation"],
            "justifications": {
                "dataset": {"quote": "Paper uses SST-2", "citation": "Section 3"},
                "model": {"quote": "CNN architecture", "citation": "Table 1"},
                "config": {"quote": "Training config", "citation": "Page 5"}
            },
            "estimated_runtime_minutes": 15.0,
            "license_compliant": True,
            "policy": {"budget_minutes": 20, "max_retries": 1}
        }

        # Run sanitizer
        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {"budget_minutes": 20})

        # Verify sanitizer keeps version as string
        assert sanitized["version"] == "1.1"
        assert isinstance(sanitized["version"], str)

        # Verify Pydantic validation passes
        plan_model = PlanDocumentV11.model_validate(sanitized)
        assert plan_model.version == "1.1"

    def test_version_as_float_gets_fixed_by_sanitizer(self):
        """
        REGRESSION TEST: Even if Stage 2 returns version as float 1.1,
        sanitizer should enforce string literal "1.1".

        The sanitizer's coerce_value() function converts "1.1" → 1.1 (float),
        but then line 381 enforces pruned["version"] = "1.1" (string).
        """
        # Simulate Stage 2 output with version as float (the bug scenario)
        raw_plan = {
            "version": 1.1,  # Float (what was causing the bug)
            "dataset": {"name": "sst2", "split": "train", "filters": []},
            "model": {"name": "cnn", "size_category": "tiny"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": [{"name": "accuracy", "split": "test"}],
            "visualizations": ["training_curve"],
            "explain": ["This is a test explanation"],
            "justifications": {
                "dataset": {"quote": "Paper uses SST-2", "citation": "Section 3"},
                "model": {"quote": "CNN architecture", "citation": "Table 1"},
                "config": {"quote": "Training config", "citation": "Page 5"}
            },
            "estimated_runtime_minutes": 15.0,
            "license_compliant": True,
            "policy": {"budget_minutes": 20, "max_retries": 1}
        }

        # Run sanitizer
        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {"budget_minutes": 20})

        # CRITICAL: Sanitizer must convert float 1.1 → string "1.1"
        assert sanitized["version"] == "1.1"
        assert isinstance(sanitized["version"], str), "Sanitizer must enforce version as string"

        # Verify Pydantic validation passes
        plan_model = PlanDocumentV11.model_validate(sanitized)
        assert plan_model.version == "1.1"

    def test_version_missing_gets_defaulted(self):
        """
        EDGE CASE: If Stage 2 somehow omits version, sanitizer should add it.
        """
        raw_plan = {
            # No version field
            "dataset": {"name": "sst2", "split": "train", "filters": []},
            "model": {"name": "cnn", "size_category": "tiny"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": [{"name": "accuracy", "split": "test"}],
            "visualizations": ["training_curve"],
            "explain": ["This is a test explanation"],
            "justifications": {
                "dataset": {"quote": "Paper uses SST-2", "citation": "Section 3"},
                "model": {"quote": "CNN architecture", "citation": "Table 1"},
                "config": {"quote": "Training config", "citation": "Page 5"}
            },
            "estimated_runtime_minutes": 15.0,
            "license_compliant": True,
            "policy": {"budget_minutes": 20, "max_retries": 1}
        }

        # Run sanitizer
        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {"budget_minutes": 20})

        # Sanitizer should add version
        assert "version" in sanitized
        assert sanitized["version"] == "1.1"
        assert isinstance(sanitized["version"], str)

        # Verify Pydantic validation passes
        plan_model = PlanDocumentV11.model_validate(sanitized)
        assert plan_model.version == "1.1"
