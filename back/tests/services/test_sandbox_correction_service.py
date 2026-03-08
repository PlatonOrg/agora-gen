"""
Tests for src.services.sandbox_correction_service.

Covers:
- apply_generated_to_exercise: field mapping, list keys, ignored keys, extra fields
- SandboxCorrectionService.preview_pure_exercise_with_retry: success, retry, failure, callback
- SandboxCorrectionService.preview_template_with_retry: success, correction merging, callback
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.models.api import ExerciseData, GeneratedExercise
from src.services.models.platon import ExerciseState, PreviewResult, SandboxError
from src.services.sandbox_correction_service import (
    SandboxCorrectionService,
    apply_generated_to_exercise,
)

# Repair prompt template fixture
FAKE_REPAIR_PROMPT = (
    "Fix. Attempt {attempt_number}/{max_attempts}. "
    "Error: {sandbox_error}. Code: {original_code}. Request: {user_request}."
)


def _make_preview(resource_id: str = "r1") -> PreviewResult:
    return PreviewResult(
        state=ExerciseState(session_id="s1", preview_url="https://p.com"),
        resource_id=resource_id,
    )


def _make_exercise(**kwargs) -> ExerciseData:
    return ExerciseData(**kwargs)


def _make_generated(**kwargs) -> GeneratedExercise:
    defaults = {
        "name": "N", "title": "T", "statement": "S",
        "form": "F", "solution": "Sol", "builder": "B",
        "grader": "G", "sandbox": "python",
    }
    defaults.update(kwargs)
    return GeneratedExercise(**defaults)


# ---------------------------------------------------------------------------
# apply_generated_to_exercise
# ---------------------------------------------------------------------------

class TestApplyGeneratedToExercise:
    @patch("src.services.workspace_service.workspace_service")
    def test_title_maps_to_titre(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(title="My Title")
        apply_generated_to_exercise(ex, gen)
        assert ex.titre == "My Title"

    @patch("src.services.workspace_service.workspace_service")
    def test_statement_maps_to_enonce(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(statement="<p>Do this</p>")
        apply_generated_to_exercise(ex, gen)
        assert ex.enonce == "<p>Do this</p>"

    @patch("src.services.workspace_service.workspace_service")
    def test_form_maps_to_forme(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(form="<form/>")
        apply_generated_to_exercise(ex, gen)
        assert ex.forme == "<form/>"

    @patch("src.services.workspace_service.workspace_service")
    def test_solution_maps_to_solution(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(solution="42")
        apply_generated_to_exercise(ex, gen)
        assert ex.solution == "42"

    @patch("src.services.workspace_service.workspace_service")
    def test_builder_maps_to_construction(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(builder="def b(): pass")
        apply_generated_to_exercise(ex, gen)
        assert ex.construction == "def b(): pass"

    @patch("src.services.workspace_service.workspace_service")
    def test_grader_maps_to_evaluation(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(grader="def g(): pass")
        apply_generated_to_exercise(ex, gen)
        assert ex.evaluation == "def g(): pass"

    @patch("src.services.workspace_service.workspace_service")
    def test_hint_maps_to_indications(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(hint=["tip1", "tip2"])
        apply_generated_to_exercise(ex, gen)
        assert ex.indications == ["tip1", "tip2"]

    @patch("src.services.workspace_service.workspace_service")
    def test_falsy_hint_defaults_to_empty_list(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(hint=None)
        apply_generated_to_exercise(ex, gen)
        assert ex.indications == []

    @patch("src.services.workspace_service.workspace_service")
    def test_theories_maps_to_theories(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(theories=[{"title": "T", "url": "u"}])
        apply_generated_to_exercise(ex, gen)
        assert ex.theories == [{"title": "T", "url": "u"}]

    @patch("src.services.workspace_service.workspace_service")
    def test_levels_maps_to_levels(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(levels=["CM2", "Difficile"])
        apply_generated_to_exercise(ex, gen)
        assert ex.levels == ["CM2", "Difficile"]

    @patch("src.services.workspace_service.workspace_service")
    def test_topics_maps_to_topics(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated(topics=["Géométrie", "Mathématiques"])
        apply_generated_to_exercise(ex, gen)
        assert ex.topics == ["Géométrie", "Mathématiques"]

    @patch("src.services.workspace_service.workspace_service")
    def test_author_key_is_ignored(self, mock_ws):
        ex = _make_exercise()
        gen = GeneratedExercise.from_llm_dict({"name": "N", "author": "John"})
        apply_generated_to_exercise(ex, gen)
        # "author" must not bleed into sandbox_variables or any field
        assert "author" not in (ex.sandbox_variables or {})

    @patch("src.services.workspace_service.workspace_service")
    def test_extra_fields_go_into_sandbox_variables(self, mock_ws):
        ex = _make_exercise()
        gen = GeneratedExercise.from_llm_dict({"name": "N", "my_custom_var": "val"})
        apply_generated_to_exercise(ex, gen)
        assert ex.sandbox_variables.get("my_custom_var") == "val"

    @patch("src.services.workspace_service.workspace_service")
    def test_sanitise_is_called(self, mock_ws):
        ex = _make_exercise()
        gen = _make_generated()
        apply_generated_to_exercise(ex, gen)
        mock_ws.sanitise_exercise_data.assert_called_once_with(ex)


# ---------------------------------------------------------------------------
# SandboxCorrectionService.preview_pure_exercise_with_retry
# ---------------------------------------------------------------------------

class TestPreviewPureExerciseWithRetry:
    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    @patch("src.services.workspace_service.workspace_service")
    async def test_success_on_first_attempt(self, mock_ws, mock_llm, _mock_prompt):
        mock_ws.from_json_to_ple.return_value = "title = T"
        mock_platon = AsyncMock()
        mock_platon.create_exercise_preview.return_value = _make_preview()

        service = SandboxCorrectionService()
        ex = _make_exercise(titre="T")
        gen = _make_generated()

        result = await service.preview_pure_exercise_with_retry(
            exercise_data=ex,
            generated_exercise=gen,
            user_request="make exercise",
            platon_service=mock_platon,
        )

        assert result.success is True
        assert result.attempts_used == 1
        mock_llm.assert_not_awaited()

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    @patch("src.services.workspace_service.workspace_service")
    async def test_retry_on_sandbox_error_then_success(self, mock_ws, mock_llm, _mock_prompt):
        mock_ws.from_json_to_ple.return_value = "title = T"
        mock_platon = AsyncMock()
        mock_platon.create_exercise_preview.side_effect = [
            SandboxError("compile error"),
            _make_preview(resource_id="fixed"),
        ]
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(
            parsed={"name": "N", "title": "Fixed", "builder": "b()", "grader": "g()", "sandbox": "python"},
            provider="groq",
            model="llama3",
        )

        service = SandboxCorrectionService()
        ex = _make_exercise(titre="T")
        gen = _make_generated()

        result = await service.preview_pure_exercise_with_retry(
            exercise_data=ex,
            generated_exercise=gen,
            user_request="make exercise",
            platon_service=mock_platon,
        )

        assert result.success is True
        assert result.attempts_used == 2
        mock_llm.assert_awaited_once()

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    @patch("src.services.workspace_service.workspace_service")
    async def test_all_attempts_fail(self, mock_ws, mock_llm, _mock_prompt):
        mock_ws.from_json_to_ple.return_value = "title = T"
        mock_platon = AsyncMock()
        mock_platon.create_exercise_preview.side_effect = SandboxError("always broken")
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(
            parsed={"name": "N", "title": "T", "builder": "b()", "grader": "g()", "sandbox": "python"},
            provider="groq",
            model="llama3",
        )

        service = SandboxCorrectionService()
        result = await service.preview_pure_exercise_with_retry(
            exercise_data=_make_exercise(),
            generated_exercise=_make_generated(),
            user_request="make exercise",
            platon_service=mock_platon,
        )

        assert result.success is False
        assert result.attempts_used == 3  # default max
        assert len(result.errors_encountered) == 3

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    @patch("src.services.workspace_service.workspace_service")
    async def test_progress_callback_fires_on_retry(self, mock_ws, mock_llm, _mock_prompt):
        mock_ws.from_json_to_ple.return_value = "title = T"
        mock_platon = AsyncMock()
        mock_platon.create_exercise_preview.side_effect = [
            SandboxError("err"),
            _make_preview(),
        ]
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(
            parsed={"name": "N", "title": "T", "builder": "b()", "grader": "g()", "sandbox": "python"},
            provider="groq",
            model="llama3",
        )
        callback = MagicMock()

        service = SandboxCorrectionService()
        await service.preview_pure_exercise_with_retry(
            exercise_data=_make_exercise(),
            generated_exercise=_make_generated(),
            user_request="test",
            platon_service=mock_platon,
            progress_callback=callback,
        )

        callback.assert_called_once()
        event_name, event_data = callback.call_args[0]
        assert event_name == "sandbox_retry"
        assert "attempt" in event_data
        assert "error" in event_data


# ---------------------------------------------------------------------------
# SandboxCorrectionService.preview_template_with_retry
# ---------------------------------------------------------------------------

class TestPreviewTemplateWithRetry:
    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    async def test_success_on_first_attempt(self, mock_llm, _mock_prompt):
        mock_platon = AsyncMock()
        mock_platon.generate_ple_content.return_value = "@extends /tpl:latest/main.ple"
        mock_platon.create_exercise_preview.return_value = _make_preview()

        ex = _make_exercise(
            template_id="tpl-1",
            config_variables={"inputs": [{"name": "v1", "value": "default"}]},
        )
        complete_vars = {"v1": "generated"}

        service = SandboxCorrectionService()
        result = await service.preview_template_with_retry(
            exercise_data=ex,
            complete_vars=complete_vars,
            user_request="gen vars",
            platon_service=mock_platon,
        )

        assert result.success is True
        assert result.attempts_used == 1
        mock_llm.assert_not_awaited()

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    async def test_correction_updates_complete_vars(self, mock_llm, _mock_prompt):
        mock_platon = AsyncMock()
        mock_platon.generate_ple_content.return_value = "@extends /tpl:latest/main.ple"
        mock_platon.create_exercise_preview.side_effect = [
            SandboxError("template error"),
            _make_preview(resource_id="tpl-fixed"),
        ]
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(
            parsed={"v1": "corrected_value"},
            provider="groq",
            model="llama3",
        )

        ex = _make_exercise(
            template_id="tpl-1",
            config_variables={"inputs": [{"name": "v1", "value": "default"}]},
        )
        complete_vars = {"v1": "original"}

        service = SandboxCorrectionService()
        result = await service.preview_template_with_retry(
            exercise_data=ex,
            complete_vars=complete_vars,
            user_request="gen vars",
            platon_service=mock_platon,
        )

        assert result.success is True
        assert complete_vars["v1"] == "corrected_value"

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    async def test_all_attempts_exhausted_returns_failure(self, mock_llm, _mock_prompt):
        mock_platon = AsyncMock()
        mock_platon.generate_ple_content.return_value = "@extends /tpl:latest/main.ple"
        mock_platon.create_exercise_preview.side_effect = SandboxError("persistent error")
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(
            parsed={"v1": "still_bad"},
            provider="groq",
            model="llama3",
        )

        ex = _make_exercise(
            template_id="tpl-1",
            config_variables={"inputs": [{"name": "v1", "value": "def"}]},
        )
        complete_vars = {"v1": "bad"}

        service = SandboxCorrectionService()
        result = await service.preview_template_with_retry(
            exercise_data=ex,
            complete_vars=complete_vars,
            user_request="gen",
            platon_service=mock_platon,
        )

        assert result.success is False

    @pytest.mark.asyncio
    @patch.object(SandboxCorrectionService, "_load_repair_prompt", return_value=FAKE_REPAIR_PROMPT)
    @patch("src.services.sandbox_correction_service.chat_with_llm", new_callable=AsyncMock)
    async def test_progress_callback_fires(self, mock_llm, _mock_prompt):
        mock_platon = AsyncMock()
        mock_platon.generate_ple_content.return_value = "@extends /tpl:latest/main.ple"
        mock_platon.create_exercise_preview.side_effect = [
            SandboxError("err"),
            _make_preview(),
        ]
        from src.services.models.api import LLMResult
        mock_llm.return_value = LLMResult(parsed={"v1": "ok"}, provider="groq", model="llama3")
        callback = MagicMock()

        ex = _make_exercise(
            template_id="tpl-1",
            config_variables={"inputs": [{"name": "v1", "value": "d"}]},
        )

        service = SandboxCorrectionService()
        await service.preview_template_with_retry(
            exercise_data=ex,
            complete_vars={"v1": "v"},
            user_request="gen",
            platon_service=mock_platon,
            progress_callback=callback,
        )

        callback.assert_called_once()
        event_name, _ = callback.call_args[0]
        assert event_name == "sandbox_retry"

