"""
Unit tests for dataset registry.

Tests cover:
- Normalization logic (case, hyphens, underscores)
- Exact match lookups
- Alias matching
- Not found scenarios
- Registry helpers
"""

import pytest

from app.materialize.generators.dataset_registry import (
    DATASET_REGISTRY,
    DatasetMetadata,
    DatasetSource,
    get_all_dataset_names,
    get_datasets_by_source,
    lookup_dataset,
    normalize_dataset_name,
)


class TestNormalization:
    """Test dataset name normalization."""

    def test_normalize_lowercase(self):
        """Uppercase should become lowercase."""
        assert normalize_dataset_name("SST2") == "sst2"
        assert normalize_dataset_name("MNIST") == "mnist"

    def test_normalize_hyphens(self):
        """Hyphens should be removed."""
        assert normalize_dataset_name("sst-2") == "sst2"
        assert normalize_dataset_name("fashion-mnist") == "fashionmnist"

    def test_normalize_underscores(self):
        """Underscores should be removed."""
        assert normalize_dataset_name("sst_2") == "sst2"
        assert normalize_dataset_name("ag_news") == "agnews"

    def test_normalize_whitespace(self):
        """Whitespace should be stripped and removed."""
        assert normalize_dataset_name(" sst2 ") == "sst2"
        assert normalize_dataset_name("ag news") == "agnews"

    def test_normalize_combined(self):
        """Multiple transformations should work together."""
        assert normalize_dataset_name(" SST-2 ") == "sst2"
        assert normalize_dataset_name("Fashion_MNIST") == "fashionmnist"


class TestLookupExactMatch:
    """Test exact match lookups in registry."""

    def test_lookup_digits(self):
        """Sklearn digits dataset should be found."""
        meta = lookup_dataset("digits")
        assert meta is not None
        assert meta.source == DatasetSource.SKLEARN
        assert meta.load_function == "load_digits"
        assert meta.typical_size_mb == 1

    def test_lookup_iris(self):
        """Sklearn iris dataset should be found."""
        meta = lookup_dataset("iris")
        assert meta is not None
        assert meta.source == DatasetSource.SKLEARN
        assert meta.load_function == "load_iris"

    def test_lookup_mnist(self):
        """Torchvision MNIST should be found."""
        meta = lookup_dataset("mnist")
        assert meta is not None
        assert meta.source == DatasetSource.TORCHVISION
        assert meta.load_function == "MNIST"
        assert meta.typical_size_mb == 15

    def test_lookup_sst2(self):
        """HuggingFace SST-2 should be found."""
        meta = lookup_dataset("sst2")
        assert meta is not None
        assert meta.source == DatasetSource.HUGGINGFACE
        assert meta.load_function == "load_dataset"
        assert meta.hf_path == ("glue", "sst2")
        assert meta.supports_streaming is True

    def test_lookup_imdb(self):
        """HuggingFace IMDB should be found."""
        meta = lookup_dataset("imdb")
        assert meta is not None
        assert meta.source == DatasetSource.HUGGINGFACE
        assert meta.hf_path == ("imdb",)
        assert meta.supports_streaming is True


class TestLookupAliases:
    """Test alias matching."""

    def test_sst2_hyphenated_alias(self):
        """SST-2 with hyphen should match via alias."""
        meta = lookup_dataset("sst-2")
        assert meta is not None
        assert meta.source == DatasetSource.HUGGINGFACE
        assert meta.hf_path == ("glue", "sst2")

    def test_sst2_glue_path_alias(self):
        """glue/sst2 should match via alias."""
        meta = lookup_dataset("glue/sst2")
        assert meta is not None
        assert meta.hf_path == ("glue", "sst2")

    def test_sst2_underscore_alias(self):
        """sst_2 should match via alias."""
        meta = lookup_dataset("sst_2")
        assert meta is not None
        assert meta.hf_path == ("glue", "sst2")

    def test_digits_sklearn_prefix_alias(self):
        """sklearn_digits should match via alias."""
        meta = lookup_dataset("sklearn_digits")
        assert meta is not None
        assert meta.load_function == "load_digits"


class TestLookupCaseInsensitive:
    """Test case-insensitive matching."""

    def test_uppercase(self):
        """Uppercase names should match."""
        assert lookup_dataset("MNIST") is not None
        assert lookup_dataset("SST2") is not None
        assert lookup_dataset("DIGITS") is not None

    def test_mixed_case(self):
        """Mixed case should match."""
        assert lookup_dataset("MnIsT") is not None
        assert lookup_dataset("Sst2") is not None

    def test_alias_case_insensitive(self):
        """Aliases should be case-insensitive."""
        assert lookup_dataset("SST-2") is not None
        assert lookup_dataset("Glue/SST2") is not None


class TestLookupNotFound:
    """Test lookup behavior for unknown datasets."""

    def test_unknown_dataset_returns_none(self):
        """Unknown dataset should return None."""
        assert lookup_dataset("unknown_dataset") is None
        assert lookup_dataset("does_not_exist") is None
        assert lookup_dataset("cifar10") is None  # Not in Phase 2 registry yet

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        assert lookup_dataset("") is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only should return None."""
        assert lookup_dataset("   ") is None


class TestRegistryHelpers:
    """Test helper functions."""

    def test_get_all_dataset_names(self):
        """Should return all primary dataset names."""
        names = get_all_dataset_names()
        assert isinstance(names, list)
        assert len(names) == 5  # Phase 2 has 5 datasets
        assert "digits" in names
        assert "iris" in names
        assert "mnist" in names
        assert "sst2" in names
        assert "imdb" in names

    def test_get_all_dataset_names_sorted(self):
        """Names should be sorted alphabetically."""
        names = get_all_dataset_names()
        assert names == sorted(names)

    def test_get_datasets_by_source_sklearn(self):
        """Should return sklearn datasets."""
        sklearn_datasets = get_datasets_by_source(DatasetSource.SKLEARN)
        assert len(sklearn_datasets) == 2
        assert "digits" in sklearn_datasets
        assert "iris" in sklearn_datasets

    def test_get_datasets_by_source_torchvision(self):
        """Should return torchvision datasets."""
        torch_datasets = get_datasets_by_source(DatasetSource.TORCHVISION)
        assert len(torch_datasets) == 1
        assert "mnist" in torch_datasets

    def test_get_datasets_by_source_huggingface(self):
        """Should return HuggingFace datasets."""
        hf_datasets = get_datasets_by_source(DatasetSource.HUGGINGFACE)
        assert len(hf_datasets) == 2
        assert "sst2" in hf_datasets
        assert "imdb" in hf_datasets


class TestMetadataFields:
    """Test metadata field values."""

    def test_sst2_metadata_complete(self):
        """SST-2 should have all expected metadata."""
        meta = lookup_dataset("sst2")
        assert meta.source == DatasetSource.HUGGINGFACE
        assert meta.load_function == "load_dataset"
        assert meta.typical_size_mb == 67
        assert meta.supports_streaming is True
        assert meta.hf_path == ("glue", "sst2")
        assert meta.license == "other"
        assert len(meta.aliases) > 0

    def test_mnist_metadata_complete(self):
        """MNIST should have all expected metadata."""
        meta = lookup_dataset("mnist")
        assert meta.source == DatasetSource.TORCHVISION
        assert meta.load_function == "MNIST"
        assert meta.typical_size_mb == 15
        assert meta.supports_streaming is False  # Torchvision doesn't stream
        assert meta.hf_path is None  # Not a HuggingFace dataset
        assert meta.license == "CC-BY-SA-3.0"

    def test_digits_metadata_complete(self):
        """Digits should have sklearn metadata."""
        meta = lookup_dataset("digits")
        assert meta.source == DatasetSource.SKLEARN
        assert meta.typical_size_mb == 1  # Tiny
        assert meta.supports_streaming is False
        assert meta.hf_path is None


class TestAliasSymmetry:
    """Test that all aliases point back to correct dataset."""

    def test_sst2_all_aliases_match(self):
        """All SST-2 aliases should return same metadata."""
        variants = ["sst2", "sst-2", "sst_2", "glue/sst2", "SST2", "SST-2"]
        metas = [lookup_dataset(v) for v in variants]

        # All should find the same dataset
        assert all(m is not None for m in metas)
        assert all(m.hf_path == ("glue", "sst2") for m in metas)

    def test_imdb_all_aliases_match(self):
        """All IMDB aliases should return same metadata."""
        variants = ["imdb", "IMDB", "imdb_reviews"]
        metas = [lookup_dataset(v) for v in variants]

        assert all(m is not None for m in metas)
        assert all(m.hf_path == ("imdb",) for m in metas)


class TestRegistryIntegrity:
    """Test overall registry integrity."""

    def test_no_duplicate_aliases(self):
        """No alias should point to multiple datasets."""
        # Build map of normalized name -> dataset primary key
        name_to_dataset = {}

        for name, meta in DATASET_REGISTRY.items():
            # Track primary name
            normalized = normalize_dataset_name(name)
            if normalized in name_to_dataset:
                pytest.fail(f"Duplicate primary name: {normalized} in {name} and {name_to_dataset[normalized]}")
            name_to_dataset[normalized] = name

            # Track aliases - they should either be unique OR match the primary
            for alias in meta.aliases:
                if alias in name_to_dataset and name_to_dataset[alias] != name:
                    pytest.fail(f"Alias conflict: {alias} points to both {name} and {name_to_dataset[alias]}")
                name_to_dataset[alias] = name

    def test_all_hf_datasets_have_hf_path(self):
        """HuggingFace datasets must have hf_path."""
        for name, meta in DATASET_REGISTRY.items():
            if meta.source == DatasetSource.HUGGINGFACE:
                assert (
                    meta.hf_path is not None
                ), f"HF dataset {name} missing hf_path"
                assert len(meta.hf_path) > 0, f"HF dataset {name} has empty hf_path"

    def test_non_hf_datasets_no_hf_path(self):
        """Non-HuggingFace datasets should not have hf_path."""
        for name, meta in DATASET_REGISTRY.items():
            if meta.source != DatasetSource.HUGGINGFACE:
                assert meta.hf_path is None, f"Non-HF dataset {name} has hf_path"

    def test_all_sizes_positive(self):
        """All dataset sizes should be positive."""
        for name, meta in DATASET_REGISTRY.items():
            assert (
                meta.typical_size_mb > 0
            ), f"Dataset {name} has invalid size: {meta.typical_size_mb}"

    def test_streaming_only_for_hf(self):
        """Only HuggingFace datasets can support streaming."""
        for name, meta in DATASET_REGISTRY.items():
            if meta.supports_streaming:
                assert (
                    meta.source == DatasetSource.HUGGINGFACE
                ), f"Non-HF dataset {name} claims streaming support"
