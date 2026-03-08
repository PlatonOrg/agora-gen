"""
Tests for src.infra.llm.llm.LLMProviderRegistry.

Covers:
- Provider registration and retrieval
- Default provider selection
- Error handling for unknown providers and missing defaults
- default_model_for lookup
- registered_names property
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.infra.llm.llm import LLMProviderRegistry


def _make_provider(name: str) -> MagicMock:
    """Build a minimal mock that satisfies the LLMProvider protocol."""
    provider = MagicMock()
    provider.name = name
    return provider


class TestLLMProviderRegistryRegistration:
    def test_register_single_provider(self):
        registry = LLMProviderRegistry()
        provider = _make_provider("groq")
        registry.register(provider, default_model="llama3", is_default=True)

        assert "groq" in registry.registered_names

    def test_register_multiple_providers(self):
        registry = LLMProviderRegistry()
        for name in ("groq", "gemini", "ollama"):
            registry.register(_make_provider(name), default_model=f"{name}-model")

        assert set(registry.registered_names) == {"groq", "gemini", "ollama"}

    def test_default_provider_is_set_by_flag(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1", is_default=False)
        registry.register(_make_provider("gemini"), default_model="m2", is_default=True)

        assert registry.default_provider.name == "gemini"

    def test_last_is_default_wins(self):
        """When multiple providers are marked default, the last one wins."""
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1", is_default=True)
        registry.register(_make_provider("gemini"), default_model="m2", is_default=True)

        assert registry.default_provider.name == "gemini"

    def test_overwrite_existing_provider(self):
        """Re-registering a provider under the same name replaces it."""
        registry = LLMProviderRegistry()
        p1 = _make_provider("groq")
        p2 = _make_provider("groq")
        registry.register(p1, default_model="m1", is_default=True)
        registry.register(p2, default_model="m2", is_default=True)

        assert registry.get("groq") is p2


class TestLLMProviderRegistryLookup:
    def test_get_existing_provider(self):
        registry = LLMProviderRegistry()
        provider = _make_provider("groq")
        registry.register(provider, default_model="m1")

        assert registry.get("groq") is provider

    def test_get_unknown_provider_raises_value_error(self):
        registry = LLMProviderRegistry()
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            registry.get("nonexistent")

    def test_error_message_lists_available_providers(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1")
        with pytest.raises(ValueError, match="groq"):
            registry.get("missing")

    def test_get_when_empty_lists_none(self):
        registry = LLMProviderRegistry()
        with pytest.raises(ValueError, match="none"):
            registry.get("x")


class TestLLMProviderRegistryDefaultProvider:
    def test_no_default_raises_runtime_error(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1", is_default=False)

        with pytest.raises(RuntimeError, match="No default LLM provider"):
            _ = registry.default_provider

    def test_default_provider_name_raises_when_not_set(self):
        registry = LLMProviderRegistry()
        with pytest.raises(RuntimeError):
            _ = registry.default_provider_name

    def test_default_provider_name_returns_string(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("ollama"), default_model="llama3", is_default=True)

        assert registry.default_provider_name == "ollama"


class TestLLMProviderRegistryDefaultModel:
    def test_default_model_for_known_provider(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="llama3-70b", is_default=True)

        assert registry.default_model_for("groq") == "llama3-70b"

    def test_default_model_for_unknown_raises_value_error(self):
        registry = LLMProviderRegistry()
        with pytest.raises(ValueError, match="No default model"):
            registry.default_model_for("unknown")


class TestLLMProviderRegistryRegisteredNames:
    def test_empty_registry(self):
        registry = LLMProviderRegistry()
        assert registry.registered_names == []

    def test_names_after_registration(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("a"), default_model="m")
        registry.register(_make_provider("b"), default_model="m")

        assert sorted(registry.registered_names) == ["a", "b"]


class TestLLMProviderRegistryMultiModel:
    def test_register_with_models_list(self):
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="model-a",
            models=["model-a", "model-b", "model-c"],
            is_default=True,
        )
        options = registry.available_options()
        assert len(options) == 3
        assert options[0] == {"provider": "groq", "model": "model-a"}
        assert options[1] == {"provider": "groq", "model": "model-b"}
        assert options[2] == {"provider": "groq", "model": "model-c"}

    def test_default_model_auto_added_to_models(self):
        """If default_model is not in the models list, it is prepended."""
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="model-x",
            models=["model-a", "model-b"],
            is_default=True,
        )
        options = registry.available_options()
        models = [o["model"] for o in options]
        assert "model-x" in models
        assert models[0] == "model-x"

    def test_no_models_list_falls_back_to_default_model(self):
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="only-model",
            is_default=True,
        )
        options = registry.available_options()
        assert len(options) == 1
        assert options[0] == {"provider": "groq", "model": "only-model"}

    def test_available_options_multiple_providers(self):
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="groq-a",
            models=["groq-a", "groq-b"],
            is_default=True,
        )
        registry.register(
            _make_provider("ragustave"),
            default_model="rag-a",
            models=["rag-a"],
        )
        options = registry.available_options()
        assert len(options) == 3
        providers = [o["provider"] for o in options]
        assert providers.count("groq") == 2
        assert providers.count("ragustave") == 1


class TestLLMProviderRegistrySetDefault:
    def test_set_default_switches_provider(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1", is_default=True)
        registry.register(_make_provider("gemini"), default_model="m2")

        registry.set_default("gemini")
        assert registry.default_provider_name == "gemini"

    def test_set_default_with_valid_model(self):
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="model-a",
            models=["model-a", "model-b"],
            is_default=True,
        )
        registry.set_default("groq", "model-b")
        assert registry.default_model_for("groq") == "model-b"

    def test_set_default_with_invalid_model_raises(self):
        registry = LLMProviderRegistry()
        registry.register(
            _make_provider("groq"),
            default_model="model-a",
            models=["model-a", "model-b"],
            is_default=True,
        )
        with pytest.raises(ValueError, match="not available"):
            registry.set_default("groq", "nonexistent-model")

    def test_set_default_unknown_provider_raises(self):
        registry = LLMProviderRegistry()
        registry.register(_make_provider("groq"), default_model="m1", is_default=True)

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            registry.set_default("nonexistent")


