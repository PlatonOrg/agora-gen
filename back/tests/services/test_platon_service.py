"""
Tests for src.services.platon_service.PlatonService.

Covers:
- _extract_exercise_state
- _build_files
- generate_ple_content
- check_resource_exists
- create_exercise_preview (success, no success flag, missing resource_id, eval failure)
- evaluate_exercise (success, missing exercise, feedbacks)
- get_topics / get_levels (dict and non-dict responses)
- get_resource
- extract_exercise_components
All HTTP calls are intercepted with httpx.MockTransport / respx or plain unittest.mock.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.services.models.platon import (
    SandboxError,
    PreviewResult,
    EvaluateResult,
)
from src.services.platon_service import PlatonService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(token: str = "test-token") -> PlatonService:
    return PlatonService(
        base_url="https://platon.test/api/v1",
        player_url="https://platon.test/player/preview",
        timeout=10.0,
        token=token,
    )


# ---------------------------------------------------------------------------
# _extract_exercise_state
# ---------------------------------------------------------------------------

class TestExtractExerciseState:
    def test_extracts_session_id(self):
        service = _make_service()
        data = {"exercise": {"sessionId": "s123", "title": "T", "form": "<f/>"}}
        state = service._extract_exercise_state(data)
        assert state.session_id == "s123"

    def test_extracts_title_and_form(self):
        service = _make_service()
        data = {"exercise": {"sessionId": "s1", "title": "My Title", "form": "<form/>"}}
        state = service._extract_exercise_state(data)
        assert state.title == "My Title"
        assert state.form == "<form/>"

    def test_missing_exercise_key_returns_empty_session_id(self):
        service = _make_service()
        state = service._extract_exercise_state({})
        assert state.session_id == ""

    def test_preview_url_attached(self):
        service = _make_service()
        data = {"exercise": {"sessionId": "s1"}}
        state = service._extract_exercise_state(data, preview_url="https://preview.url")
        assert state.preview_url == "https://preview.url"


# ---------------------------------------------------------------------------
# _build_files
# ---------------------------------------------------------------------------

class TestBuildFiles:
    def test_single_ple_file(self):
        service = _make_service()
        files = service._build_files(ple="title = T")
        assert len(files) == 1
        assert files[0]["path"] == "main.ple"
        assert files[0]["content"] == "title = T"

    def test_none_content_excluded(self):
        service = _make_service()
        files = service._build_files(ple="title = T", plo=None)
        assert len(files) == 1
        assert all(f["path"] != "main.plo" for f in files)

    def test_multiple_files(self):
        service = _make_service()
        files = service._build_files(ple="ple", plo="plo", plc="plc")
        paths = {f["path"] for f in files}
        assert paths == {"main.ple", "main.plo", "main.plc"}

    def test_all_none_returns_empty_list(self):
        service = _make_service()
        files = service._build_files(ple=None, plo=None)
        assert files == []


# ---------------------------------------------------------------------------
# generate_ple_content
# ---------------------------------------------------------------------------

class TestGeneratePleContent:
    def test_returns_extends_statement(self):
        service = _make_service()
        result = service.generate_ple_content("tpl-123")
        assert "@extends" in result
        assert "tpl-123" in result
        assert "latest" in result


# ---------------------------------------------------------------------------
# check_resource_exists
# ---------------------------------------------------------------------------

class TestCheckResourceExists:
    @pytest.mark.asyncio
    async def test_returns_true_when_resource_found(self):
        service = _make_service()
        service._request = AsyncMock(return_value={"id": "r1"})
        result = await service.check_resource_exists("r1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_sandbox_error(self):
        service = _make_service()
        service._request = AsyncMock(side_effect=SandboxError("not found"))
        result = await service.check_resource_exists("missing")
        assert result is False


# ---------------------------------------------------------------------------
# create_exercise_preview
# ---------------------------------------------------------------------------

class TestCreateExercisePreview:
    @pytest.mark.asyncio
    async def test_success_returns_preview_result(self):
        service = _make_service()
        preview_response = {
            "success": True,
            "resource": {"id": "r1"},
        }
        evaluate_response = {
            "exercise": {"sessionId": "s1", "title": "T", "form": "<f/>"},
        }
        service._request = AsyncMock(side_effect=[preview_response, evaluate_response])

        result = await service.create_exercise_preview(ple="title = T")

        assert isinstance(result, PreviewResult)
        assert result.resource_id == "r1"
        assert result.state.session_id == "s1"
        assert "r1" in result.state.preview_url

    @pytest.mark.asyncio
    async def test_raises_when_success_false(self):
        service = _make_service()
        service._request = AsyncMock(return_value={"success": False, "error": "Compile failed"})

        with pytest.raises(SandboxError, match="Preview creation failed"):
            await service.create_exercise_preview(ple="bad = code")

    @pytest.mark.asyncio
    async def test_raises_when_no_resource_id(self):
        service = _make_service()
        service._request = AsyncMock(return_value={"success": True, "resource": {}})

        with pytest.raises(SandboxError, match="No resource ID"):
            await service.create_exercise_preview(ple="title = T")

    @pytest.mark.asyncio
    async def test_raises_when_evaluate_success_false(self):
        service = _make_service()
        preview_response = {"success": True, "resource": {"id": "r1"}}
        evaluate_response = {"success": False, "error": "Runtime error"}
        service._request = AsyncMock(side_effect=[preview_response, evaluate_response])

        with pytest.raises(SandboxError, match="Sandbox evaluation failed"):
            await service.create_exercise_preview(ple="title = T")


# ---------------------------------------------------------------------------
# evaluate_exercise
# ---------------------------------------------------------------------------

class TestEvaluateExercise:
    @pytest.mark.asyncio
    async def test_returns_evaluate_result(self):
        service = _make_service()
        service._request = AsyncMock(return_value={
            "exercise": {
                "sessionId": "s1",
                "title": "T",
                "form": "<f/>",
                "feedbacks": [{"content": "Good job!", "type": "success"}],
                "platon_logs": [],
            }
        })

        result = await service.evaluate_exercise("s1")

        assert isinstance(result, EvaluateResult)
        assert result.session_id == "s1"
        assert len(result.feedbacks) == 1
        assert result.feedbacks[0].content == "Good job!"

    @pytest.mark.asyncio
    async def test_raises_when_exercise_key_missing(self):
        service = _make_service()
        service._request = AsyncMock(return_value={})

        with pytest.raises(SandboxError, match="Invalid evaluate response"):
            await service.evaluate_exercise("s1")

    @pytest.mark.asyncio
    async def test_ignores_non_dict_feedbacks(self):
        service = _make_service()
        service._request = AsyncMock(return_value={
            "exercise": {
                "sessionId": "s1",
                "feedbacks": ["not-a-dict", {"content": "OK", "type": "info"}],
                "platon_logs": [],
            }
        })

        result = await service.evaluate_exercise("s1")
        assert len(result.feedbacks) == 1
        assert result.feedbacks[0].type == "info"


# ---------------------------------------------------------------------------
# get_topics / get_levels
# ---------------------------------------------------------------------------

class TestGetTopicsAndLevels:
    @pytest.mark.asyncio
    async def test_get_topics_returns_resources(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value={"resources": [{"id": "t1", "name": "Algebra"}]})

        result = await service.get_topics()
        assert len(result) == 1
        assert result[0]["name"] == "Algebra"

    @pytest.mark.asyncio
    async def test_get_topics_returns_empty_list_when_no_resources_key(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value={})

        result = await service.get_topics()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_topics_returns_empty_list_when_non_dict_response(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value=[])

        result = await service.get_topics()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_levels_returns_resources(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value={"resources": [{"id": "l1", "name": "L1"}]})

        result = await service.get_levels()
        assert result[0]["name"] == "L1"


# ---------------------------------------------------------------------------
# get_resource
# ---------------------------------------------------------------------------

class TestGetResource:
    @pytest.mark.asyncio
    async def test_returns_resource_dict(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value={
            "success": True,
            "resource": {"id": "r1", "name": "Res"},
        })

        result = await service.get_resource("r1")
        assert result["id"] == "r1"

    @pytest.mark.asyncio
    async def test_raises_on_non_dict_response(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value="not-a-dict")

        with pytest.raises(RuntimeError, match="Invalid Platon response"):
            await service.get_resource("r1")

    @pytest.mark.asyncio
    async def test_raises_on_success_false(self):
        service = _make_service()
        service._request_with_token = AsyncMock(return_value={"success": False, "error": "nope"})

        with pytest.raises(RuntimeError, match="Platon API error"):
            await service.get_resource("r1")


# ---------------------------------------------------------------------------
# extract_exercise_components
# ---------------------------------------------------------------------------

class TestExtractExerciseComponents:
    @pytest.mark.asyncio
    async def test_extracts_component_selectors(self):
        service = _make_service()
        compiled = {
            "variables": {
                "q1": {"cid": "1", "selector": "tag-quiz"},
                "title": "My Exercise",
            }
        }
        service.compile_resource_json = AsyncMock(return_value=compiled)

        result = await service.extract_exercise_components("ex-1")
        assert "tag-quiz" in result

    @pytest.mark.asyncio
    async def test_uses_precompiled_json_when_provided(self):
        service = _make_service()
        service.compile_resource_json = AsyncMock()

        compiled = {"variables": {"q1": {"cid": "1", "selector": "tag-form"}}}
        result = await service.extract_exercise_components("ex-1", compiled_json=compiled)

        assert result == ["tag-form"]
        service.compile_resource_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_components(self):
        service = _make_service()
        compiled = {"variables": {"title": "T", "statement": "S"}}
        service.compile_resource_json = AsyncMock(return_value=compiled)

        result = await service.extract_exercise_components("ex-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self):
        service = _make_service()
        service.compile_resource_json = AsyncMock(side_effect=Exception("Network error"))

        result = await service.extract_exercise_components("ex-1")
        assert result == []

