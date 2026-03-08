"""
Tests for src.core.di -- LLM provider registry builder functions.

Covers:
- _build_providers_from_config: known kinds, unknown kind skipped, default via flag
- _load_providers_config: file-based loading with env var fallback
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch
from pathlib import Path

from src.infra.llm.llm import LLMProviderRegistry
from src.core.di import _build_providers_from_config, _load_providers_config, _expand_env_vars


# ---------------------------------------------------------------------------
# _build_providers_from_config
# ---------------------------------------------------------------------------

class TestBuildProvidersFromConfig:
    def _groq_entry(self, **overrides) -> dict:
        base = {
            "name": "groq",
            "kind": "openai_compatible",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "groq-key",
            "default_model": "llama3-70b",
        }
        base.update(overrides)
        return base

    def test_registers_openai_compatible_provider(self):
        entries = [self._groq_entry(default=True)]
        registry = _build_providers_from_config(entries)
        assert "groq" in registry.registered_names

    def test_registers_gemini_provider(self):
        entries = [{
            "name": "gemini",
            "kind": "gemini",
            "api_key": "gemini-key",
            "default_model": "gemini-2.5-flash",
            "default": True,
        }]
        registry = _build_providers_from_config(entries)
        assert "gemini" in registry.registered_names

    def test_registers_ollama_provider(self):
        entries = [{
            "name": "ollama",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
            "default_model": "llama3.1",
            "default": True,
        }]
        registry = _build_providers_from_config(entries)
        assert "ollama" in registry.registered_names

    def test_registers_ragustave_provider(self):
        entries = [{
            "name": "ragustave",
            "kind": "ragustave",
            "base_url": "https://rag.example",
            "api_key": "rag-key",
            "default_model": "model",
            "default": True,
        }]
        registry = _build_providers_from_config(entries)
        assert "ragustave" in registry.registered_names

    def test_unknown_kind_is_skipped(self):
        entries = [{
            "name": "mystery",
            "kind": "unknown_vendor",
            "base_url": "https://x.com",
            "api_key": "k",
            "default_model": "m",
        }]
        registry = _build_providers_from_config(entries)
        assert "mystery" not in registry.registered_names

    def test_default_provider_set_by_flag(self):
        entries = [
            self._groq_entry(name="groq"),
            {
                "name": "gemini", "kind": "gemini",
                "api_key": "k", "default_model": "m",
                "default": True,
            },
        ]
        registry = _build_providers_from_config(entries)
        assert registry.default_provider_name == "gemini"

    def test_multiple_providers_all_registered(self):
        entries = [
            self._groq_entry(default=True),
            {"name": "gemini", "kind": "gemini", "api_key": "k", "default_model": "m"},
            {"name": "ollama", "kind": "ollama", "base_url": "http://localhost:11434", "default_model": "m"},
        ]
        registry = _build_providers_from_config(entries)
        assert set(registry.registered_names) == {"groq", "gemini", "ollama"}

    def test_empty_entries_returns_registry_with_no_providers(self):
        registry = _build_providers_from_config([])
        assert registry.registered_names == []

    def test_returns_registry_instance(self):
        entries = [self._groq_entry(default=True)]
        registry = _build_providers_from_config(entries)
        assert isinstance(registry, LLMProviderRegistry)

    def test_entry_without_default_flag_is_not_default(self):
        entries = [
            self._groq_entry(),
            {
                "name": "gemini", "kind": "gemini",
                "api_key": "k", "default_model": "m",
                "default": True,
            },
        ]
        registry = _build_providers_from_config(entries)
        assert registry.default_provider_name == "gemini"


# ---------------------------------------------------------------------------
# _load_providers_config
# ---------------------------------------------------------------------------

class TestLoadProvidersConfig:
    def test_loads_from_file_when_present(self, tmp_path: Path):
        config = [{"name": "groq", "kind": "openai_compatible",
                    "base_url": "u", "api_key": "k", "default_model": "m", "default": True}]
        config_file = tmp_path / "providers.json"
        config_file.write_text(json.dumps(config))

        with patch("src.core.di.settings") as mock_settings:
            mock_settings.LLM_PROVIDERS_FILE = str(config_file)
            mock_settings.LLM_PROVIDERS = None
            result = _load_providers_config()

        assert len(result) == 1
        assert result[0]["name"] == "groq"

    def test_falls_back_to_env_var_when_file_missing(self, tmp_path: Path):
        env_entries = [{"name": "gemini", "kind": "gemini",
                        "api_key": "k", "default_model": "m", "default": True}]

        with patch("src.core.di.settings") as mock_settings:
            mock_settings.LLM_PROVIDERS_FILE = str(tmp_path / "nonexistent.json")
            mock_settings.LLM_PROVIDERS = env_entries
            result = _load_providers_config()

        assert len(result) == 1
        assert result[0]["name"] == "gemini"

    def test_raises_when_no_config_available(self, tmp_path: Path):
        with patch("src.core.di.settings") as mock_settings:
            mock_settings.LLM_PROVIDERS_FILE = str(tmp_path / "nonexistent.json")
            mock_settings.LLM_PROVIDERS = None
            with pytest.raises(RuntimeError, match="No LLM provider configuration found"):
                _load_providers_config()

    def test_expands_env_vars_in_json_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "secret-key-123")
        config = [{"name": "groq", "kind": "openai_compatible",
                    "base_url": "u", "api_key": "${TEST_API_KEY}",
                    "default_model": "m", "default": True}]
        config_file = tmp_path / "providers.json"
        config_file.write_text(json.dumps(config))

        with patch("src.core.di.settings") as mock_settings:
            mock_settings.LLM_PROVIDERS_FILE = str(config_file)
            mock_settings.LLM_PROVIDERS = None
            result = _load_providers_config()

        assert result[0]["api_key"] == "secret-key-123"


# ---------------------------------------------------------------------------
# _expand_env_vars
# ---------------------------------------------------------------------------

class TestExpandEnvVars:
    def test_replaces_single_var(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "abc123")
        assert _expand_env_vars("key=${MY_KEY}") == "key=abc123"

    def test_replaces_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "alpha")
        monkeypatch.setenv("B", "beta")
        assert _expand_env_vars("${A}-${B}") == "alpha-beta"

    def test_raises_on_missing_var(self):
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345"):
            _expand_env_vars("${NONEXISTENT_VAR_12345}")

    def test_no_placeholders_returns_unchanged(self):
        text = '{"key": "plain_value"}'
        assert _expand_env_vars(text) == text

