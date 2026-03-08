"""
Tests for src.core.config_app.Settings.

Covers:
- Default values
- Computed properties (DATABASE_URL, REDIS_URL, cors_origin_list)
- LLM_PROVIDERS JSON parsing validator
- CORS origin list parsing
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config_app import Settings


class TestSettingsDefaults:
    def test_project_name_default(self):
        s = Settings()
        assert s.PROJECT_NAME == "Agora AI Agent"

    def test_api_v1_str(self):
        s = Settings()
        assert s.API_V1_STR == "/api/v1"

    def test_debug_false_by_default(self):
        s = Settings()
        assert s.DEBUG is False

    def test_sandbox_retry_defaults(self):
        s = Settings()
        assert s.SANDBOX_RETRY_MAX_ATTEMPTS == 3
        assert s.SANDBOX_RETRY_TIMEOUT_SECONDS == 120.0

    def test_template_score_threshold(self):
        s = Settings()
        assert s.TEMPLATE_SCORE_THRESHOLD == 0.9

    def test_temp_generation(self):
        s = Settings()
        assert s.TEMP_GENERATION == 0.0

    def test_platon_docs_embed_model_default(self):
        from src.core import path_constants
        assert path_constants.PLATON_DOCS_EMBED_MODEL.name == "multilingual-e5-large-instruct"

    def test_platon_timeout(self):
        s = Settings()
        assert s.PLATON_TIMEOUT_SECONDS == 30.0

    def test_session_ttl(self):
        s = Settings()
        assert s.SESSION_TTL_SECONDS == 86400

    def test_log_level_default(self):
        s = Settings()
        assert s.LOG_LEVEL == "INFO"


class TestComputedProperties:
    def test_database_url_with_credentials(self):
        s = Settings(
            POSTGRES_USER="user",
            POSTGRES_PASSWORD="pass",
            POSTGRES_HOST="localhost",
            POSTGRES_PORT=5432,
            POSTGRES_DB="mydb",
        )
        assert s.DATABASE_URL == "postgresql://user:pass@localhost:5432/mydb"

    def test_redis_url(self):
        s = Settings(REDIS_HOST="myredis", REDIS_PORT=6380)
        assert s.REDIS_URL == "redis://myredis:6380/0"

    def test_redis_url_default(self):
        s = Settings()
        assert s.REDIS_URL == "redis://redis:6379/0"

    def test_cors_origin_list_default(self):
        s = Settings()
        origins = s.cors_origin_list
        assert "http://localhost:4200" in origins
        assert "http://localhost:80" in origins

    def test_cors_origin_list_custom(self):
        s = Settings(CORS_ORIGINS="https://a.com,https://b.com")
        origins = s.cors_origin_list
        assert origins == ["https://a.com", "https://b.com"]

    def test_cors_origin_list_strips_spaces(self):
        s = Settings(CORS_ORIGINS="https://a.com , https://b.com")
        origins = s.cors_origin_list
        assert "https://a.com" in origins
        assert "https://b.com" in origins

    def test_cors_origin_list_ignores_empty_entries(self):
        s = Settings(CORS_ORIGINS="https://a.com,,https://b.com")
        origins = s.cors_origin_list
        assert len(origins) == 2


class TestLLMProvidersJsonValidator:
    def test_valid_json_string_is_parsed(self):
        json_str = '[{"name":"groq","kind":"openai_compatible","base_url":"https://api.groq.com/openai/v1","api_key":"key","default_model":"llama3"}]'
        s = Settings(LLM_PROVIDERS=json_str)  # type: ignore[arg-type]
        assert isinstance(s.LLM_PROVIDERS, list)
        assert s.LLM_PROVIDERS[0]["name"] == "groq"

    def test_invalid_json_string_returns_none(self):
        s = Settings(LLM_PROVIDERS="not-valid-json")  # type: ignore[arg-type]
        assert s.LLM_PROVIDERS is None

    def test_none_stays_none(self):
        s = Settings(LLM_PROVIDERS=None)
        assert s.LLM_PROVIDERS is None

    def test_list_passthrough(self):
        providers = [{"name": "groq", "kind": "openai_compatible", "base_url": "x", "api_key": "k", "default_model": "m"}]
        s = Settings(LLM_PROVIDERS=providers)
        assert s.LLM_PROVIDERS == providers

