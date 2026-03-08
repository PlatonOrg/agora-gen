"""
Tests for src.workflows.workflow helper functions.

Covers:
- _build_resource_overview_url: URL construction with and without /api/ in base URL
- _extract_top_resources: limit, missing resource_id handling, name extraction
- _find_best_template: score threshold, no templates, empty list
- _workflow_result_to_response: error and success paths
- _emit_progress: with/without callback, awaitable callback
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.models.api import ChatResponse, ExerciseData, WorkflowResult
from src.services.models.platon import ExerciseState, PreviewResult
from src.services.models.rag import RetrievedChunk
from src.workflows.workflow import (
    _build_resource_overview_url,
    _extract_top_resources,
    _find_best_template,
    _workflow_result_to_response,
    _emit_progress,
)


# ---------------------------------------------------------------------------
# _build_resource_overview_url
# ---------------------------------------------------------------------------

class TestBuildResourceOverviewUrl:
    def test_api_prefix_is_stripped(self):
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://platon.univ.fr/api/v1"
            url = _build_resource_overview_url("r123")
        assert url == "https://platon.univ.fr/resources/r123/overview"
        assert "/api/" not in url

    def test_no_api_prefix_leaves_base_intact(self):
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://platon.univ.fr"
            url = _build_resource_overview_url("r123")
        assert url == "https://platon.univ.fr/resources/r123/overview"

    def test_trailing_slash_is_stripped(self):
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://platon.univ.fr/api/v1/"
            url = _build_resource_overview_url("r1")
        assert not url.endswith("/")

    def test_resource_id_in_url(self):
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://platon.univ.fr/api/v1"
            url = _build_resource_overview_url("my-resource-42")
        assert "my-resource-42" in url


# ---------------------------------------------------------------------------
# _extract_top_resources
# ---------------------------------------------------------------------------

def _make_chunk(resource_id: str, name: str = None) -> RetrievedChunk:
    metadata = {"resource_id": resource_id}
    if name:
        metadata["name"] = name
    return RetrievedChunk(
        doc_type="EXERCICE",
        name=name,
        score=0.9,
        content="content",
        metadata=metadata,
    )


class TestExtractTopResources:
    def test_returns_up_to_limit(self):
        chunks = [_make_chunk(f"r{i}", f"Name {i}") for i in range(10)]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://p.fr/api/v1"
            result = _extract_top_resources(chunks, limit=3)
        assert len(result) == 3

    def test_missing_resource_id_is_skipped(self):
        chunk = RetrievedChunk(
            doc_type="EXERCICE", name=None, score=0.9, content="x",
            metadata={}
        )
        result = _extract_top_resources([chunk])
        assert result == []

    def test_blank_resource_id_is_skipped(self):
        chunk = RetrievedChunk(
            doc_type="EXERCICE", name=None, score=0.9, content="x",
            metadata={"resource_id": "  "}
        )
        result = _extract_top_resources([chunk])
        assert result == []

    def test_resource_id_in_result(self):
        chunks = [_make_chunk("r42", "Exercise 42")]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://p.fr/api/v1"
            result = _extract_top_resources(chunks)
        assert result[0]["resource_id"] == "r42"
        assert result[0]["name"] == "Exercise 42"

    def test_url_is_included(self):
        chunks = [_make_chunk("r1", "R1")]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.PLATON_BASE_URL = "https://p.fr/api/v1"
            result = _extract_top_resources(chunks)
        assert "url" in result[0]
        assert "r1" in result[0]["url"]

    def test_empty_list(self):
        result = _extract_top_resources([])
        assert result == []


# ---------------------------------------------------------------------------
# _find_best_template
# ---------------------------------------------------------------------------

def _make_template_chunk(score: float, resource_id: str = "tpl-1") -> RetrievedChunk:
    return RetrievedChunk(
        doc_type="TEMPLATE",
        name="Template",
        score=score,
        content="content",
        metadata={"kind": "TEMPLATE", "resource_id": resource_id, "platon_id": resource_id},
    )


def _make_exercise_chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        doc_type="EXERCICE",
        name="Exercise",
        score=score,
        content="content",
        metadata={"kind": "EXERCICE", "resource_id": "ex-1", "platon_id": "ex-1"},
    )


class TestFindBestTemplate:
    def test_returns_none_for_empty_list(self):
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template([])
        assert result is None

    def test_returns_none_when_no_templates(self):
        chunks = [_make_exercise_chunk(0.95)]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template(chunks)
        assert result is None

    def test_returns_template_when_score_above_threshold(self):
        chunks = [_make_template_chunk(0.95)]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template(chunks)
        assert result is not None
        assert result.metadata["resource_id"] == "tpl-1"

    def test_returns_none_when_score_below_threshold(self):
        chunks = [_make_template_chunk(0.85)]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template(chunks)
        assert result is None

    def test_returns_none_when_score_is_none(self):
        chunk = _make_template_chunk(0.95)
        chunk.score = None
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template([chunk])
        assert result is None

    def test_returns_best_template_among_mixed_chunks(self):
        chunks = [
            _make_exercise_chunk(0.99),
            _make_template_chunk(0.95, "tpl-best"),
            _make_template_chunk(0.92, "tpl-second"),
        ]
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template(chunks)
        assert result is not None
        assert result.metadata["resource_id"] == "tpl-best"

    def test_exact_threshold_score_qualifies(self):
        """Score exactly equal to threshold IS returned (implementation uses >=)."""
        chunk = _make_template_chunk(0.9)
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template([chunk])
        assert result is not None

    def test_score_below_threshold_not_returned(self):
        """Score strictly below threshold must NOT be returned."""
        chunk = _make_template_chunk(0.89)
        with patch("src.workflows.workflow.settings") as mock_settings:
            mock_settings.TEMPLATE_SCORE_THRESHOLD = 0.9
            result = _find_best_template([chunk])
        assert result is None


# ---------------------------------------------------------------------------
# _workflow_result_to_response
# ---------------------------------------------------------------------------

class TestWorkflowResultToResponse:
    def _make_result(self, **kwargs) -> WorkflowResult:
        defaults = dict(
            exercise_data=ExerciseData(),
            url="https://preview.example",
            message="Done",
        )
        defaults.update(kwargs)
        return WorkflowResult(**defaults)

    def test_success_path_returns_exercise_data_and_url(self):
        result = self._make_result()
        response = _workflow_result_to_response(result, ExerciseData())
        assert response.url == "https://preview.example"
        assert response.message == "Done"
        assert response.error is None

    def test_error_path_returns_error(self):
        result = self._make_result(error="Preview failed", url="")
        fallback = ExerciseData()
        response = _workflow_result_to_response(result, fallback)
        assert response.error == "Preview failed"
        assert response.exercise_data is fallback

    def test_retry_count_preserved(self):
        result = self._make_result(retry_count=2, retry_errors=["e1", "e2"])
        response = _workflow_result_to_response(result, ExerciseData())
        assert response.retry_count == 2
        assert response.retry_errors == ["e1", "e2"]

    def test_error_path_preserves_retry_info(self):
        result = self._make_result(error="fail", url="", retry_count=3, retry_errors=["a"])
        response = _workflow_result_to_response(result, ExerciseData())
        assert response.retry_count == 3


# ---------------------------------------------------------------------------
# _emit_progress
# ---------------------------------------------------------------------------

class TestEmitProgress:
    @pytest.mark.asyncio
    async def test_no_callback_is_noop(self):
        # Must not raise
        await _emit_progress(None, "event", {"key": "val"})

    @pytest.mark.asyncio
    async def test_sync_callback_is_called(self):
        callback = MagicMock()
        await _emit_progress(callback, "my_event", {"key": "val"})
        callback.assert_called_once_with("my_event", {"key": "val"})

    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(self):
        callback = AsyncMock()
        await _emit_progress(callback, "my_event", {"key": "val"})
        callback.assert_awaited_once_with("my_event", {"key": "val"})

    @pytest.mark.asyncio
    async def test_empty_data_defaults_to_empty_dict(self):
        callback = MagicMock()
        await _emit_progress(callback, "event")
        _, data_arg = callback.call_args[0]
        assert data_arg == {}

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self):
        def bad_callback(*args):
            raise RuntimeError("callback failed")

        # Must not raise
        await _emit_progress(bad_callback, "event", {})

