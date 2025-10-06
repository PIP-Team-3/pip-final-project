"""Test Pydantic schemas for Responses API compatibility."""
import pytest
from pydantic import ValidationError

from api.app.agents.schemas import (
    CitationModel,
    ExtractedClaimModel,
    ExtractorOutputModel,
)


def test_extractor_output_model_validates():
    """Test ExtractorOutputModel accepts valid JSON with nested citation."""
    valid_json = {
        "claims": [
            {
                "dataset_name": "CIFAR-10",
                "split": "test",
                "metric_name": "accuracy",
                "metric_value": 95.5,
                "units": "percent",
                "method_snippet": "ResNet-18 with data augmentation",
                "citation": {
                    "source_citation": "Table 1, p.3",
                    "confidence": 0.95
                }
            }
        ]
    }
    model = ExtractorOutputModel.model_validate(valid_json)
    assert len(model.claims) == 1
    assert model.claims[0].metric_value == 95.5
    assert model.claims[0].citation.source_citation == "Table 1, p.3"


def test_extractor_output_model_empty_claims():
    """Test empty claims list is valid."""
    model = ExtractorOutputModel.model_validate({"claims": []})
    assert len(model.claims) == 0


def test_extractor_output_model_rejects_extra_fields():
    """Test that extra='forbid' works."""
    invalid_json = {
        "claims": [],
        "extra_field": "should fail"
    }
    with pytest.raises(ValidationError) as exc_info:
        ExtractorOutputModel.model_validate(invalid_json)
    assert "extra_field" in str(exc_info.value)


def test_confidence_range_validation():
    """Test confidence must be 0.0-1.0."""
    # Too high
    invalid_json = {
        "claims": [{
            "dataset_name": "test",
            "citation": {"source_citation": "Table 1", "confidence": 1.5}
        }]
    }
    with pytest.raises(ValidationError) as exc_info:
        ExtractorOutputModel.model_validate(invalid_json)
    assert "confidence" in str(exc_info.value)

    # Negative
    invalid_json["claims"][0]["citation"]["confidence"] = -0.1
    with pytest.raises(ValidationError):
        ExtractorOutputModel.model_validate(invalid_json)


def test_nested_citation_structure():
    """Test that citation must be nested, not flat."""
    flat_json = {
        "claims": [{
            "dataset_name": "CIFAR-10",
            "source_citation": "Table 1",  # WRONG: flat instead of nested
            "confidence": 0.9
        }]
    }
    with pytest.raises(ValidationError) as exc_info:
        ExtractorOutputModel.model_validate(flat_json)
    assert "citation" in str(exc_info.value)
