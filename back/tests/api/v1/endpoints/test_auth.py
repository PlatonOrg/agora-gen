"""
Tests for src.api.v1.endpoints.auth HTTP routes.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.api.v1.endpoints.auth import router
from src.api.v1.dependencies import get_settings
from src.infra.db.redis import get_redis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_settings(**overrides):
    """Return a MagicMock that behaves like Settings."""
    mock = MagicMock()
    mock.SESSION_COOKIE_NAME = overrides.get("SESSION_COOKIE_NAME", "session_id")
    mock.SESSION_TTL_SECONDS = overrides.get("SESSION_TTL_SECONDS", 86400)
    mock.SESSION_COOKIE_SAMESITE = overrides.get("SESSION_COOKIE_SAMESITE", "lax")
    mock.SESSION_COOKIE_SECURE = overrides.get("SESSION_COOKIE_SECURE", False)
    mock.PLATON_LOGIN_BASE_URL = overrides.get("PLATON_LOGIN_BASE_URL", "https://platon.example/login")
    mock.PLATON_CALLBACK_URL = overrides.get("PLATON_CALLBACK_URL", "https://app.example/callback")
    mock.PLATON_CALLBACK_TITLE = overrides.get("PLATON_CALLBACK_TITLE", "Agora")
    mock.PLATON_PUBLIC_KEY = overrides.get("PLATON_PUBLIC_KEY", "key")
    return mock


def _make_app(mock_redis, mock_settings=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_redis] = lambda: mock_redis
    if mock_settings is not None:
        app.dependency_overrides[get_settings] = lambda: mock_settings
    return app


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# POST /auth/platon/init
# ---------------------------------------------------------------------------

class TestPlatonInit:
    @pytest.mark.asyncio
    async def test_returns_redirect_url_and_state(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.generate_oauth_state = AsyncMock(return_value="state-abc")

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/auth/platon/init")

        assert response.status_code == 200
        data = response.json()
        assert "redirectUrl" in data
        assert data["state"] == "state-abc"


# ---------------------------------------------------------------------------
# POST /auth/platon/callback
# ---------------------------------------------------------------------------

class TestPlatonCallback:
    def _payload(self, **overrides) -> dict:
        base = {
            "state": "valid-state",
            "platonAccessToken": "header.eyJ1c2VybmFtZSI6InRlYWNoZXIxIn0.sig",
            "platonRefreshToken": "refresh-tok",
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_invalid_state_returns_400(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.validate_oauth_state = AsyncMock(return_value=False)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/auth/platon/callback", json=self._payload())
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.validate_oauth_state = AsyncMock(return_value=True)
            mock_auth.decode_jwt_payload_secure = MagicMock(return_value=None)
            mock_auth.decode_jwt_payload_unsafe = MagicMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/auth/platon/callback", json=self._payload())
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_success_sets_cookie_and_returns_user(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.validate_oauth_state = AsyncMock(return_value=True)
            mock_auth.decode_jwt_payload_secure = MagicMock(
                return_value={"sub": "u1", "username": "teacher.dupont"}
            )
            mock_auth.determine_role = MagicMock(return_value="TEACHER")
            mock_auth.create_session = AsyncMock(return_value="sess-xyz")

            # Patch platon_service import inside the callback to avoid network call
            with patch("src.api.v1.endpoints.auth.platon_service", create=True) as mock_platon:
                mock_platon.get_user_profile = AsyncMock(side_effect=Exception("skip"))

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post("/auth/platon/callback", json=self._payload())

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["username"] == "teacher.dupont"
        assert "session_id" in response.cookies


# ---------------------------------------------------------------------------
# GET /auth/user
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_cookie_returns_401(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/auth/user")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_session_returns_401(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.get_session_user = AsyncMock(return_value=None)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={"session_id": "expired"},
            ) as client:
                response = await client.get("/auth/user")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_session_returns_user_profile(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        session_data = {
            "id": "u1", "username": "teacher.dupont",
            "email": "teacher@example.com", "role": "TEACHER",
        }
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.get_session_user = AsyncMock(return_value=session_data)
            mock_auth.get_permissions = MagicMock(return_value=["CREATE_EX"])
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={"session_id": "valid-sess"},
            ) as client:
                response = await client.get("/auth/user")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "teacher.dupont"
        assert data["role"] == "TEACHER"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_session_and_cookie(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.logout_session = AsyncMock()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                cookies={"session_id": "sess-abc"},
            ) as client:
                response = await client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_auth.logout_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logout_without_cookie_still_succeeds(self):
        mock_redis = _make_redis()
        mock_settings = _make_mock_settings()
        app = _make_app(mock_redis, mock_settings)
        with patch("src.api.v1.endpoints.auth.auth_service") as mock_auth:
            mock_auth.logout_session = AsyncMock()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/auth/logout")

        assert response.status_code == 200
        mock_auth.logout_session.assert_not_awaited()

