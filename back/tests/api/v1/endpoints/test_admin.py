"""
Tests for src.api.v1.endpoints.admin HTTP routes.

Covers:
- No auth cookie → 401
- Invalid/expired session → 401
- TEACHER role → 403
- ADMIN role → 200 with valid AdminStatsResponse JSON
- Custom date_from/date_to query params accepted
- Invalid date format → 400
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.api.v1.endpoints.admin import router
from src.api.v1.dependencies import get_settings
from src.infra.db.redis import get_redis
from src.core.sqlalchemy import get_db_session
from src.services.models.admin_stats import AdminStatsResponse, DailyMetrics, SummaryMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis(session_data: dict | None = None) -> AsyncMock:
    """Return a minimal async Redis mock.

    If *session_data* is provided, ``redis.get()`` returns it as JSON bytes
    (simulating a valid session lookup).  Otherwise returns ``None``.
    """
    redis = AsyncMock()
    if session_data is not None:
        redis.get = AsyncMock(return_value=json.dumps(session_data).encode())
    else:
        redis.get = AsyncMock(return_value=None)
    return redis


def _make_db_session() -> AsyncMock:
    """Return a minimal async DB session mock."""
    return AsyncMock()


def _make_stats_response(**overrides) -> AdminStatsResponse:
    """Build a minimal AdminStatsResponse for mocking service return."""
    defaults = dict(
        summary=SummaryMetrics(
            total_conversations=10,
            total_published_exercises=5,
            clean_generations=3,
            recovered_generations=2,
            fatal_generations=1,
            internal_error_generations=1,
            avg_response_time_ms=1234.56,
            total_input_tokens=5000,
            total_output_tokens=3000,
            avg_tokens_per_generation=800.0,
        ),
        daily=[
            DailyMetrics(
                date="2026-02-20",
                conversations=10,
                published_exercises=5,
                clean_generations=3,
                recovered_generations=2,
                fatal_generations=1,
                internal_error_generations=1,
                avg_response_time_ms=1234.56,
                total_input_tokens=5000,
                total_output_tokens=3000,
            ),
        ],
        date_from="2026-02-20",
        date_to="2026-02-20",
    )
    defaults.update(overrides)
    return AdminStatsResponse(**defaults)


ADMIN_SESSION = {"username": "admin.dupont", "platon_access": "tok", "role": "admin"}
TEACHER_SESSION = {"username": "jean.dupont", "platon_access": "tok", "role": "teacher"}
COOKIE_NAME = "agora_session_id"


def _make_mock_settings():
    """Return a MagicMock that behaves like Settings for admin tests."""
    mock = MagicMock()
    mock.SESSION_COOKIE_NAME = COOKIE_NAME
    mock.SESSION_TTL_SECONDS = 86400
    return mock


# ---------------------------------------------------------------------------
# App fixture (minimal, mirrors test_exercises.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis_default():
    return _make_redis()


@pytest.fixture
def app_factory():
    """Return a factory that builds a minimal FastAPI app with the admin router."""
    def _build(mock_redis=None, mock_db=None):
        application = FastAPI()
        application.include_router(router, prefix="/admin")
        if mock_redis is not None:
            application.dependency_overrides[get_redis] = lambda: mock_redis
        if mock_db is not None:
            application.dependency_overrides[get_db_session] = lambda: mock_db
        application.dependency_overrides[get_settings] = _make_mock_settings
        return application
    return _build


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAdminEndpoint:

    async def test_no_cookie_returns_401(self, app_factory):
        """Request without auth cookie → 401."""
        application = app_factory(
            mock_redis=_make_redis(),
            mock_db=_make_db_session(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get("/admin/stats")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    async def test_invalid_session_returns_401(self, app_factory):
        """Cookie present but session expired/invalid in Redis → 401."""
        application = app_factory(
            mock_redis=_make_redis(session_data=None),
            mock_db=_make_db_session(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get(
                "/admin/stats",
                cookies={COOKIE_NAME: "expired-session-id"},
            )

        assert response.status_code == 401
        assert "Session expired" in response.json()["detail"]

    async def test_teacher_role_returns_403(self, app_factory):
        """Valid session but TEACHER role → 403."""
        application = app_factory(
            mock_redis=_make_redis(session_data=TEACHER_SESSION),
            mock_db=_make_db_session(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get(
                "/admin/stats",
                cookies={COOKIE_NAME: "valid-teacher-session"},
            )

        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    async def test_admin_role_returns_200(self, app_factory):
        """ADMIN user → 200 with valid AdminStatsResponse JSON."""
        mock_response = _make_stats_response()
        application = app_factory(
            mock_redis=_make_redis(session_data=ADMIN_SESSION),
            mock_db=_make_db_session(),
        )

        with patch(
            "src.api.v1.endpoints.admin.get_admin_stats",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/admin/stats",
                    cookies={COOKIE_NAME: "valid-admin-session"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "daily" in data
        assert data["summary"]["total_conversations"] == 10
        assert data["summary"]["total_published_exercises"] == 5
        assert data["date_from"] == "2026-02-20"
        assert data["date_to"] == "2026-02-20"

    async def test_custom_date_params(self, app_factory):
        """Custom date_from/date_to query params are accepted and forwarded."""
        mock_response = _make_stats_response(
            date_from="2026-01-01",
            date_to="2026-01-31",
        )
        application = app_factory(
            mock_redis=_make_redis(session_data=ADMIN_SESSION),
            mock_db=_make_db_session(),
        )

        with patch(
            "src.api.v1.endpoints.admin.get_admin_stats",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_stats:
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/admin/stats",
                    params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
                    cookies={COOKIE_NAME: "valid-admin-session"},
                )

        assert response.status_code == 200
        # Verify the service was called with parsed date objects
        mock_stats.assert_awaited_once()
        call_args = mock_stats.call_args
        from datetime import date
        assert call_args[0][1] == date(2026, 1, 1)   # date_from
        assert call_args[0][2] == date(2026, 1, 31)  # date_to

    async def test_invalid_date_format_returns_400(self, app_factory):
        """Bad date_from string → 400."""
        application = app_factory(
            mock_redis=_make_redis(session_data=ADMIN_SESSION),
            mock_db=_make_db_session(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get(
                "/admin/stats",
                params={"date_from": "not-a-date"},
                cookies={COOKIE_NAME: "valid-admin-session"},
            )

        assert response.status_code == 400
        assert "Invalid date_from format" in response.json()["detail"]

    async def test_invalid_date_to_format_returns_400(self, app_factory):
        """Bad date_to string → 400."""
        application = app_factory(
            mock_redis=_make_redis(session_data=ADMIN_SESSION),
            mock_db=_make_db_session(),
        )

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get(
                "/admin/stats",
                params={"date_from": "2026-02-20", "date_to": "bad"},
                cookies={COOKIE_NAME: "valid-admin-session"},
            )

        assert response.status_code == 400
        assert "Invalid date_to format" in response.json()["detail"]
