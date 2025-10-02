from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_config_doctor_reports_presence(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-demo")

    client = TestClient(app)

    response = client.get("/internal/config/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["supabase_url_present"] is True
    assert payload["supabase_service_role_present"] is True
    assert payload["supabase_anon_present"] is True
    assert payload["openai_api_key_present"] is True
    assert payload["all_core_present"] is True
    assert payload["missing_env_keys"] == []
    assert payload["responses_mode_enabled"] is True
    assert isinstance(payload["openai_python_version"], str)
    assert payload["openai_python_version"]
    assert payload["models"]["selected"] == get_settings().openai_model
    assert payload["tools"]["file_search"] is True
    assert payload["tools"]["web_search"] is True


def test_config_doctor_missing_keys(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = TestClient(app)

    response = client.get("/internal/config/doctor")
    assert response.status_code == 200
    payload = response.json()
    assert payload["supabase_url_present"] is False
    assert payload["supabase_service_role_present"] is False
    assert payload["openai_api_key_present"] is False
    assert payload["all_core_present"] is False
    assert "SUPABASE_URL" in payload["missing_env_keys"]
    assert "SUPABASE_SERVICE_ROLE_KEY" in payload["missing_env_keys"]
    assert "OPENAI_API_KEY" in payload["missing_env_keys"]
    assert payload["responses_mode_enabled"] is True
    assert isinstance(payload["openai_python_version"], str)
    assert payload["models"]["selected"] == get_settings().openai_model
