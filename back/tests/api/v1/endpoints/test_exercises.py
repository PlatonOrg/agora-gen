"""
Tests for src.api.v1.endpoints.exercises HTTP routes.

Covers:
- POST /exercises/state/save/{exercise_id}: saves to Redis, returns sanitised ExerciseData
- GET /exercises/state/{exercise_id}: cache hit, cache miss (404)
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.api.v1.endpoints.exercises import router
from src.infra.db.redis import get_redis
from src.services.models.api import ExerciseData


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.setex = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def app(mock_redis):
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_redis] = lambda: mock_redis
    return application


def _minimal_exercise_payload(**overrides) -> dict:
    base = {
        "titre": "Test Exercise",
        "enonce": "<p>Statement</p>",
        "forme": "<input/>",
        "construction": "def b(): pass",
        "evaluation": "def g(): pass",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST /exercises/state/save/{exercise_id}
# ---------------------------------------------------------------------------

class TestSaveExerciseState:
    @pytest.mark.asyncio
    async def test_save_returns_exercise_data(self, app, mock_redis):
        with patch("src.api.v1.endpoints.exercises.workspace_service") as mock_ws:
            mock_ws.sanitise_exercise_data = MagicMock()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/exercises/state/save/ex-123",
                    json=_minimal_exercise_payload(),
                )

        assert response.status_code == 200
        data = response.json()
        assert data["exercise_id"] == "ex-123"

    @pytest.mark.asyncio
    async def test_save_calls_redis_setex(self, app, mock_redis):
        with patch("src.api.v1.endpoints.exercises.workspace_service") as mock_ws:
            mock_ws.sanitise_exercise_data = MagicMock()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/exercises/state/save/ex-123",
                    json=_minimal_exercise_payload(),
                )

        mock_redis.setex.assert_awaited_once()
        key_used = mock_redis.setex.call_args[0][0]
        assert "ex-123" in key_used

    @pytest.mark.asyncio
    async def test_save_calls_sanitise(self, app, mock_redis):
        with patch("src.api.v1.endpoints.exercises.workspace_service") as mock_ws:
            mock_ws.sanitise_exercise_data = MagicMock()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/exercises/state/save/ex-123",
                    json=_minimal_exercise_payload(),
                )
        mock_ws.sanitise_exercise_data.assert_called_once()


# ---------------------------------------------------------------------------
# GET /exercises/state/{exercise_id}
# ---------------------------------------------------------------------------

class TestGetExerciseState:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_exercise(self, app, mock_redis):
        cached = ExerciseData(titre="Cached Title").model_dump_json()
        mock_redis.get = AsyncMock(return_value=cached)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/exercises/state/ex-123")

        assert response.status_code == 200
        assert response.json()["titre"] == "Cached Title"

    @pytest.mark.asyncio
    async def test_cache_miss_returns_404(self, app, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/exercises/state/nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cache_key_contains_exercise_id(self, app, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/exercises/state/my-unique-id")

        key_used = mock_redis.get.call_args[0][0]
        assert "my-unique-id" in key_used

