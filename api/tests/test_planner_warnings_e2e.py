"""
E2E smoke test for planner warning propagation.

Validates that warnings flow through the entire pipeline:
- Sanitizer generates warnings
- Warnings appear in API response
- Warnings are logged properly
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.materialize.sanitizer import sanitize_plan
from app.materialize.generators.dataset_registry import DATASET_REGISTRY


class TestWarningPropagation:
    """Test that warnings propagate through the system."""

    def test_sanitizer_warnings_for_blocked_dataset(self):
        """Blocked dataset should generate warning."""
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "ImageNet", "split": "train"},  # Blocked
            "model": {"name": "resnet"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "sgd"
            },
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
            "estimated_runtime_minutes": 20,
            "license_compliant": True,
        }

        # Should raise ValueError (no allowed datasets)
        with pytest.raises(ValueError, match="No allowed datasets"):
            sanitize_plan(raw_plan, DATASET_REGISTRY, {})

    def test_sanitizer_warnings_for_alias_normalization(self):
        """Dataset alias should generate normalization warning."""
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "SST-2", "split": "train"},  # Alias
            "model": {"name": "cnn"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
            "estimated_runtime_minutes": 15,
            "license_compliant": True,
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # Should have normalization warning
        assert len(warnings) > 0
        assert any("normalized" in w.lower() for w in warnings)
        assert any("SST-2" in w and "sst2" in w for w in warnings)

        # Dataset should be normalized
        assert sanitized["dataset"]["name"] == "sst2"

    def test_sanitizer_warnings_for_missing_defaults(self):
        """Missing fields should generate default warnings."""
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "sst2", "split": "train"},
            "model": {"name": "cnn"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            # Missing metrics, visualizations, estimated_runtime, license_compliant
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {"budget_minutes": 20})

        # Should have warnings for defaults
        assert len(warnings) >= 3
        assert any("metrics" in w.lower() for w in warnings)
        assert any("visualizations" in w.lower() for w in warnings)
        assert any("runtime" in w.lower() for w in warnings)

        # Defaults should be added
        assert "accuracy" in sanitized["metrics"]
        assert "training_curve" in sanitized["visualizations"]
        assert sanitized["estimated_runtime_minutes"] == 20

    def test_zero_warnings_for_perfect_plan(self):
        """Perfect plan should have zero warnings (F2 validation)."""
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "sst2", "split": "train"},  # Already canonical
            "model": {"name": "cnn"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
            "estimated_runtime_minutes": 15,
            "license_compliant": True,
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # ZERO warnings for perfect plan (F2 contract)
        assert len(warnings) == 0
        assert sanitized["dataset"]["name"] == "sst2"


class TestWarningLogging:
    """Test that warnings are logged properly."""

    @patch('app.materialize.sanitizer.logger')
    def test_sanitizer_logs_blocked_dataset(self, mock_logger):
        """Blocked dataset should be logged."""
        from app.materialize.sanitizer import resolve_dataset_name

        result = resolve_dataset_name("ImageNet", DATASET_REGISTRY)

        # Should return None
        assert result is None

        # Should log blocked
        assert mock_logger.info.called
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("blocked" in str(call).lower() for call in calls)

    @patch('app.materialize.sanitizer.logger')
    def test_sanitizer_logs_unknown_dataset(self, mock_logger):
        """Unknown dataset should be logged as warning."""
        from app.materialize.sanitizer import resolve_dataset_name

        result = resolve_dataset_name("unknown_dataset", DATASET_REGISTRY)

        # Should return None
        assert result is None

        # Should log warning
        assert mock_logger.warning.called
        calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("unknown" in str(call).lower() for call in calls)

    @patch('app.materialize.sanitizer.logger')
    def test_sanitizer_logs_completion(self, mock_logger):
        """Sanitizer should log completion with warnings count."""
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "SST-2", "split": "train"},  # Will normalize
            "model": {"name": "cnn"},
            "config": {
                "framework": "pytorch",
                "seed": 42,
                "epochs": 10,
                "batch_size": 32,
                "learning_rate": 0.001,
                "optimizer": "adam"
            },
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
            "estimated_runtime_minutes": 15,
            "license_compliant": True,
        }

        sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # Should log completion
        assert mock_logger.info.called
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("sanitizer.complete" in str(call) for call in calls)
        assert any("warnings_count" in str(call) for call in calls)


class TestF2PreparationZeroWarnings:
    """
    Tests for F2 preparation: Assert zero warnings when only registry datasets appear.

    These tests validate the "perfect plan" contract that F2 (registry-only prompts)
    should achieve.
    """

    def test_registry_only_plan_has_zero_warnings(self):
        """Plan with only registry datasets should have zero warnings."""
        test_cases = [
            {"name": "sst2", "expected_warnings": 0},
            {"name": "mnist", "expected_warnings": 0},
            {"name": "digits", "expected_warnings": 0},
            {"name": "imdb", "expected_warnings": 0},
            {"name": "cifar10", "expected_warnings": 0},
        ]

        for case in test_cases:
            raw_plan = {
                "version": "1.1",
                "dataset": {"name": case["name"], "split": "train"},
                "model": {"name": "cnn"},
                "config": {
                    "framework": "pytorch",
                    "seed": 42,
                    "epochs": 10,
                    "batch_size": 32,
                    "learning_rate": 0.001,
                    "optimizer": "adam"
                },
                "metrics": ["accuracy"],
                "visualizations": ["training_curve"],
                "justifications": {
                    "dataset": {"quote": "test", "citation": "test"},
                    "model": {"quote": "test", "citation": "test"},
                    "config": {"quote": "test", "citation": "test"}
                },
                "estimated_runtime_minutes": 15,
                "license_compliant": True,
            }

            sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

            assert len(warnings) == case["expected_warnings"], (
                f"Dataset {case['name']} should have {case['expected_warnings']} warnings, "
                f"got {len(warnings)}: {warnings}"
            )
