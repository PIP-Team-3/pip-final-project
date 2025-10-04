"""Tests for C-OBS-01: Observability enhancements to doctor endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.doctor import config_snapshot
from app.main import app
from app.utils.redaction import redact_api_key, redact_signed_url


def test_doctor_includes_runner_posture_and_last_run_snapshot():
    """Test that doctor endpoint includes runner config and last run info."""
    health = config_snapshot()

    # Verify runner posture fields
    assert "runner" in health.__dict__
    runner = health.runner
    assert runner["cpu_only"] is True
    assert runner["seed_policy"] == "deterministic"
    assert "artifact_caps" in runner
    assert runner["artifact_caps"]["logs_mib"] == 2
    assert runner["artifact_caps"]["events_mib"] == 5

    # Verify last_run field exists (may be None on cold start)
    assert "last_run" in health.__dict__
    # last_run can be None or a dict with id, status, completed_at, env_hash
    if health.last_run:
        assert isinstance(health.last_run, dict)

    # Verify caps still present
    assert health.caps["file_search_per_run"] >= 0
    assert health.caps["web_search_per_run"] >= 0


def test_redaction_removes_signed_url_tokens():
    """Test that signed URL query parameters are redacted."""
    # Full signed URL with token
    url_with_token = "https://example.supabase.co/storage/v1/object/sign/runs/run-123/metrics.json?token=eyJhbGc.abc123.def456"

    redacted = redact_signed_url(url_with_token)

    # Should preserve path but hide query string
    assert "https://example.supabase.co/storage/v1/object/sign/runs/run-123/metrics.json" in redacted
    assert "?<redacted>" in redacted
    assert "token=" not in redacted
    assert "eyJhbGc" not in redacted


def test_redaction_handles_urls_without_query():
    """Test that URLs without query strings pass through unchanged."""
    url_no_query = "https://example.com/file.pdf"

    redacted = redact_signed_url(url_no_query)

    assert redacted == url_no_query


def test_redaction_removes_api_key_secrets():
    """Test that API keys are properly redacted."""
    # OpenAI format
    openai_key = "sk-proj-abc123def456ghi789"
    redacted = redact_api_key(openai_key)

    assert redacted.startswith("sk-proj-")
    assert redacted.endswith("***")
    assert "abc123" not in redacted

    # Generic key
    generic_key = "very_long_secret_key_12345678"
    redacted_generic = redact_api_key(generic_key)

    assert len(redacted_generic) < len(generic_key)
    assert "***" in redacted_generic


def test_doctor_endpoint_returns_observability_fields():
    """Test that /internal/config/doctor includes all observability fields."""
    client = TestClient(app)

    response = client.get("/internal/config/doctor")

    assert response.status_code == 200
    data = response.json()

    # Original fields
    assert "supabase_url_present" in data
    assert "openai_api_key_present" in data
    assert "caps" in data
    assert "responses_mode_enabled" in data
    assert "tools" in data

    # New C-OBS-01 fields
    assert "runner" in data
    assert data["runner"]["cpu_only"] is True
    assert data["runner"]["seed_policy"] == "deterministic"
    assert "artifact_caps" in data["runner"]

    assert "last_run" in data
    # last_run can be null, that's ok


def test_doctor_does_not_leak_secrets():
    """Verify that doctor response doesn't contain raw secrets."""
    client = TestClient(app)

    response = client.get("/internal/config/doctor")

    assert response.status_code == 200
    data = response.json()

    # Should have presence booleans only, not actual values
    assert isinstance(data["supabase_url_present"], bool)
    assert isinstance(data["openai_api_key_present"], bool)
    assert isinstance(data["supabase_service_role_present"], bool)

    # Check that response doesn't contain actual secret patterns
    # (but field names like "supabase_service_role_present" are OK)
    response_text = response.text

    # No actual OpenAI API keys (sk-proj- followed by random chars)
    import re

    # Pattern: sk-proj- or sk- followed by long alphanumeric
    assert not re.search(r"sk-proj-[a-zA-Z0-9]{20,}", response_text)
    assert not re.search(r"sk-[a-zA-Z0-9]{30,}", response_text)

    # No JWT tokens (eyJ... pattern with dots)
    assert not re.search(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", response_text)

    # Field names are OK, but shouldn't have actual Supabase URLs with full credentials
    # Check there's no pattern like https://...supabase.co with service_role= in query
    assert "service_role=" not in response_text
