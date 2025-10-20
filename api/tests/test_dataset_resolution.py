"""
Unit tests for dataset resolution classifier.

Tests the Phase A: Dataset Resolution Assistant functionality.
"""

import pytest
from app.materialize.dataset_resolution import (
    classify_dataset,
    ResolutionStatus,
    DatasetResolutionResult,
    normalize_dataset_name,
    is_complex_dataset,
    resolve_dataset_for_plan,
)
from app.materialize.generators.dataset_registry import DATASET_REGISTRY
from app.materialize.sanitizer import BLOCKED_DATASETS


class TestNormalizeDatasetName:
    """Test dataset name normalization."""

    def test_lowercase_conversion(self):
        assert normalize_dataset_name("SST-2") == "sst2"
        assert normalize_dataset_name("ImageNet") == "imagenet"

    def test_punctuation_removal(self):
        assert normalize_dataset_name("AG-News") == "agnews"
        assert normalize_dataset_name("NYC_Taxi+NOAA") == "nyctaxinoaa"

    def test_whitespace_removal(self):
        assert normalize_dataset_name("My Custom Dataset") == "mycustomdataset"

    def test_empty_string(self):
        assert normalize_dataset_name("") == ""

    def test_alphanumeric_only(self):
        assert normalize_dataset_name("CIFAR-10") == "cifar10"
        assert normalize_dataset_name("GLUE/SST-2") == "gluesst2"


class TestIsComplexDataset:
    """Test complexity detection heuristics."""

    def test_multi_dataset_indicator(self):
        assert is_complex_dataset("NYC_Taxi+NOAA") is True
        assert is_complex_dataset("ImageNet+Places365") is True

    def test_taxi_weather_pattern(self):
        assert is_complex_dataset("taxi_weather_correlation") is True
        assert is_complex_dataset("weather_taxi_study") is True

    def test_fairness_demographic_pattern(self):
        assert is_complex_dataset("fairness_demographic_parity") is True
        assert is_complex_dataset("demographic_fairness_analysis") is True

    def test_eia_load_pattern(self):
        assert is_complex_dataset("eia_electricity_load") is True
        assert is_complex_dataset("load_eia_930") is True

    def test_simple_datasets_not_complex(self):
        assert is_complex_dataset("SST-2") is False
        assert is_complex_dataset("CIFAR-10") is False
        assert is_complex_dataset("ImageNet") is False


class TestClassifyDataset:
    """Test dataset classification logic."""

    def test_resolved_exact_match(self):
        """Registry dataset with exact name match."""
        result = classify_dataset("sst2", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.canonical_name == "sst2"
        assert result.metadata is not None
        assert "found in registry" in result.reason.lower()

    def test_resolved_alias_match(self):
        """Registry dataset with alias match."""
        result = classify_dataset("SST-2", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.canonical_name == "sst2"
        assert result.reason is not None

    def test_resolved_case_insensitive(self):
        """Registry lookup is case-insensitive."""
        result = classify_dataset("CIFAR10", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.RESOLVED
        assert result.canonical_name == "cifar10"

    def test_blocked_imagenet(self):
        """Blocked dataset (large/restricted)."""
        result = classify_dataset("ImageNet", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.BLOCKED
        assert result.dataset_name == "ImageNet"
        assert "blocked" in result.reason.lower()
        assert len(result.suggestions) > 0
        assert "alternative" in result.suggestions[0].lower()

    def test_blocked_normalized_name(self):
        """Blocked list uses normalized names."""
        result = classify_dataset("Image-Net", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.BLOCKED

    def test_unknown_simple_dataset(self):
        """Unknown dataset without complexity indicators."""
        result = classify_dataset("my_custom_benchmark", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.UNKNOWN
        assert result.dataset_name == "my_custom_benchmark"
        assert "not found in registry" in result.reason.lower()
        assert len(result.suggestions) > 0
        assert any("add" in s.lower() or "registry" in s.lower() for s in result.suggestions)

    def test_complex_multi_dataset(self):
        """Complex dataset with multi-source indicator."""
        result = classify_dataset("NYC_Taxi+NOAA_Weather", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.COMPLEX
        assert result.dataset_name == "NYC_Taxi+NOAA_Weather"
        assert "custom acquisition" in result.reason.lower()
        assert len(result.suggestions) > 0
        assert any("advisor" in s.lower() for s in result.suggestions)

    def test_complex_known_pattern_taxi_weather(self):
        """Complex dataset matching known pattern."""
        result = classify_dataset("taxi_weather_correlation_2015", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.COMPLEX
        assert "preprocessing" in result.reason.lower() or "acquisition" in result.reason.lower()

    def test_complex_eia_pattern(self):
        """Complex dataset matching EIA pattern."""
        result = classify_dataset("eia_demand_load_data", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.COMPLEX

    def test_empty_dataset_name(self):
        """Handle empty dataset name gracefully."""
        result = classify_dataset("", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.UNKNOWN
        assert "no dataset name" in result.reason.lower()

    def test_none_dataset_name(self):
        """Handle None dataset name gracefully."""
        result = classify_dataset(None, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.status == ResolutionStatus.UNKNOWN


class TestResolveDatasetForPlan:
    """Test plan-level dataset resolution."""

    def test_extract_dataset_from_plan(self):
        """Extract and classify dataset from plan dict."""
        plan_dict = {
            "version": "1.1",
            "dataset": {"name": "sst2", "split": "train"},
            "model": {"name": "cnn"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is not None
        assert result.status == ResolutionStatus.RESOLVED
        assert result.dataset_name == "sst2"

    def test_plan_with_alias_dataset(self):
        """Plan uses dataset alias."""
        plan_dict = {
            "dataset": {"name": "AG News", "split": "test"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is not None
        assert result.status == ResolutionStatus.RESOLVED
        assert result.canonical_name == "agnews"

    def test_plan_with_blocked_dataset(self):
        """Plan uses blocked dataset."""
        plan_dict = {
            "dataset": {"name": "ImageNet", "split": "val"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is not None
        assert result.status == ResolutionStatus.BLOCKED

    def test_plan_with_unknown_dataset(self):
        """Plan uses unknown dataset."""
        plan_dict = {
            "dataset": {"name": "proprietary_benchmark", "split": "test"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is not None
        assert result.status == ResolutionStatus.UNKNOWN

    def test_plan_with_complex_dataset(self):
        """Plan uses complex dataset."""
        plan_dict = {
            "dataset": {"name": "NYC_Taxi+NOAA", "split": "jan_2015"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is not None
        assert result.status == ResolutionStatus.COMPLEX

    def test_plan_missing_dataset_section(self):
        """Plan missing dataset section."""
        plan_dict = {
            "version": "1.1",
            "model": {"name": "resnet"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is None

    def test_plan_missing_dataset_name(self):
        """Plan has dataset section but no name."""
        plan_dict = {
            "dataset": {"split": "train"},
        }

        result = resolve_dataset_for_plan(plan_dict, DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result is None


class TestResolutionResultSuggestions:
    """Test that resolution results provide actionable suggestions."""

    def test_resolved_no_suggestions_needed(self):
        """Resolved datasets don't need suggestions (optional)."""
        result = classify_dataset("sst2", DATASET_REGISTRY, BLOCKED_DATASETS)
        # Suggestions optional for RESOLVED status

    def test_blocked_has_alternative_suggestion(self):
        """Blocked datasets suggest alternatives."""
        result = classify_dataset("ImageNet", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.suggestions is not None
        assert len(result.suggestions) > 0
        assert any("alternative" in s.lower() for s in result.suggestions)

    def test_unknown_has_registry_suggestion(self):
        """Unknown datasets suggest adding to registry."""
        result = classify_dataset("new_benchmark", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.suggestions is not None
        assert len(result.suggestions) > 0
        assert any("registry" in s.lower() for s in result.suggestions)

    def test_complex_has_advisor_suggestion(self):
        """Complex datasets suggest Phase B advisor."""
        result = classify_dataset("taxi+weather", DATASET_REGISTRY, BLOCKED_DATASETS)

        assert result.suggestions is not None
        assert len(result.suggestions) > 0
        assert any("advisor" in s.lower() or "adapter" in s.lower() for s in result.suggestions)
