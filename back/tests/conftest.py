"""
Shared fixtures and configuration for the entire test suite.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.models.api import ExerciseData, ComponentInstance, GeneratedExercise
from src.services.models.platon import ExerciseState, PreviewResult


# ---------------------------------------------------------------------------
# pytest-asyncio configuration
# ---------------------------------------------------------------------------

pytest_plugins = ("pytest_asyncio",)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_exercise_data(**overrides) -> ExerciseData:
    """Return a minimal, valid ExerciseData instance."""
    defaults: dict = {
        "titre": "Sample Title",
        "enonce": "<p>Statement text</p>",
        "forme": "<input/>",
        "construction": "def builder(): pass",
        "evaluation": "def grader(): pass",
    }
    defaults.update(overrides)
    return ExerciseData(**defaults)


def make_preview_result(
    session_id: str = "sess-001",
    preview_url: str = "https://platon.example/preview/r1",
    resource_id: str = "r1",
) -> PreviewResult:
    """Return a minimal, valid PreviewResult instance."""
    return PreviewResult(
        state=ExerciseState(session_id=session_id, preview_url=preview_url),
        resource_id=resource_id,
    )


def make_generated_exercise(**overrides) -> GeneratedExercise:
    """Return a minimal GeneratedExercise instance."""
    defaults: dict = {
        "name": "Exercise Name",
        "title": "Title",
        "statement": "Do this",
        "form": "<form/>",
        "solution": "42",
        "builder": "def b(): pass",
        "grader": "def g(): pass",
        "sandbox": "python",
    }
    defaults.update(overrides)
    return GeneratedExercise(**defaults)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def exercise_data() -> ExerciseData:
    return make_exercise_data()


@pytest.fixture
def preview_result() -> PreviewResult:
    return make_preview_result()


@pytest.fixture
def generated_exercise() -> GeneratedExercise:
    return make_generated_exercise()


@pytest.fixture
def mock_platon_service() -> AsyncMock:
    """Mock of PlatonService with sensible defaults."""
    mock = AsyncMock()
    mock.generate_ple_content.return_value = "@extends /tpl:latest/main.ple"
    mock.create_exercise_preview.return_value = make_preview_result()
    mock.get_resource.return_value = {"name": "Resource", "desc": "A resource", "success": True}
    mock.compile_resource_json.return_value = {"variables": {}}
    mock.get_file_content.return_value = '{"inputs": []}'
    return mock

