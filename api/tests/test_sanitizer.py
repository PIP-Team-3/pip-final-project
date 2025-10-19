"""
Unit tests for plan sanitizer.

Tests type coercion, key pruning, dataset resolution, and justification extraction.
"""

import pytest
from app.materialize.sanitizer import (
    coerce_value,
    prune_dict,
    is_dataset_allowed,
    resolve_dataset_name,
    extract_justification,
    sanitize_plan,
    BLOCKED_DATASETS,
)
from app.materialize.generators.dataset_registry import (
    DATASET_REGISTRY,
    normalize_dataset_name,
)


class TestCoerceValue:
    """Test type coercion for string numbers, booleans, and nulls."""

    def test_coerce_string_int(self):
        assert coerce_value("10") == 10
        assert coerce_value("0") == 0
        assert coerce_value("-5") == -5

    def test_coerce_string_float(self):
        assert coerce_value("0.5") == 0.5
        assert coerce_value("3.14") == 3.14
        assert coerce_value("-2.5") == -2.5

    def test_coerce_string_bool(self):
        assert coerce_value("true") is True
        assert coerce_value("True") is True
        assert coerce_value("TRUE") is True
        assert coerce_value("false") is False
        assert coerce_value("False") is False
        assert coerce_value("FALSE") is False

    def test_coerce_string_null(self):
        assert coerce_value("null") is None
        assert coerce_value("None") is None
        assert coerce_value("NULL") is None

    def test_coerce_non_numeric_string(self):
        # Non-numeric strings should remain strings
        assert coerce_value("hello") == "hello"
        assert coerce_value("SST-2") == "SST-2"

    def test_coerce_list(self):
        result = coerce_value(["10", "0.5", "true", "hello"])
        assert result == [10, 0.5, True, "hello"]

    def test_coerce_dict(self):
        result = coerce_value({
            "count": "5",
            "rate": "0.1",
            "enabled": "true",
            "name": "test"
        })
        assert result == {
            "count": 5,
            "rate": 0.1,
            "enabled": True,
            "name": "test"
        }

    def test_coerce_nested(self):
        result = coerce_value({
            "data": [
                {"value": "10", "active": "true"},
                {"value": "20", "active": "false"}
            ]
        })
        assert result == {
            "data": [
                {"value": 10, "active": True},
                {"value": 20, "active": False}
            ]
        }

    def test_coerce_already_correct_types(self):
        # Already-correct types should pass through
        assert coerce_value(42) == 42
        assert coerce_value(3.14) == 3.14
        assert coerce_value(True) is True
        assert coerce_value(None) is None


class TestPruneDict:
    """Test key pruning (simulate additionalProperties: false)."""

    def test_prune_removes_unknown_keys(self):
        data = {"a": 1, "b": 2, "extra": 3, "another": 4}
        allowed = {"a", "b"}
        result = prune_dict(data, allowed)
        assert result == {"a": 1, "b": 2}

    def test_prune_keeps_all_allowed(self):
        data = {"a": 1, "b": 2}
        allowed = {"a", "b", "c"}
        result = prune_dict(data, allowed)
        assert result == {"a": 1, "b": 2}

    def test_prune_empty_allowed(self):
        data = {"a": 1, "b": 2}
        allowed = set()
        result = prune_dict(data, allowed)
        assert result == {}


class TestDatasetResolution:
    """Test dataset name resolution and blocking."""

    def test_is_dataset_allowed_registry(self):
        # Datasets in registry should be allowed
        assert is_dataset_allowed("sst2", DATASET_REGISTRY) is True
        assert is_dataset_allowed("SST-2", DATASET_REGISTRY) is True  # Alias
        assert is_dataset_allowed("mnist", DATASET_REGISTRY) is True

    def test_is_dataset_allowed_blocked(self):
        # Blocked datasets should not be allowed
        assert is_dataset_allowed("imagenet", DATASET_REGISTRY) is False
        assert is_dataset_allowed("ImageNet", DATASET_REGISTRY) is False
        assert is_dataset_allowed("ImageNet-1K", DATASET_REGISTRY) is False

    def test_is_dataset_allowed_unknown(self):
        # Unknown datasets should not be allowed
        assert is_dataset_allowed("unknown_dataset", DATASET_REGISTRY) is False

    def test_resolve_dataset_name_exact(self):
        # Exact match should return canonical name
        assert resolve_dataset_name("sst2", DATASET_REGISTRY) == "sst2"
        assert resolve_dataset_name("mnist", DATASET_REGISTRY) == "mnist"

    def test_resolve_dataset_name_alias(self):
        # Aliases should resolve to canonical name
        result = resolve_dataset_name("SST-2", DATASET_REGISTRY)
        assert result == "sst2"

        result = resolve_dataset_name("glue/sst2", DATASET_REGISTRY)
        assert result == "sst2"

        result = resolve_dataset_name("ag_news", DATASET_REGISTRY)
        assert result == "agnews"

    def test_resolve_dataset_name_blocked(self):
        # Blocked datasets should return None
        assert resolve_dataset_name("imagenet", DATASET_REGISTRY) is None
        assert resolve_dataset_name("ImageNet", DATASET_REGISTRY) is None

    def test_resolve_dataset_name_unknown(self):
        # Unknown datasets should return None
        assert resolve_dataset_name("unknown_dataset", DATASET_REGISTRY) is None


class TestExtractJustification:
    """Test justification extraction from prose."""

    def test_extract_with_citation(self):
        prose = "The paper uses SST-2 dataset with 67k training samples (Section 3.1)"
        result = extract_justification(prose, "dataset")
        assert result["quote"] == "The paper uses SST-2 dataset with 67k training samples"
        assert result["citation"] == "Section 3.1"

    def test_extract_with_table_citation(self):
        prose = "CNN achieves 88.1% accuracy (Table 2)"
        result = extract_justification(prose, "model")
        assert result["quote"] == "CNN achieves 88.1% accuracy"
        assert result["citation"] == "Table 2"

    def test_extract_with_page_citation(self):
        prose = "Batch size of 32 is used (p. 5)"
        result = extract_justification(prose, "config")
        assert result["quote"] == "Batch size of 32 is used"
        assert result["citation"] == "p. 5"

    def test_extract_no_citation(self):
        prose = "The model uses dropout regularization."
        result = extract_justification(prose, "model")
        assert "dropout regularization" in result["quote"]
        assert result["citation"] == "Inferred from plan (model)"

    def test_extract_empty_prose(self):
        result = extract_justification("", "dataset")
        assert "Justification for dataset" in result["quote"]
        assert result["citation"] == "Inferred from plan (dataset)"


class TestSanitizePlan:
    """Test full plan sanitization workflow."""

    def test_sanitize_type_coercion(self):
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "sst2", "split": "train"},
            "model": {"name": "cnn"},
            "config": {
                "framework": "pytorch",
                "seed": "42",  # String number
                "epochs": "10",  # String number
                "batch_size": "32",  # String number
                "learning_rate": "0.001",  # String float
                "optimizer": "adam"
            },
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
            "estimated_runtime_minutes": "15",  # String number
            "license_compliant": "true",  # String bool
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # Check type coercion worked
        assert isinstance(sanitized["config"]["seed"], int)
        assert sanitized["config"]["seed"] == 42
        assert isinstance(sanitized["config"]["epochs"], int)
        assert isinstance(sanitized["config"]["learning_rate"], float)
        assert isinstance(sanitized["estimated_runtime_minutes"], int)
        assert isinstance(sanitized["license_compliant"], bool)
        assert sanitized["license_compliant"] is True

    def test_sanitize_dataset_alias_resolution(self):
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

        # Check dataset name was normalized
        assert sanitized["dataset"]["name"] == "sst2"
        # Check for normalization warning
        assert any("normalized" in w.lower() for w in warnings)

    def test_sanitize_blocked_dataset(self):
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

    def test_sanitize_unknown_dataset(self):
        raw_plan = {
            "version": "1.1",
            "dataset": {"name": "unknown_dataset", "split": "train"},
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

        # Should raise ValueError (dataset not in registry)
        with pytest.raises(ValueError, match="No allowed datasets"):
            sanitize_plan(raw_plan, DATASET_REGISTRY, {})

    def test_sanitize_missing_justifications(self):
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
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            # Missing justifications entirely
            "estimated_runtime_minutes": 15,
            "license_compliant": True,
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # Should add placeholder justifications
        assert "justifications" in sanitized
        assert "dataset" in sanitized["justifications"]
        assert "model" in sanitized["justifications"]
        assert "config" in sanitized["justifications"]

        # Check warnings for missing justifications
        assert any("missing justification" in w.lower() for w in warnings)

    def test_sanitize_prose_justifications(self):
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
            "metrics": ["accuracy"],
            "visualizations": ["training_curve"],
            # Justifications as prose (Stage 1 format)
            "justifications": {
                "dataset": "The paper uses SST-2 with 67k samples (Section 3.1)",
                "model": "CNN with multichannel architecture (Table 2)",
                "config": "Batch size 32, learning rate 0.001 (Appendix A)"
            },
            "estimated_runtime_minutes": 15,
            "license_compliant": True,
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {})

        # Should convert prose to {quote, citation} structure
        assert isinstance(sanitized["justifications"]["dataset"], dict)
        assert "quote" in sanitized["justifications"]["dataset"]
        assert "citation" in sanitized["justifications"]["dataset"]
        assert "Section 3.1" in sanitized["justifications"]["dataset"]["citation"]

    def test_sanitize_missing_defaults(self):
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
            # Missing metrics, visualizations, estimated_runtime_minutes, license_compliant
            "justifications": {
                "dataset": {"quote": "test", "citation": "test"},
                "model": {"quote": "test", "citation": "test"},
                "config": {"quote": "test", "citation": "test"}
            },
        }

        sanitized, warnings = sanitize_plan(raw_plan, DATASET_REGISTRY, {"budget_minutes": 20})

        # Should add defaults
        assert "metrics" in sanitized
        assert "accuracy" in sanitized["metrics"]
        assert "visualizations" in sanitized
        assert "training_curve" in sanitized["visualizations"]
        assert sanitized["estimated_runtime_minutes"] == 20
        assert "license_compliant" in sanitized

        # Check warnings for defaults
        assert len(warnings) > 0
