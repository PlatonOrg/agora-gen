"""
Tests for src.api.v1.endpoints.chat pure helper functions and simple endpoints.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.api.v1.endpoints.chat import _get_session_files, _save_session_files, router
from src.api.v1.dependencies import get_settings
from src.infra.db.redis import get_redis
from src.services.models.api import SessionFile


# ---------------------------------------------------------------------------
# _get_session_files
# ---------------------------------------------------------------------------

class TestGetSessionFiles:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_key_in_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        result = await _get_session_files(redis, "sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_parsed_session_files(self):
        redis = AsyncMock()
        data = [{"file_id": "f1", "filename": "doc.pdf"}]
        redis.get = AsyncMock(return_value=json.dumps(data).encode())
        result = await _get_session_files(redis, "sess-1")
        assert len(result) == 1
        assert result[0].file_id == "f1"
        assert result[0].filename == "doc.pdf"

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_malformed_json(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=b"not-valid-json")
        result = await _get_session_files(redis, "sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_missing_key_in_item(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps([{"bad": "data"}]).encode())
        result = await _get_session_files(redis, "sess-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_files_returned(self):
        redis = AsyncMock()
        data = [
            {"file_id": "f1", "filename": "a.pdf"},
            {"file_id": "f2", "filename": "b.pdf"},
        ]
        redis.get = AsyncMock(return_value=json.dumps(data).encode())
        result = await _get_session_files(redis, "sess-1")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _save_session_files
# ---------------------------------------------------------------------------

class TestSaveSessionFiles:
    @pytest.mark.asyncio
    async def test_calls_redis_setex_with_correct_key(self):
        redis = AsyncMock()
        redis.setex = AsyncMock()
        files = [SessionFile(file_id="f1", filename="doc.pdf")]

        await _save_session_files(redis, "my-session", files, ttl=86400)

        key_used = redis.setex.call_args[0][0]
        assert "my-session" in key_used

    @pytest.mark.asyncio
    async def test_serializes_files_as_json(self):
        redis = AsyncMock()
        redis.setex = AsyncMock()
        files = [SessionFile(file_id="f1", filename="doc.pdf")]

        await _save_session_files(redis, "sess", files, ttl=86400)

        serialized = redis.setex.call_args[0][2]
        parsed = json.loads(serialized)
        assert parsed[0]["file_id"] == "f1"
        assert parsed[0]["filename"] == "doc.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(mock_redis, mock_settings=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/chat")
    app.dependency_overrides[get_redis] = lambda: mock_redis
    if mock_settings is not None:
        app.dependency_overrides[get_settings] = lambda: mock_settings
    return app


def _make_mock_settings(**overrides):
    """Return a MagicMock that behaves like Settings."""
    mock = MagicMock()
    mock.SESSION_COOKIE_NAME = overrides.get("SESSION_COOKIE_NAME", "session_id")
    mock.SESSION_TTL_SECONDS = overrides.get("SESSION_TTL_SECONDS", 86400)
    return mock


# ---------------------------------------------------------------------------
# GET /chat/file-support
# ---------------------------------------------------------------------------

class TestFileSupportEndpoint:
    def _make_registry(self, is_ragustave: bool) -> MagicMock:
        from src.infra.llm.providers import RagustaveProvider
        provider = MagicMock(spec=RagustaveProvider if is_ragustave else object)
        provider.name = "ragustave" if is_ragustave else "groq"
        registry = MagicMock()
        registry.default_provider = provider
        return registry

    def _patch_runtime_config(self, max_files: int = 3):
        """Patch runtime_config.get_int to return ``max_files`` for FILE_UPLOAD_MAX_COUNT."""
        mock_rc = MagicMock()
        mock_rc.get_int = MagicMock(return_value=max_files)
        return patch("src.services.runtime_config_service.runtime_config", mock_rc)

    @pytest.mark.asyncio
    async def test_always_supported_for_ragustave(self):
        mock_redis = AsyncMock()
        app = _make_app(mock_redis)
        registry = self._make_registry(is_ragustave=True)
        with self._patch_runtime_config():
            with patch("src.core.di.get_llm_registry", return_value=registry):
                with patch("src.infra.files.parsers.supported_extensions",
                           return_value=frozenset({".pdf", ".txt"})):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/chat/file-support")

        assert response.status_code == 200
        assert response.json()["supported"] is True

    @pytest.mark.asyncio
    async def test_ragustave_returns_empty_accepted_extensions(self):
        """Ragustave accepts all types so accepted_extensions is empty."""
        mock_redis = AsyncMock()
        app = _make_app(mock_redis)
        registry = self._make_registry(is_ragustave=True)
        with self._patch_runtime_config():
            with patch("src.core.di.get_llm_registry", return_value=registry):
                with patch("src.infra.files.parsers.supported_extensions",
                           return_value=frozenset({".pdf", ".txt"})):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/chat/file-support")

        assert response.json()["accepted_extensions"] == []

    @pytest.mark.asyncio
    async def test_always_supported_for_other_providers(self):
        """All providers are now supported=True."""
        mock_redis = AsyncMock()
        app = _make_app(mock_redis)
        registry = self._make_registry(is_ragustave=False)
        with self._patch_runtime_config():
            with patch("src.core.di.get_llm_registry", return_value=registry):
                with patch("src.infra.files.parsers.supported_extensions",
                           return_value=frozenset({".pdf", ".txt"})):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get("/chat/file-support")

        assert response.json()["supported"] is True

    @pytest.mark.asyncio
    async def test_non_ragustave_returns_empty_accepted_extensions(self):
        """Non-ragustave providers now return empty accepted_extensions.

        Extension filtering is content-based (binary probe), not allowlist-based.
        An empty list signals to the frontend that all text files are accepted.
        """
        mock_redis = AsyncMock()
        app = _make_app(mock_redis)
        registry = self._make_registry(is_ragustave=False)
        with self._patch_runtime_config():
            with patch("src.core.di.get_llm_registry", return_value=registry):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/chat/file-support")

        assert response.json()["accepted_extensions"] == []


# ---------------------------------------------------------------------------
# GET /chat/files
# ---------------------------------------------------------------------------

class TestGetSessionFilesEndpoint:
    @pytest.mark.asyncio
    async def test_no_session_cookie_returns_empty_list(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        app = _make_app(mock_redis, _make_mock_settings())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/chat/files")

        assert response.status_code == 200
        assert response.json()["files"] == []

    @pytest.mark.asyncio
    async def test_returns_files_from_session(self):
        files_data = [{"file_id": "f1", "filename": "doc.pdf"}]
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(files_data).encode())
        app = _make_app(mock_redis, _make_mock_settings())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            cookies={"session_id": "valid-sess"},
        ) as client:
            response = await client.get("/chat/files")

        assert response.status_code == 200
        assert len(response.json()["files"]) == 1

