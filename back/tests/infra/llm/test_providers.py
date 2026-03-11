"""
Tests for src.infra.llm.providers.

Covers:
- OpenAICompatibleProvider.wrap_json_schema
- RagustaveProvider.wrap_json_schema
- GeminiProvider.wrap_json_schema
- OllamaProvider.wrap_json_schema
- Provider name properties
- HTTP interaction via httpx mock (chat, upload_file, delete_file)
- JSON markdown fence stripping
- Retry-on-429 logic for OpenAICompatibleProvider
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from pathlib import Path

import httpx
import respx

from src.infra.llm.providers import (
    GeminiProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    RagustaveProvider,
)
from src.infra.llm.llm import LLMChatResult


# ---------------------------------------------------------------------------
# wrap_json_schema
# ---------------------------------------------------------------------------

class TestWrapJsonSchema:
    def test_openai_compatible_wraps_correctly(self):
        provider = OpenAICompatibleProvider(
            provider_name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="key",
        )
        schema = {"type": "object", "properties": {}}
        result = provider.wrap_json_schema(schema)
        assert result["type"] == "json_schema"
        assert result["json_schema"]["name"] == "exercise_output"
        assert result["json_schema"]["schema"] is schema

    def test_openai_compatible_custom_schema_name(self):
        provider = OpenAICompatibleProvider(
            provider_name="groq", base_url="x", api_key="k"
        )
        result = provider.wrap_json_schema({"type": "object"}, schema_name="custom_name")
        assert result["json_schema"]["name"] == "custom_name"

    def test_ragustave_wraps_correctly(self):
        provider = RagustaveProvider(base_url="https://rag.example", api_key="key")
        schema = {"type": "object"}
        result = provider.wrap_json_schema(schema)
        assert result["type"] == "json_schema"
        assert result["json_schema"]["schema"] is schema

    def test_gemini_returns_schema_directly(self):
        provider = GeminiProvider(api_key="key")
        schema = {"type": "object", "properties": {}}
        result = provider.wrap_json_schema(schema)
        assert result is schema

    def test_ollama_wraps_in_name_schema_envelope(self):
        provider = OllamaProvider(base_url="http://localhost:11434")
        schema = {"type": "object"}
        result = provider.wrap_json_schema(schema)
        assert result["name"] == "exercise_output"
        assert result["schema"] is schema


# ---------------------------------------------------------------------------
# Provider name properties
# ---------------------------------------------------------------------------

class TestProviderNames:
    def test_openai_compatible_name(self):
        p = OpenAICompatibleProvider(provider_name="my-provider", base_url="x", api_key="k")
        assert p.name == "my-provider"

    def test_ragustave_name(self):
        p = RagustaveProvider(base_url="x", api_key="k")
        assert p.name == "ragustave"

    def test_gemini_name(self):
        p = GeminiProvider(api_key="k")
        assert p.name == "gemini"

    def test_ollama_name(self):
        p = OllamaProvider(base_url="http://localhost")
        assert p.name == "ollama"


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider.chat
# ---------------------------------------------------------------------------

class TestOpenAICompatibleChat:
    def _make_provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            provider_name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key="test-key",
        )

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_parsed_json_when_schema_provided(self):
        provider = self._make_provider()
        payload = {"choices": [{"message": {"content": '{"key": "value"}'}}]}
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        schema = provider.wrap_json_schema({"type": "object"})

        result = await provider.chat(
            model="llama3",
            system_prompt="sys",
            user_prompt="user",
            json_schema=schema,
            temperature=0.0,
        )

        assert isinstance(result, LLMChatResult)
        assert result.content == {"key": "value"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_plain_string_when_no_schema(self):
        provider = self._make_provider()
        payload = {"choices": [{"message": {"content": "Hello world"}}]}
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )

        result = await provider.chat(
            model="llama3",
            system_prompt="sys",
            user_prompt="user",
            temperature=0.0,
        )

        assert isinstance(result, LLMChatResult)
        assert result.content == "Hello world"

    @pytest.mark.asyncio
    @respx.mock
    async def test_strips_markdown_json_fence(self):
        provider = self._make_provider()
        raw = '```json\n{"answer": 42}\n```'
        payload = {"choices": [{"message": {"content": raw}}]}
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        schema = provider.wrap_json_schema({"type": "object"})

        result = await provider.chat(
            model="llama3", system_prompt="s", user_prompt="u",
            json_schema=schema, temperature=0.0,
        )

        assert result.content == {"answer": 42}

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_raw_string_on_json_decode_error(self):
        provider = self._make_provider()
        payload = {"choices": [{"message": {"content": "not-json"}}]}
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        schema = provider.wrap_json_schema({"type": "object"})

        result = await provider.chat(
            model="llama3", system_prompt="s", user_prompt="u",
            json_schema=schema, temperature=0.0,
        )

        assert result.content == "not-json"

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_unexpected_response_structure(self):
        provider = self._make_provider()
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"wrong": "structure"})
        )

        with pytest.raises(ValueError, match="Unexpected response structure"):
            await provider.chat(
                model="llama3", system_prompt="s", user_prompt="u", temperature=0.0
            )

    @pytest.mark.asyncio
    @respx.mock
    async def test_file_ids_warning_logged_and_ignored(self, caplog):
        import logging
        provider = self._make_provider()
        payload = {"choices": [{"message": {"content": "ok"}}]}
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )

        with caplog.at_level(logging.WARNING):
            await provider.chat(
                model="llama3", system_prompt="s", user_prompt="u",
                temperature=0.0, file_ids=["f1"],
            )

        assert any("not supported" in r.message.lower() or "ignoring" in r.message.lower()
                   for r in caplog.records)

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_429(self):
        provider = self._make_provider()
        success_payload = {"choices": [{"message": {"content": "ok"}}]}

        call_count = 0

        def _handler(request):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return httpx.Response(429, headers={"retry-after": "0"}, json={})
            return httpx.Response(200, json=success_payload)

        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(side_effect=_handler)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.chat(
                model="llama3", system_prompt="s", user_prompt="u", temperature=0.0
            )

        assert result.content == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_after_max_retries_on_persistent_500(self):
        provider = self._make_provider()
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.HTTPStatusError):
                await provider.chat(
                    model="llama3", system_prompt="s", user_prompt="u", temperature=0.0
                )


# ---------------------------------------------------------------------------
# GeminiProvider.chat
# ---------------------------------------------------------------------------

class TestGeminiProviderChat:
    def _make_provider(self) -> GeminiProvider:
        return GeminiProvider(api_key="gemini-key")

    @pytest.mark.asyncio
    @respx.mock
    async def test_strips_provider_prefix_from_model(self):
        provider = self._make_provider()
        payload = {
            "candidates": [{"content": {"parts": [{"text": '{"key": "v"}'}]}}]
        }
        respx.post(
            url__regex=r"https://generativelanguage\.googleapis\.com/.*gemini-flash.*"
        ).mock(return_value=httpx.Response(200, json=payload))

        schema = provider.wrap_json_schema({"type": "object"})
        result = await provider.chat(
            model="gemini/gemini-flash",
            system_prompt="s",
            user_prompt="u",
            json_schema=schema,
            temperature=0.0,
        )
        assert result.content == {"key": "v"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_plain_string_without_schema(self):
        provider = self._make_provider()
        payload = {
            "candidates": [{"content": {"parts": [{"text": "plain response"}]}}]
        }
        respx.post(url__regex=r".*generateContent.*").mock(
            return_value=httpx.Response(200, json=payload)
        )

        result = await provider.chat(
            model="gemini-pro", system_prompt="s", user_prompt="u", temperature=0.0
        )
        assert result.content == "plain response"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_raw_string_on_bad_json(self):
        provider = self._make_provider()
        payload = {
            "candidates": [{"content": {"parts": [{"text": "not-json"}]}}]
        }
        respx.post(url__regex=r".*generateContent.*").mock(
            return_value=httpx.Response(200, json=payload)
        )

        schema = provider.wrap_json_schema({"type": "object"})
        result = await provider.chat(
            model="gemini-pro", system_prompt="s", user_prompt="u",
            json_schema=schema, temperature=0.0,
        )
        assert isinstance(result, LLMChatResult)
        assert result.content == "not-json"

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_missing_candidates(self):
        provider = self._make_provider()
        respx.post(url__regex=r".*generateContent.*").mock(
            return_value=httpx.Response(200, json={"error": "no candidates"})
        )

        with pytest.raises(ValueError, match="unexpected response structure"):
            await provider.chat(
                model="gemini-pro", system_prompt="s", user_prompt="u", temperature=0.0
            )


# ---------------------------------------------------------------------------
# OllamaProvider.chat
# ---------------------------------------------------------------------------

class TestOllamaProviderChat:
    def _make_provider(self) -> OllamaProvider:
        return OllamaProvider(base_url="http://localhost:11434")

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_parsed_json_with_schema(self):
        provider = self._make_provider()
        payload = {"message": {"content": '{"result": true}'}}
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=payload)
        )
        schema = provider.wrap_json_schema({"type": "object"})

        result = await provider.chat(
            model="llama3", system_prompt="s", user_prompt="u",
            json_schema=schema, temperature=0.0,
        )
        assert isinstance(result, LLMChatResult)
        assert result.content == {"result": True}

    @pytest.mark.asyncio
    @respx.mock
    async def test_strips_provider_prefix(self):
        provider = self._make_provider()
        payload = {"message": {"content": "response"}}
        route = respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=payload)
        )

        await provider.chat(
            model="ollama/llama3.1", system_prompt="s", user_prompt="u", temperature=0.0
        )
        # Verify the request body used the stripped model name
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["model"] == "llama3.1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_raw_string_on_invalid_json(self):
        provider = self._make_provider()
        payload = {"message": {"content": "bad-json"}}
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json=payload)
        )
        schema = provider.wrap_json_schema({"type": "object"})

        result = await provider.chat(
            model="llama3", system_prompt="s", user_prompt="u",
            json_schema=schema, temperature=0.0,
        )
        assert isinstance(result, LLMChatResult)
        assert result.content == "bad-json"


# ---------------------------------------------------------------------------
# RagustaveProvider.upload_file / delete_file
# ---------------------------------------------------------------------------

class TestRagustaveFileOperations:
    def _make_provider(self) -> RagustaveProvider:
        return RagustaveProvider(base_url="https://rag.example", api_key="key")

    @pytest.mark.asyncio
    @respx.mock
    async def test_upload_file_returns_file_id(self, tmp_path):
        provider = self._make_provider()
        tmp_file = tmp_path / "doc.pdf"
        tmp_file.write_bytes(b"pdf content")

        respx.post("https://rag.example/v1/files/").mock(
            return_value=httpx.Response(200, json={"id": "file-abc"})
        )
        with patch("src.infra.llm.providers.log_file_uploaded"):
            file_id = await provider.upload_file(tmp_file, "doc.pdf")

        assert file_id == "file-abc"

    @pytest.mark.asyncio
    async def test_upload_file_raises_when_file_missing(self):
        provider = self._make_provider()
        with pytest.raises(FileNotFoundError):
            await provider.upload_file(Path("/nonexistent/file.pdf"), "file.pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_upload_file_raises_on_missing_id_in_response(self, tmp_path):
        provider = self._make_provider()
        tmp_file = tmp_path / "doc.pdf"
        tmp_file.write_bytes(b"data")

        respx.post("https://rag.example/v1/files/").mock(
            return_value=httpx.Response(200, json={"status": "ok"})  # no "id"
        )

        with pytest.raises(ValueError, match="missing 'id'"):
            await provider.upload_file(tmp_file, "doc.pdf")

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_file_calls_correct_endpoint(self):
        provider = self._make_provider()
        route = respx.delete("https://rag.example/v1/files/file-abc").mock(
            return_value=httpx.Response(200, json={})
        )
        with patch("src.infra.llm.providers.log_file_deleted"):
            await provider.delete_file("file-abc", "doc.pdf")

        assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_file_raises_on_http_error(self):
        provider = self._make_provider()
        respx.delete("https://rag.example/v1/files/bad-id").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await provider.delete_file("bad-id")

