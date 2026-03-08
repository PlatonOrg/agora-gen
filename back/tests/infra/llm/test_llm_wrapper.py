"""
Tests for src.infra.llm.llm_wrapper.

Covers:
- chat_with_llm: fixed schema path, config schema path, no schema path,
  schema wrapping delegated to provider, LLMResult construction
- chat_text_with_llm: plain string result, non-string result coerced to str
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.models.api import LLMResult


def _make_registry(provider_name: str = "groq", model: str = "llama3") -> MagicMock:
    """Build a minimal mock LLMProviderRegistry."""
    provider = MagicMock()
    provider.name = provider_name
    provider.wrap_json_schema.side_effect = lambda schema: {"wrapped": schema}
    provider.chat = AsyncMock(return_value={"answer": 42})

    registry = MagicMock()
    registry.default_provider = provider
    registry.default_model_for.return_value = model
    return registry


class TestChatWithLlm:
    @pytest.mark.asyncio
    async def test_returns_llm_result(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            result = await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.0,
            )
        assert isinstance(result, LLMResult)

    @pytest.mark.asyncio
    async def test_provider_and_model_stored_in_result(self):
        registry = _make_registry(provider_name="gemini", model="gemini-pro")
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            result = await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.5,
            )
        assert result.provider == "gemini"
        assert result.model == "gemini-pro"

    @pytest.mark.asyncio
    async def test_no_schema_passes_none_to_provider(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.0,
            )
        call_kwargs = registry.default_provider.chat.call_args[1]
        assert call_kwargs["json_schema"] is None

    @pytest.mark.asyncio
    async def test_fixed_schema_builds_and_wraps_schema(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            with patch("src.infra.llm.llm_wrapper.build_fixed_exercise_json_schema") as mock_build:
                mock_build.return_value = {"type": "object"}
                from src.infra.llm.llm_wrapper import chat_with_llm
                await chat_with_llm(
                    system_prompt="sys",
                    user_request="user",
                    temperature=0.0,
                    use_fixed_schema=True,
                )
        mock_build.assert_called_once()
        registry.default_provider.wrap_json_schema.assert_called_once()

    @pytest.mark.asyncio
    async def test_config_schema_builds_and_wraps_schema(self):
        registry = _make_registry()
        schema_config = [{"name": "q", "type": "text", "description": "d", "value": ""}]
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            with patch("src.infra.llm.llm_wrapper.build_json_schema_from_config") as mock_build:
                mock_build.return_value = {"type": "object"}
                from src.infra.llm.llm_wrapper import chat_with_llm
                await chat_with_llm(
                    system_prompt="sys",
                    user_request="user",
                    temperature=0.0,
                    schema_config=schema_config,
                )
        mock_build.assert_called_once_with(schema_config, include_properties=None)
        registry.default_provider.wrap_json_schema.assert_called_once()

    @pytest.mark.asyncio
    async def test_include_properties_forwarded_to_schema_builder(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            with patch("src.infra.llm.llm_wrapper.build_fixed_exercise_json_schema") as mock_build:
                mock_build.return_value = {"type": "object"}
                from src.infra.llm.llm_wrapper import chat_with_llm
                await chat_with_llm(
                    system_prompt="sys",
                    user_request="user",
                    temperature=0.0,
                    use_fixed_schema=True,
                    include_properties=["title", "statement"],
                )
        mock_build.assert_called_once_with(include_properties=["title", "statement"])

    @pytest.mark.asyncio
    async def test_string_result_stored_as_empty_dict(self):
        """When provider returns a raw string instead of JSON, parsed becomes {}."""
        registry = _make_registry()
        registry.default_provider.chat = AsyncMock(return_value="plain text")
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            result = await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.0,
            )
        assert result.parsed == {}

    @pytest.mark.asyncio
    async def test_dict_result_stored_in_parsed(self):
        registry = _make_registry()
        registry.default_provider.chat = AsyncMock(return_value={"key": "value"})
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            result = await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.0,
            )
        assert result.parsed == {"key": "value"}

    @pytest.mark.asyncio
    async def test_temperature_forwarded_to_provider(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_with_llm
            await chat_with_llm(
                system_prompt="sys",
                user_request="user",
                temperature=0.7,
            )
        call_kwargs = registry.default_provider.chat.call_args[1]
        assert call_kwargs["temperature"] == 0.7


class TestChatTextWithLlm:
    @pytest.mark.asyncio
    async def test_returns_plain_string(self):
        registry = _make_registry()
        registry.default_provider.chat = AsyncMock(return_value="  Hello world  ")
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_text_with_llm
            result = await chat_text_with_llm(
                system_prompt="sys",
                user_request="user",
            )
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_non_string_result_coerced_to_str(self):
        registry = _make_registry()
        registry.default_provider.chat = AsyncMock(return_value={"unexpected": "dict"})
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_text_with_llm
            result = await chat_text_with_llm(
                system_prompt="sys",
                user_request="user",
            )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_passes_none_json_schema_to_provider(self):
        registry = _make_registry()
        with patch("src.infra.llm.llm_wrapper.get_llm_registry", return_value=registry):
            from src.infra.llm.llm_wrapper import chat_text_with_llm
            await chat_text_with_llm(
                system_prompt="sys",
                user_request="user",
            )
        call_kwargs = registry.default_provider.chat.call_args[1]
        assert call_kwargs.get("json_schema") is None

